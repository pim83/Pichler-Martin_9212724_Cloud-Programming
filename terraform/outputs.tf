output "resource_group_name" {
  description = "Name der angelegten Projektressourcengruppe."
  value       = azurerm_resource_group.project.name
}

output "location" {
  description = "Region der Projektressourcengruppe."
  value       = azurerm_resource_group.project.location
}
