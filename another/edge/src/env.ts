/**
 * Env — биндинги Worker'а, объявленные в wrangler.toml. Секреты
 * (ANOTHER_SERVICE_SECRET) в реальном деплое задаются через
 * `wrangler secret put`, а не хранятся в wrangler.toml — см. edge/README.md.
 */
export interface Env {
  NONCE_LEDGER: DurableObjectNamespace;
  BAN_CACHE: KVNamespace;

  /** Origin control-plane API (HF/Render), без завершающего слэша. */
  MONGO_REST_PROXY_URL: string;
  ANOTHER_SERVICE_SECRET: string;

  // Список Tier1-узлов, отдаваемый клиенту при онбординге (§7.1) — в v1
  // задаётся статически через переменную окружения (JSON-строка), в v2
  // может формироваться динамически (напр. в зависимости от геолокации
  // запроса, доступной в Worker через `request.cf`).
  ORIGIN_XHTTP_URL?: string;
  NODES_JSON: string;
  /** "1" = Worker шлёт сырой IP в upsert сессии (режим расследования). */
  ANOTHER_INVESTIGATION?: string;
}
