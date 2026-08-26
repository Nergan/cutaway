/**
 * ClockPort — единственный источник "текущего времени" для domain-слоя.
 * Вынесен в порт, а не вызывается напрямую Date.now(), чтобы тесты
 * challenge_response_service могли детерминированно проверять граничные
 * случаи sliding window (§7.2 спецификации, ±30 секунд).
 */
export interface ClockPort {
  nowUnixSeconds(): number;
}
