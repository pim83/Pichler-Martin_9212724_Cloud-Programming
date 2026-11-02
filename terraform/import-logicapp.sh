#!/usr/bin/env bash
set -euo pipefail
umask 077

# Im bestehenden Terraform-Verzeichnis der Cloud Shell ausführen.
cd "$(dirname "$0")"
test -f logicapp.tf
test -f alarm-workflow.json
expected_subscription="9a3ac9e4-7982-4f63-9247-6e7178233e1f"
az account set --subscription "$expected_subscription"
export ARM_SUBSCRIPTION_ID="$expected_subscription"

terraform validate
existing_state=$(terraform state list)
if ! printf '%s\n' "$existing_state" | grep -Fxq 'azurerm_resource_group.project'; then
  echo "Abbruch: Bestehender Projekt-State nicht gefunden. Nicht in einem neuen Verzeichnis importieren."
  exit 1
fi

backup_file="terraform-before-logicapp-$(date -u +%Y%m%dT%H%M%SZ)-$$.tfstate"
terraform state pull > "$backup_file"
echo "State-Sicherung erstellt: $backup_file (enthält möglicherweise Secrets, nicht teilen)."

resource_base="/subscriptions/$expected_subscription/resourceGroups/rg-cloud-projekt-dev"
workflow_id="$resource_base/providers/Microsoft.Logic/workflows/la-pruefstand-alarm"

import_once() {
  local address="$1"
  local resource_id="$2"
  if printf '%s\n' "$existing_state" | grep -Fxq "$address"; then
    echo "Bereits im State: $address"
  else
    terraform import "$address" "$resource_id"
  fi
}

import_once azurerm_api_connection.alarm_eventgrid "$resource_base/providers/Microsoft.Web/connections/azureeventgrid"
import_once azurerm_api_connection.alarm_outlook "$resource_base/providers/Microsoft.Web/connections/office365"
import_once azurerm_logic_app_workflow.alarm "$workflow_id"
import_once azurerm_logic_app_action_custom.alarm_email "$workflow_id/actions/E-Mail_senden_(V2)"
import_once azurerm_logic_app_trigger_custom.alarm_event "$workflow_id/triggers/Bei_Eintritt_eines_Ressourcenereignisses"

terraform plan -out=logicapp-import.tfplan
echo "Import und Plan beendet. Kein Apply ausgeführt. Plan zuerst prüfen."
