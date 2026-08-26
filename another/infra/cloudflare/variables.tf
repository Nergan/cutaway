variable "cloudflare_api_token" {
  description = "Cloudflare API token: Zone:DNS Edit, Zone:Zone Settings Edit, Account:Workers KV Storage Edit. См. .env.example (CLOUDFLARE_API_TOKEN)."
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "См. .env.example (CLOUDFLARE_ACCOUNT_ID)"
  type        = string
}

variable "cloudflare_zone_id" {
  description = "См. .env.example (CLOUDFLARE_ZONE_ID)"
  type        = string
}

variable "cloudflare_account_subdomain" {
  description = "Поддомен workers.dev аккаунта (напр. 'my-account' для my-account.workers.dev)"
  type        = string
}

variable "worker_subdomain" {
  description = "Поддомен, на котором будет доступен edge/ Worker (напр. 'cf-worker' → cf-worker.another.example)"
  type        = string
  default     = "cf-worker"
}

variable "environment" {
  description = "development | staging | production — см. §15 архитектурной спецификации"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "environment должен быть одним из: development, staging, production."
  }
}
