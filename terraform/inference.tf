# Inferenz-Worker: standardmäßig ausgeschaltet, gezielt für Tests einschalten.
variable "inference_enabled" {
  description = "Eine Worker-Instanz für Tests starten. Nach Tests wieder false setzen."
  type        = bool
  default     = false
}

variable "inference_image_digest" {
  description = "Unveränderlicher Image-Digest. Beim Rollout auf den neuen Build setzen."
  type        = string
  default     = "sha256:c80f82c558a69bcf3b37fd8f0902eae995560a79c1a73f13cb8b43a59669ad53"

  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.inference_image_digest))
    error_message = "Der Image-Digest muss sha256: und 64 kleine Hex-Zeichen enthalten."
  }
}

# Checkpoints bleiben erhalten, auch wenn temporäre Messabschnitte gelöscht werden.
resource "azurerm_storage_container" "checkpoints" {
  name                  = "checkpoints"
  storage_account_id    = azurerm_storage_account.measurements.id
  container_access_type = "private"
}

resource "azurerm_iothub_consumer_group" "inference" {
  name                   = "inferenz"
  iothub_name            = azurerm_iothub.measurements.name
  eventhub_endpoint_name = "events"
  resource_group_name    = azurerm_resource_group.project.name
}

# Der bestehende Worker verwendet für den IoT-Empfang eine Service-Verbindung.
# Kein iothubowner-Schlüssel und kein Zugang zur Geräteverwaltung.
resource "azurerm_iothub_shared_access_policy" "inference" {
  name                = "inferenz-service"
  resource_group_name = azurerm_resource_group.project.name
  iothub_name         = azurerm_iothub.measurements.name
  service_connect     = true
  device_connect      = false
  registry_read       = false
  registry_write      = false
}

resource "azurerm_user_assigned_identity" "inference" {
  name                = "id-pruefstand-inferenz"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  tags                = azurerm_resource_group.project.tags
}

resource "azurerm_role_assignment" "inference_image" {
  scope                            = azurerm_container_registry.inference.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.inference.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "inference_model" {
  scope                            = "${azurerm_storage_account.measurements.id}/blobServices/default/containers/${azurerm_storage_container.models.name}"
  role_definition_name             = "Storage Blob Data Reader"
  principal_id                     = azurerm_user_assigned_identity.inference.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "inference_data" {
  for_each = {
    measurements = azurerm_storage_container.measurements.name
    chunks       = azurerm_storage_container.chunks.name
    checkpoints  = azurerm_storage_container.checkpoints.name
  }
  scope                            = "${azurerm_storage_account.measurements.id}/blobServices/default/containers/${each.value}"
  role_definition_name             = "Storage Blob Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.inference.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_cosmosdb_sql_role_assignment" "inference_results" {
  resource_group_name = azurerm_resource_group.project.name
  account_name        = azurerm_cosmosdb_account.results.name
  role_definition_id  = "${azurerm_cosmosdb_account.results.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azurerm_user_assigned_identity.inference.principal_id
  scope               = "${azurerm_cosmosdb_account.results.id}/dbs/${azurerm_cosmosdb_sql_database.results.name}"
}

# Kleine Protokollablage für Fehlersuche und Funktionsnachweis.
# Das tägliche Datenlimit ist keine garantierte Kostensperre.
resource "azurerm_log_analytics_workspace" "inference" {
  name                = "log-pruefstand-dev"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.1
  tags                = azurerm_resource_group.project.tags
}

resource "azurerm_container_app_environment" "inference" {
  name                       = "cae-pruefstand-dev"
  resource_group_name        = azurerm_resource_group.project.name
  location                   = azurerm_resource_group.project.location
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.inference.id

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
  tags = azurerm_resource_group.project.tags
}

resource "azurerm_container_app" "inference" {
  name                         = "ca-pruefstand-inferenz"
  resource_group_name          = azurerm_resource_group.project.name
  container_app_environment_id = azurerm_container_app_environment.inference.id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"

  # Azure meldet für diese Express-App beide Skalierungsintervalle als 0.
  # Ohne eigene Skalierungsregel behalten wir diese Plattformwerte bei,
  # statt bei jedem Update die Provider-Defaults 300/30 zu erzwingen.
  # Bei Einführung automatischer Skalierung diese Ausnahme neu prüfen.
  lifecycle {
    ignore_changes = [
      template[0].cooldown_period_in_seconds,
      template[0].polling_interval_in_seconds,
    ]
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.inference.id]
  }

  registry {
    server   = azurerm_container_registry.inference.login_server
    identity = azurerm_user_assigned_identity.inference.id
  }

  # Event-Hubs-kompatibler Endpunkt des vorhandenen IoT Hubs.
  # Terraform schützt die Anzeige, speichert den Wert aber im lokalen State.
  # Keine State- oder Plan-Dateien veröffentlichen.
  secret {
    name  = "iothub-events"
    value = "Endpoint=${azurerm_iothub.measurements.event_hub_events_endpoint};SharedAccessKeyName=${azurerm_iothub_shared_access_policy.inference.name};SharedAccessKey=${azurerm_iothub_shared_access_policy.inference.primary_key};EntityPath=${azurerm_iothub.measurements.event_hub_events_path}"
  }

  # Kein ingress und kein automatischer Skalierungstrigger.
  # false: skaliert auf null und wacht NICHT durch IoT-Nachrichten auf.
  # true: genau eine gewünschte Instanz, damit der Worker Nachrichten abholt.
  template {
    min_replicas = var.inference_enabled ? 1 : 0
    max_replicas = 1
    # Express-Umgebungen unterstützen keine eigene Beendigungsfrist.
    # Daher die Azure-Vorgabe verwenden und das optionale Feld weglassen.

    container {
      name   = "inferenz"
      image  = "${azurerm_container_registry.inference.login_server}/pruefstand-inferenz@${var.inference_image_digest}"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.inference.client_id
      }
      env {
        name  = "BLOB_ACCOUNT_URL"
        value = azurerm_storage_account.measurements.primary_blob_endpoint
      }
      env {
        name  = "COSMOS_URL"
        value = azurerm_cosmosdb_account.results.endpoint
      }
      env {
        name  = "EVENTGRID_TOPIC_ENDPOINT"
        value = azurerm_eventgrid_topic.alarms.endpoint
      }
      env {
        name  = "MODEL_BLOB"
        value = "autoencoder.npz"
      }
      env {
        name  = "MODEL_SHA256"
        value = "accd8bacb8647e9dfc4c2e647b7421d607fe7029708bdc6f56b226607c9bae57"
      }
      env {
        name        = "IOTHUB_EVENT_CONNECTION_STRING"
        secret_name = "iothub-events"
      }
    }
  }

  # Erst nach Anlage der Berechtigungen und Empfangsgruppe bereitstellen.
  # Die tatsächliche Azure-Rollenverteilung kann trotzdem kurz verzögert sein.
  depends_on = [
    azurerm_role_assignment.inference_image,
    azurerm_role_assignment.inference_model,
    azurerm_role_assignment.inference_data,
    azurerm_role_assignment.inference_events,
    azurerm_cosmosdb_sql_role_assignment.inference_results,
    azurerm_cosmosdb_sql_container.results,
    azurerm_iothub_consumer_group.inference,
  ]
  tags = azurerm_resource_group.project.tags
}

output "inference_app_name" {
  description = "Name der Container App für Status und Protokolle."
  value       = azurerm_container_app.inference.name
}

output "inference_enabled" {
  description = "Gewünschter Testbetrieb, kein Nachweis einer laufenden Instanz."
  value       = var.inference_enabled
}

output "inference_image" {
  description = "Festgelegtes Image einschließlich Digest."
  value       = azurerm_container_app.inference.template[0].container[0].image
}
