# Bestehende Ressourcen zuerst importieren. Keine parallele Alarmierung anlegen.
locals {
  alarm_definition = jsondecode(file("${path.module}/alarm-workflow.json"))
  alarm_trigger    = local.alarm_definition.triggers.Bei_Eintritt_eines_Ressourcenereignisses
  alarm_api_base   = "/subscriptions/${data.azurerm_client_config.iot.subscription_id}/providers/Microsoft.Web/locations/${azurerm_resource_group.project.location}/managedApis"
}

resource "azurerm_api_connection" "alarm_eventgrid" {
  name                = "azureeventgrid"
  resource_group_name = azurerm_resource_group.project.name
  managed_api_id      = "${local.alarm_api_base}/azureeventgrid"
  display_name        = "alarm@example.invalid"
  lifecycle {
    prevent_destroy = true
    # OAuth-Autorisierung erfolgt interaktiv und bleibt außerhalb von Terraform.
    ignore_changes = [parameter_values]
  }
}

resource "azurerm_api_connection" "alarm_outlook" {
  name                = "office365"
  resource_group_name = azurerm_resource_group.project.name
  managed_api_id      = "${local.alarm_api_base}/office365"
  display_name        = "office365-pruefstand-alarm"
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [parameter_values]
  }
}

resource "azurerm_logic_app_workflow" "alarm" {
  name                = "la-pruefstand-alarm"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  enabled             = true
  workflow_schema     = local.alarm_definition["$schema"]
  workflow_version    = local.alarm_definition.contentVersion
  workflow_parameters = {
    "$connections" = jsonencode(local.alarm_definition.parameters["$connections"])
  }
  parameters = {
    "$connections" = jsonencode({
      azureeventgrid = {
        connectionId         = azurerm_api_connection.alarm_eventgrid.id
        connectionName       = azurerm_api_connection.alarm_eventgrid.name
        connectionProperties = {}
        id                   = "${local.alarm_api_base}/azureeventgrid"
      }
      office365 = {
        connectionId         = azurerm_api_connection.alarm_outlook.id
        connectionName       = azurerm_api_connection.alarm_outlook.name
        connectionProperties = {}
        id                   = "${local.alarm_api_base}/office365"
      }
    })
  }
  lifecycle { prevent_destroy = true }
}

resource "azurerm_logic_app_action_custom" "alarm_email" {
  name         = "E-Mail_senden_(V2)"
  logic_app_id = azurerm_logic_app_workflow.alarm.id
  body         = jsonencode(local.alarm_definition.actions["E-Mail_senden_(V2)"])
  lifecycle { prevent_destroy = true }
}

resource "azurerm_logic_app_trigger_custom" "alarm_event" {
  name         = "Bei_Eintritt_eines_Ressourcenereignisses"
  logic_app_id = azurerm_logic_app_workflow.alarm.id
  body = jsonencode(merge(local.alarm_trigger, {
    inputs = merge(local.alarm_trigger.inputs, {
      path = "/subscriptions/@{encodeURIComponent('${data.azurerm_client_config.iot.subscription_id}')}/providers/@{encodeURIComponent('Microsoft.EventGrid.Topics')}/resource/eventSubscriptions"
      body = {
        properties = merge(local.alarm_trigger.inputs.body.properties, {
          topic = azurerm_eventgrid_topic.alarms.id
        })
      }
    })
  }))
  # Dieser Connector erzeugt und verwaltet das Event-Grid-Abonnement selbst.
  # Deshalb keine zweite azurerm_eventgrid_event_subscription für dasselbe Abo.
  depends_on = [azurerm_logic_app_action_custom.alarm_email]
  lifecycle { prevent_destroy = true }
}
