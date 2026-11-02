# Alarmereignisse des Inferenz-Service. Empfänger werden separat ergänzt.
resource "azurerm_eventgrid_topic" "alarms" {
  name                          = "evgt-pruefstand-${substr(sha256(data.azurerm_client_config.iot.subscription_id), 0, 12)}"
  location                      = azurerm_resource_group.project.location
  resource_group_name           = azurerm_resource_group.project.name
  input_schema                  = "EventGridSchema"
  public_network_access_enabled = true
  local_auth_enabled            = false
  tags                          = azurerm_resource_group.project.tags
}

# Nur die bestehende Worker-Identität darf über diese Rolle Ereignisse senden.
resource "azurerm_role_assignment" "inference_events" {
  scope                            = azurerm_eventgrid_topic.alarms.id
  role_definition_name             = "EventGrid Data Sender"
  principal_id                     = azurerm_user_assigned_identity.inference.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

output "eventgrid_topic_name" {
  description = "Event-Grid-Topic für Alarmereignisse."
  value       = azurerm_eventgrid_topic.alarms.name
}

output "eventgrid_topic_endpoint" {
  description = "Veröffentlichungsadresse für den Inferenz-Service, kein Zugangsschlüssel."
  value       = azurerm_eventgrid_topic.alarms.endpoint
}
