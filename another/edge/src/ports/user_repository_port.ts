/**
 * ClientRecord — проекция одного элемента `clients[]` из документа
 * пользователя MongoDB Atlas (§10 спецификации, исправленная схема без
 * HWID/MAC — идентичность только через public_key).
 */
export interface ClientRecord {
  clientId: string;
  publicKeyHex: string;
  vlessUserIdHex: string; // 32 hex-символа = 16 байт UUID для VLESS-заголовка
  isBanned: boolean;
  quotaLimitBytes: number;
  bytesUsed: number;
}

export interface EnrollmentRecord {
  clientId: string;
  expiresAtUnixSeconds: number;
}

/**
 * UserRepositoryPort — доступ к источнику истины (Mongo через origin
 * REST-прокси, docs/adr/0005-mongo-rest-proxy.md). Worker не ходит в Atlas
 * Data API (EOL 2025-09-30) и не говорит Mongo wire-protocol.
 */
export interface UserRepositoryPort {
  findClient(clientId: string): Promise<ClientRecord | null>;

  /** Ищет активное приглашение по SHA-256(enrollment_token) — см. §7.1. */
  findEnrollmentByTokenHash(tokenHash: string): Promise<EnrollmentRecord | null>;

  /** Привязывает публичный ключ и VLESS UUID к client_id при онбординге. */
  bindDeviceIdentity(
    clientId: string,
    publicKeyHex: string,
    vlessUserIdHex: string,
    publicKeyMldsaHex?: string,
  ): Promise<void>;

  /** Помечает enrollment_token использованным (одноразовость). */
  consumeEnrollmentToken(tokenHash: string): Promise<void>;

  /** Батчевый инкремент счётчика трафика (§8.4 — вызывается редко, не на каждый пакет). */
  incrementUsage(clientId: string, bytesDelta: number): Promise<void>;
}
