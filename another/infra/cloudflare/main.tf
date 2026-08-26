# ВАЖНО: эта конфигурация НЕ прогонялась через `terraform validate`/`plan` —
# в среде разработки этого репозитория нет доступа к registry.terraform.io
# (проверено: 403 host_not_allowed) и не установлен сам terraform CLI. Тот
# же класс ограничения, что для Xcode (core/, Part 1) и реального MongoDB
# (control-plane-admin/, Part 3) — честно документируется, а не
# маскируется. Перед реальным `terraform apply`:
#   1. terraform init  (загрузит актуальную схему провайдера)
#   2. terraform validate
#   3. Свериться с текущей документацией cloudflare/cloudflare — у
#      Cloudflare Terraform-провайдера были breaking changes между
#      мажорными версиями (v3→v4→v5), особенно в части Workers-биндингов;
#      конкретные имена атрибутов ниже стоит перепроверить.

terraform {
  required_version = ">= 1.7"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.41"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# --- Workers KV: бан-кэш + session store (см. edge/wrangler.toml, §7.3) -----
# Единственный namespace на два разных префикса ключей ("ban:"/"session:") —
# осознанное упрощение, см. edge/README.md.
resource "cloudflare_workers_kv_namespace" "ban_cache" {
  account_id = var.cloudflare_account_id
  title      = "another-ban-cache-${var.environment}"
}

# --- DNS: маршрут к Worker'у --------------------------------------------------
resource "cloudflare_record" "worker_route" {
  zone_id = var.cloudflare_zone_id
  name    = var.worker_subdomain
  type    = "CNAME"
  content = "${var.worker_subdomain}.${var.cloudflare_account_subdomain}.workers.dev"
  proxied = true
  comment = "Another VPN — маршрут к edge/ Worker (см. docs/architecture.md §8.1)"
}

# --- Отключение ECH (§9.3 спецификации) --------------------------------------
# ТСПУ блокирует пакеты с ECH — для маскировки под легитимный HTTPS его
# нужно отключить на уровне зоны, а не просто "не использовать" (ECH может
# включаться Cloudflare по умолчанию независимо от клиента). Атрибут "ech"
# в cloudflare_zone_settings_override НЕ гарантированно присутствует во
# всех версиях провайдера — не проверено против реального провайдера в
# этой среде. Если apply падает на этом атрибуте, см. null_resource-fallback
# ниже — он буквально переносит curl-команду из исходного черновика
# спецификации в Terraform, минуя типизированную схему провайдера.
resource "cloudflare_zone_settings_override" "disable_ech" {
  zone_id = var.cloudflare_zone_id
  settings {
    # ech = "off"  # раскомментировать, если атрибут поддерживается версией провайдера
  }
}

# Fallback, если "ech" не поддерживается cloudflare_zone_settings_override
# в установленной версии провайдера. Раскомментировать и закомментировать
# resource выше при необходимости.
# resource "null_resource" "disable_ech_fallback" {
#   triggers = { zone_id = var.cloudflare_zone_id }
#   provisioner "local-exec" {
#     command = <<-EOT
#       curl -sf -X PATCH "https://api.cloudflare.com/client/v4/zones/${var.cloudflare_zone_id}/settings/ech" \
#         -H "Authorization: Bearer ${var.cloudflare_api_token}" \
#         -H "Content-Type: application/json" \
#         --data '{"value":"off"}'
#     EOT
#   }
# }

# --- Деплой самого кода Worker'а: НАМЕРЕННО НЕ здесь -------------------------
# `wrangler deploy` уже делает bundling+upload лучше, чем
# cloudflare_workers_script (который ожидает готовый собранный файл) —
# дублировать эту логику в Terraform избыточно. Terraform управляет ТОЛЬКО
# инфраструктурой вокруг Worker'а (KV, DNS, zone settings); сам код и его
# биндинги (Durable Object class, KV namespace id) деплоятся через
# `wrangler deploy` из edge/wrangler.toml — см. .github/workflows/edge-deploy.yml,
# где оба шага идут последовательно в одном пайплайне.
