/**
 * isWithinSlidingWindow — проверка ±30с из §7.2 спецификации, вынесена как
 * чистая функция для юнит-тестирования граничных случаев без моков и без
 * реального времени в тестах.
 */
export function isWithinSlidingWindow(
  nowUnixSeconds: number,
  timestampUnixSeconds: number,
  windowSeconds = 30,
): boolean {
  return Math.abs(nowUnixSeconds - timestampUnixSeconds) <= windowSeconds;
}
