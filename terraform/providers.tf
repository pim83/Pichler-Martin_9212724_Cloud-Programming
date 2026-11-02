# Die Cloud Shell ist bereits über die Azure CLI angemeldet.
# ARM_SUBSCRIPTION_ID legt das Zielabonnement ausdrücklich fest.
provider "azurerm" {
  features {
    resource_group {
      # Verhindert das Löschen einer Gruppe mit zusätzlichen Ressourcen.
      prevent_deletion_if_contains_resources = true
    }
  }

  # Weitere Azure-Dienste registrieren wir gezielt, sobald sie benötigt werden.
  resource_provider_registrations = "none"
}
