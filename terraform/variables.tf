variable "location" {
  description = "Projektregion. Unabhängig vom Cloud-Shell-Speicher in Frankreich."
  type        = string
  default     = "germanywestcentral"
}

variable "resource_group_name" {
  description = "Gemeinsame Ressourcengruppe für die Projektanwendung."
  type        = string
  default     = "rg-cloud-projekt-dev"
}
