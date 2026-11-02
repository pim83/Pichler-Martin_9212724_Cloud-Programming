# Terraform-Version der Cloud Shell: 1.16.4.
terraform {
  required_version = ">= 1.16.4, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Zum Einstieg liegt der Zustand im dauerhaft eingebundenen clouddrive.
  # Den gesamten Arbeitsordner erhalten. Ein Blob-Backend folgt vor dem Ausbau.
  backend "local" {
    path = "terraform.tfstate"
  }
}
