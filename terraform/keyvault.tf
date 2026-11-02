# Zentraler Secret-Speicher. Secret-Werte werden separat hinterlegt,
# damit Dashboard-Passwort und Sitzungsschlüssel nicht im Terraform-State landen.
resource "azurerm_key_vault" "project" {
  name                       = "kv-pruef-${substr(sha256(data.azurerm_client_config.iot.subscription_id), 0, 12)}"
  location                   = azurerm_resource_group.project.location
  resource_group_name        = azurerm_resource_group.project.name
  tenant_id                  = data.azurerm_client_config.iot.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  # Erreichbar über HTTPS, Datenzugriff ausschließlich nach Entra/RBAC-Prüfung.
  # Die Web-App erhält später eine eigene Managed Identity mit Leserechten.
  public_network_access_enabled = true
  tags                          = azurerm_resource_group.project.tags
}

# Das bereits für Terraform verwendete Konto darf Projekt-Secrets verwalten.
# Keine Entra-App-Registrierung und keine Änderung am Hochschulverzeichnis.
resource "azurerm_role_assignment" "project_secret_manager" {
  scope                = azurerm_key_vault.project.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.iot.object_id
}

output "key_vault_name" {
  description = "Name des Secret-Speichers, kein geheimer Wert."
  value       = azurerm_key_vault.project.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.project.vault_uri
}
