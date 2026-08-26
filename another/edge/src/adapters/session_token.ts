function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * generateSessionToken — короткоживущий непрозрачный токен, возвращаемый
 * клиенту после успешного challenge-response (§7.2). В v1 это просто
 * случайные 32 байта в hex — Worker не хранит его состояние (проверка
 * авторизации на data-plane, см. handlers/proxy.ts, сверяет его как
 * bearer-секрет, переданный вместе с VLESS UUID, а не как ссылку на
 * серверную сессию). Для более строгой модели в v2 можно подписывать токен
 * HMAC'ом с истечением срока действия внутри — сейчас это осознанное
 * упрощение, соразмерное масштабу "закрытая группа".
 */
export function generateSessionToken(): string {
  return bytesToHex(crypto.getRandomValues(new Uint8Array(32)));
}
