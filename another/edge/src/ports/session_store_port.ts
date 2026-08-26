export interface SessionInfo {
  clientId: string;
  vlessUserIdHex: string;
}

/**
 * SessionStorePort — закрывает пробел, иначе оставшийся в архитектуре:
 * session_token, выданный /auth, сам по себе непрозрачен (случайные байты) —
 * без сохранённого состояния прокси-хендлер (§8.1) не смог бы отличить
 * валидный токен от произвольной строки. Здесь токен при выдаче
 * сохраняется с коротким TTL и сверяется на входе в /proxy (см.
 * handlers/proxy.ts) — если токен не найден/просрочен, WebSocket не
 * апгрейдится.
 */
export interface SessionStorePort {
  save(token: string, info: SessionInfo, ttlSeconds: number): Promise<void>;
  validate(token: string): Promise<SessionInfo | null>;
}
