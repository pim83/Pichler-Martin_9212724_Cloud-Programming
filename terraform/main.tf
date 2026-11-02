# Erster Bereitstellungsschritt: nur die Ressourcengruppe als organisatorischer
# Rahmen. IoT Hub, Speicher und Inferenz-Service ergänzen wir schrittweise.
resource "azurerm_resource_group" "project" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    project     = "cloud-programming"
    environment = "development"
    managed_by  = "terraform"
  }
}
