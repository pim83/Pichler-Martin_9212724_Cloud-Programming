# Kleines Dashboard im kostenlosen F1-Tarif. Kein automatisches Hochskalieren.
# Die Verfügbarkeit im konkreten Abonnement wird beim Apply geprüft.
resource "azurerm_service_plan" "frontend" {
  name                = "plan-pruefstand-web"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  os_type             = "Linux"
  sku_name            = "F1"
  tags                = azurerm_resource_group.project.tags
}

resource "azurerm_linux_web_app" "frontend" {
  name                = "web-pruef-${substr(sha256(data.azurerm_client_config.iot.subscription_id), 0, 12)}"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  service_plan_id     = azurerm_service_plan.frontend.id
  https_only          = true

  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on           = false
    minimum_tls_version = "1.2"
    scm_minimum_tls_version = "1.2"
    ftps_state          = "Disabled"
    # Ein Worker: die Anmeldebegrenzung wird innerhalb dieses Prozesses geteilt.
    app_command_line = "gunicorn --workers 1 --bind=0.0.0.0 --timeout 60 app:app"

    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = {
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    ENABLE_ORYX_BUILD             = "true"
    RESULTS_API_URL               = "https://${azurerm_linux_function_app.api.default_hostname}/api"
    PUBLIC_DEVICE_IDS            = "pruefstand-01"

    # Nur Referenzen, keine geheimen Werte im Terraform-State.
    RESULTS_API_KEY          = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault.project.vault_uri}secrets/results-api-key/)"
    DASHBOARD_PASSWORD_HASH  = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault.project.vault_uri}secrets/dashboard-password-hash/)"
    DASHBOARD_SESSION_KEY    = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault.project.vault_uri}secrets/dashboard-session-key/)"
  }

  tags = azurerm_resource_group.project.tags
}

# Der Projekt-Vault enthält die drei Dashboard-Secrets. Nur lesen, nicht ändern.
resource "azurerm_role_assignment" "frontend_secrets" {
  scope                = azurerm_key_vault.project.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_web_app.frontend.identity[0].principal_id
  principal_type       = "ServicePrincipal"
}

output "frontend_app_name" {
  value = azurerm_linux_web_app.frontend.name
}

output "frontend_url" {
  value = "https://${azurerm_linux_web_app.frontend.default_hostname}"
}
