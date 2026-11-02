# Anwendungsspeicher. Der Terraform-Zustand bleibt im Cloud-Shell-Verzeichnis.
resource "azurerm_storage_account" "measurements" {
  name                     = "stpruef${substr(sha256(data.azurerm_client_config.iot.subscription_id), 0, 12)}"
  resource_group_name      = azurerm_resource_group.project.name
  location                 = azurerm_resource_group.project.location
  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "LRS"
  access_tier              = "Hot"

  # LRS ist die kostengünstige Prototypvariante, ohne regionale Ausfallsicherheit.
  https_traffic_only_enabled      = true
  min_tls_version                = "TLS1_2"
  allow_nested_items_to_be_public = false
  public_network_access_enabled  = true

  # Der öffentliche Endpunkt verlangt trotzdem eine Authentifizierung.
  # Terraform verwendet zunächst Shared Key. Der spätere Inferenz-Service
  # soll mit verwalteter Identität und gezielten Rollen zugreifen.
  shared_access_key_enabled = true
  tags                      = azurerm_resource_group.project.tags
}

resource "azurerm_storage_container" "measurements" {
  name                  = "messdaten"
  storage_account_id    = azurerm_storage_account.measurements.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "chunks" {
  name                  = "temporaer"
  storage_account_id    = azurerm_storage_account.measurements.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "models" {
  name                  = "modelle"
  storage_account_id    = azurerm_storage_account.measurements.id
  container_access_type = "private"
}

# Sicherheitsnetz für abgebrochene Übertragungen. Vollständige Messungen
# und Modelle sind vom Löschfilter ausgeschlossen. Die Regel läuft asynchron.
resource "azurerm_storage_management_policy" "temporary_cleanup" {
  storage_account_id = azurerm_storage_account.measurements.id
  rule {
    name    = "temporaere-abschnitte-bereinigen"
    enabled = true
    filters {
      prefix_match = ["temporaer/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 7
      }
    }
  }
}

output "measurement_storage_account" {
  description = "Speicherkonto für Messdaten und Modelle, ohne Zugangsschlüssel."
  value       = azurerm_storage_account.measurements.name
}

output "measurement_blob_endpoint" {
  description = "Blob-Endpunkt. Zugriff erfordert Authentifizierung."
  value       = azurerm_storage_account.measurements.primary_blob_endpoint
}
