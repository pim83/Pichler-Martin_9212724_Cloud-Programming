# Ergebnisablage für den Prototyp mit einem Prüfstand.
# Serverless berechnet verbrauchte Request Units und gespeicherte Daten.
# Deshalb weder festen Durchsatz noch Autoscale-Durchsatz konfigurieren.
resource "azurerm_cosmosdb_account" "results" {
  name                = "cosmos-pruef-${substr(sha256(data.azurerm_client_config.iot.subscription_id), 0, 12)}"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  # Eine Region genügt für den Funktionsnachweis.
  geo_location {
    location          = azurerm_resource_group.project.location
    failover_priority = 0
    zone_redundant    = false
  }

  backup {
    type                = "Periodic"
    interval_in_minutes = 240
    retention_in_hours  = 8
    storage_redundancy  = "Local"
  }

  minimal_tls_version           = "Tls12"
  public_network_access_enabled = true
  # Öffentlich erreichbar, aber ausschließlich mit Entra-Authentifizierung.
  # Die Datenrolle des Workers ergänzen wir mit seiner verwalteten Identität.
  local_authentication_enabled = false
  free_tier_enabled            = false
  tags                         = azurerm_resource_group.project.tags
}

resource "azurerm_cosmosdb_sql_database" "results" {
  name                = "pruefstand"
  resource_group_name = azurerm_resource_group.project.name
  account_name        = azurerm_cosmosdb_account.results.name
}

resource "azurerm_cosmosdb_sql_container" "results" {
  name                  = "ergebnisse"
  resource_group_name   = azurerm_resource_group.project.name
  account_name          = azurerm_cosmosdb_account.results.name
  database_name         = azurerm_cosmosdb_sql_database.results.name
  partition_key_paths   = ["/device_id"]
  partition_key_kind    = "Hash"
  partition_key_version = 2
  # Ergebnisse bleiben für die Dokumentation erhalten. Keine automatische TTL.
}

output "cosmos_account_name" {
  description = "Cosmos-DB-Konto für die Analyseergebnisse."
  value       = azurerm_cosmosdb_account.results.name
}

output "cosmos_endpoint" {
  description = "Endpunkt für COSMOS_URL, ohne Zugangsschlüssel."
  value       = azurerm_cosmosdb_account.results.endpoint
}
