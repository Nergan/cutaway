# Generic VPS: cloud-init + docker compose для того же origin-образа,
# что HF/Render. Не привязан к Hetzner/DO/etc. — оператор подставляет
# hostname и SSH сам. terraform validate — у оператора (нет registry в агенте).

terraform {
  required_version = ">= 1.5"
}

variable "hostname" {
  type        = string
  description = "Публичное имя узла (для cloud-init hostname)."
}

variable "origin_image" {
  type        = string
  description = "Тот же образ, что HF/Render: deploy/origin/Dockerfile."
  default     = "another-origin:local"
}

variable "run_xhttp" {
  type    = bool
  default = true
}

variable "run_reality" {
  type        = bool
  default     = false
  description = "Только когда есть стабильный IP и подобран SNI-донор."
}

variable "reality_dest" {
  type        = string
  default     = ""
  description = "SNI-донор host:port (не google.com)."
}

variable "reality_server_names" {
  type    = string
  default = ""
}

variable "reality_short_ids" {
  type      = string
  default   = ""
  sensitive = true
}

variable "reality_private_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "mongo_uri" {
  type      = string
  sensitive = true
}

variable "service_secret" {
  type      = string
  sensitive = true
}

variable "control_plane_url" {
  type    = string
  default = "https://cf-worker.another.example"
}

variable "ssh_user" {
  type    = string
  default = "ubuntu"
}

locals {
  cloud_init = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    hostname           = var.hostname
    origin_image       = var.origin_image
    run_xhttp              = var.run_xhttp ? "1" : "0"
    run_reality            = var.run_reality ? "1" : "0"
    mongo_uri              = var.mongo_uri
    service_secret         = var.service_secret
    control_plane_url      = var.control_plane_url
    ssh_user               = var.ssh_user
    reality_dest           = var.reality_dest
    reality_server_names   = var.reality_server_names
    reality_short_ids      = var.reality_short_ids
    reality_private_key    = var.reality_private_key
  })
}

output "cloud_init" {
  description = "user-data для любого VPS (Hetzner/DO/Vultr/...)."
  value       = local.cloud_init
  sensitive   = true
}

output "docker_compose_hint" {
  value = "На хосте после cloud-init: docker compose -f /opt/another/docker-compose.yml ps"
}
