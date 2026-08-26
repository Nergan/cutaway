import type { BanCachePort } from "../ports/ban_cache_port.js";

// Workers KV отклоняет expirationTtl < 60 секунд (минимум платформы).
// Спецификация §7.3 хотела ~30с из-за eventual consistency — ниже 60 KV
// бросает, и POST /auth отвечает generic 500 ещё до проверки подписи.
export const BAN_CACHE_TTL_SECONDS = 60;

/**
 * KvBanCache — cache-aside поверх Workers KV. Псевдокод-источник: §7.3
 * архитектурной спецификации (`check_ban` / `revoke_device`).
 */
export class KvBanCache implements BanCachePort {
  constructor(private readonly kv: KVNamespace) {}

  private key(clientId: string): string {
    return `ban:${clientId}`;
  }

  async isBanned(clientId: string, fallback: () => Promise<boolean>): Promise<boolean> {
    const cached = await this.kv.get(this.key(clientId));
    if (cached !== null) {
      return cached === "1";
    }

    const denied = await fallback();
    try {
      await this.kv.put(this.key(clientId), denied ? "1" : "0", { expirationTtl: BAN_CACHE_TTL_SECONDS });
    } catch (err) {
      // Решение уже есть; не кэшировать лучше, чем ронять /auth.
      console.error("ban cache put failed", err);
    }
    return denied;
  }

  async invalidate(clientId: string): Promise<void> {
    await this.kv.delete(this.key(clientId));
  }
}
