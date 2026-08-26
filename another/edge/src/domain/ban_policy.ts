import type { ClientRecord } from "../ports/user_repository_port.js";

export interface AccessDecision {
  allowed: boolean;
  reason?: "banned" | "quota_exceeded";
}

/**
 * evaluateAccess — объединяет два независимых основания для отказа в
 * доступе клиенту: явный бан (`is_banned`) и исчерпанную квоту трафика
 * (§8.4 спецификации, псевдокод `auth_check`). Вынесено в чистую функцию
 * domain-слоя, чтобы решение "пускать/не пускать" не было размазано по
 * HTTP-хендлеру.
 */
export function evaluateAccess(record: ClientRecord): AccessDecision {
  if (record.isBanned) {
    return { allowed: false, reason: "banned" };
  }
  if (record.quotaLimitBytes > 0 && record.bytesUsed >= record.quotaLimitBytes) {
    return { allowed: false, reason: "quota_exceeded" };
  }
  return { allowed: true };
}
