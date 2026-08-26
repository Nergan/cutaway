import type { SessionInfo, SessionStorePort } from "../ports/session_store_port.js";

/**
 * KvSessionStore — session_token → {client_id, vless_user_id} с TTL через
 * Workers KV `expirationTtl`. Eventually-consistent модель KV здесь
 * приемлема (в отличие от anti-replay nonce, см. durable_object_nonce_store.ts):
 * худший случай — легитимный клиент, подключившийся к data-plane в первые
 * секунды после выдачи токена, может попасть на PoP, ещё не увидевший
 * запись, и получить отказ, что просто вызовет retry на стороне
 * ConnectUseCase (failover, см. core/internal/app/connect_usecase.go) —
 * не проблема безопасности, а вопрос UX при худшем стечении обстоятельств.
 */
export class KvSessionStore implements SessionStorePort {
  constructor(private readonly kv: KVNamespace) {}

  private key(token: string): string {
    return `session:${token}`;
  }

  async save(token: string, info: SessionInfo, ttlSeconds: number): Promise<void> {
    await this.kv.put(this.key(token), JSON.stringify(info), { expirationTtl: ttlSeconds });
  }

  async validate(token: string): Promise<SessionInfo | null> {
    const raw = await this.kv.get(this.key(token));
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as SessionInfo;
  }
}
