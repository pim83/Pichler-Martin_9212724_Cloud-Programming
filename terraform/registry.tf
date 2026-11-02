# Ablage für das Container-Image unseres Inferenz-Service.
# Basic genügt für den Prototyp. Die Registry führt das Programm nicht aus.
resource "azurerm_container_registry" "inference" {
  name                = "acrpruef${substr(sha256(data.azurerm_client_config.iot.subscription_id), 0, 12)}"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  sku                 = "Basic"

  # Zugriff über Azure-Identitäten statt gemeinsamem Admin-Kennwort.
  admin_enabled = false

  # Erreichbarer Endpunkt, aber kein anonymer Zugriff auf die Images.
  # Basic bietet keine Private Endpoints. Die spätere Container App bekommt
  # eine gezielte AcrPull-Rolle für ihre verwaltete Identität.
  public_network_access_enabled = true
  tags                          = azurerm_resource_group.project.tags
}

output "container_registry_name" {
  description = "Name der Registry für den späteren Image-Build."
  value       = azurerm_container_registry.inference.name
}

output "container_registry_login_server" {
  description = "Registry-Adresse für das Container-Image, ohne Zugangsdaten."
  value       = azurerm_container_registry.inference.login_server
}
