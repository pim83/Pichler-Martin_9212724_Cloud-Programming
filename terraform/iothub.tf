# Informationen zum angemeldeten Azure-Konto. Es werden keine Zugangsdaten ausgegeben.
data "azurerm_client_config" "iot" {}

variable "iothub_units" {
  description = "B1-Einheiten: eine für den Prototyp, zwei laut Planung für zehn Prüfstände."
  type        = number
  default     = 1

  validation {
    condition     = var.iothub_units >= 1 && var.iothub_units <= 200 && floor(var.iothub_units) == var.iothub_units
    error_message = "Die Anzahl muss eine ganze Zahl zwischen 1 und 200 sein."
  }
}

resource "azurerm_iothub" "measurements" {
  # Ein kurzer, reproduzierbarer Zusatz aus der Subscription-ID hilft dabei,
  # einen Azure-weit eindeutigen Hub-Namen zu erhalten.
  name                = "iot-pruefstand-${substr(sha256(data.azurerm_client_config.iot.subscription_id), 0, 12)}"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location

  # Basic reicht für Geräte-Telemetrie und den Empfang durch unseren Service.
  # Eine Einheit reicht für einen simulierten Prüfstand im stündlichen Betrieb.
  sku {
    name     = "B1"
    capacity = var.iothub_units
  }

  min_tls_version               = "1.2"
  public_network_access_enabled = true
  local_authentication_enabled  = true

  # Der öffentliche Endpunkt benötigt trotzdem eine Authentifizierung.
  # Für den Sender verwenden wir später ausschließlich seine Gerätezugangsdaten,
  # keinen administrativen Hub-Schlüssel.
  event_hub_partition_count   = 4
  event_hub_retention_in_days = 1

  # Alle Gerätenachrichten an den eingebauten Empfangsendpunkt weiterleiten.
  # Dafür wird kein separater Event-Hubs-Dienst angelegt.
  route {
    name           = "messdaten-zum-inferenz-service"
    source         = "DeviceMessages"
    condition      = "true"
    endpoint_names = ["events"]
    enabled        = true
  }

  tags = azurerm_resource_group.project.tags
}

output "iothub_name" {
  description = "Name des IoT Hubs für Geräteanlage und Sendeskript."
  value       = azurerm_iothub.measurements.name
}

output "iothub_hostname" {
  description = "Adresse des Hubs ohne Schlüssel oder Kennwort."
  value       = azurerm_iothub.measurements.hostname
}
