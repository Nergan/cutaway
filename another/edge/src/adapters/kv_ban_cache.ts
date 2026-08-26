import type { BanCachePort } from "../ports/ban_cache_port.js";

const BAN_CACHE_TTL_SECONDS = 30; // короткий TTL компенсирует eventual consistency KV, см. §7.3

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
    await this.kv.put(this.key(clientId), denied ? "1" : "0", { expirationTtl: BAN_CACHE_TTL_SECONDS });
    return denied;
  }

  async invalidate(clientId: string): Promise<void> {
    await this.kv.delete(this.key(clientId));
  }
}
