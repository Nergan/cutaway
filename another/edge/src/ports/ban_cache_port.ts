/**
 * BanCachePort — cache-aside поверх бан-статуса клиента (§7.3, §17
 * спецификации: ADR-2 — для бана допустима eventually-consistent KV, в
 * отличие от anti-replay nonce, где нужна строгая консистентность
 * Durable Object; короткий TTL кэша компенсирует задержку репликации KV).
 */
export interface BanCachePort {
  /**
   * Возвращает статус бана, обращаясь к fallback (обычно — UserRepositoryPort)
   * только при промахе кэша, и заполняя кэш результатом с коротким TTL.
   */
  isBanned(clientId: string, fallback: () => Promise<boolean>): Promise<boolean>;

  /** Форс-инвалидация при ручном отзыве устройства (revoke_device, §7.3). */
  invalidate(clientId: string): Promise<void>;
}
