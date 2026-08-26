output "ban_cache_kv_namespace_id" {
  description = "Вставить в edge/wrangler.toml как id для [[kv_namespaces]] binding = \"BAN_CACHE\""
  value       = cloudflare_workers_kv_namespace.ban_cache.id
}

output "worker_url" {
  description = "Публичный URL edge/ Worker — используется как ANOTHER_CONTROL_PLANE_URL"
  value       = "https://${cloudflare_record.worker_route.hostname}"
}
