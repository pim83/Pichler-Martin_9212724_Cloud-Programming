# Lesende Function API, getrennt vom Inferenz-Worker.
resource "azurerm_storage_account" "api" {
  name                            = "stapi${substr(sha256(data.azurerm_client_config.iot.subscription_id), 0, 12)}"
  resource_group_name             = azurerm_resource_group.project.name
  location                        = azurerm_resource_group.project.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = azurerm_resource_group.project.tags
}

resource "azurerm_service_plan" "api" {
  name                = "plan-pruefstand-api"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  os_type             = "Linux"
  sku_name            = "Y1"
  tags                = azurerm_resource_group.project.tags
}

resource "azurerm_application_insights" "api" {
  name                = "appi-pruefstand-api"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  workspace_id        = azurerm_log_analytics_workspace.inference.id
  application_type    = "web"
  tags                = azurerm_resource_group.project.tags
}

resource "azurerm_linux_function_app" "api" {
  name                       = "func-pruef-api-${substr(sha256(data.azurerm_client_config.iot.subscription_id), 0, 12)}"
  resource_group_name        = azurerm_resource_group.project.name
  location                   = azurerm_resource_group.project.location
  service_plan_id            = azurerm_service_plan.api.id
  storage_account_name       = azurerm_storage_account.api.name
  # Nur Host-Speicher. Cosmos-Zugriff erfolgt schlüssellos per Identität.
  # Dieser Schlüssel steht im geschützten Terraform-State, nie in Outputs.
  storage_account_access_key = azurerm_storage_account.api.primary_access_key
  https_only                 = true
  functions_extension_version = "~4"
  builtin_logging_enabled     = false
  ftp_publish_basic_authentication_enabled = false

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on                              = false
    minimum_tls_version                    = "1.2"
    ftps_state                             = "Disabled"
    application_insights_connection_string = azurerm_application_insights.api.connection_string
    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME       = "python"
    COSMOS_URL                     = azurerm_cosmosdb_account.results.endpoint
    SCM_DO_BUILD_DURING_DEPLOYMENT  = "true"
    ENABLE_ORYX_BUILD              = "true"
    # Host.Results muss Information sein, sonst fehlen erfolgreiche Aufrufe.
    # Überschreibt gezielt den Warning-Standard aus host.json.
    "AzureFunctionsJobHost__logging__logLevel__Host.Results"    = "Information"
    "AzureFunctionsJobHost__logging__logLevel__Host.Aggregator" = "Information"
    "AzureFunctionsJobHost__logging__applicationInsights__samplingSettings__excludedTypes" = "Request;Exception"
  }
  tags = azurerm_resource_group.project.tags
}

resource "azurerm_cosmosdb_sql_role_assignment" "api_results" {
  resource_group_name = azurerm_resource_group.project.name
  account_name        = azurerm_cosmosdb_account.results.name
  role_definition_id  = "${azurerm_cosmosdb_account.results.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000001"
  principal_id        = azurerm_linux_function_app.api.identity[0].principal_id
  scope               = "${azurerm_cosmosdb_account.results.id}/dbs/${azurerm_cosmosdb_sql_database.results.name}/colls/${azurerm_cosmosdb_sql_container.results.name}"
}

output "api_app_name" {
  value = azurerm_linux_function_app.api.name
}

output "api_base_url" {
  description = "API-Adresse. Cloud-Aufrufe benötigen zusätzlich einen Function-Schlüssel."
  value       = "https://${azurerm_linux_function_app.api.default_hostname}/api"
}
