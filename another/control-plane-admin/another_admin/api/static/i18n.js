/**
 * Строки админки: ru / en. Язык — localStorage, иначе navigator.
 */

const STORAGE_KEY = "another-admin-lang";
const listeners = [];

const STRINGS = {
  ru: {
    brandTag: "control plane · monitor",
    fileLabel: "файл ключа",
    filePick: "Выбрать",
    fileNone: "не выбран",
    passphrase: "passphrase",
    unlock: "Unlock + bootstrap",
    locked: "заблокировано",
    collapseHeader: "свернуть шапку",
    expandHeader: "развернуть шапку",
    devices: "Устройства",
    comment: "комментарий",
    quotaGb: "квота, ГБ",
    invite: "Invite",
    refresh: "Обновить",
    close: "закрыть",
    copyHint: "копировать",
    colClient: "client_id",
    colComment: "комментарий",
    colStatus: "статус",
    colQuota: "трафик / квота",
    sessions: "Активные сессии",
    investigation: "режим расследования",
    pollNote: "Данные не обновляются сами. Кнопка «Обновить» в панели. Сырой IP — только в режиме расследования.",
    colNode: "узел",
    colEntrypoint: "entrypoint",
    colIp: "ip",
    colBytes: "байты окна",
    colLastSeen: "last_seen",
    events: "События и алерты",
    unackedOnly: "только неподтверждённые",
    runDetector: "Прогнать детектор",
    config: "Конфигурация",
    pinger: "Пингер",
    thresholds: "Пороги",
    pingerHint: "Одна цель на строку: name | url | interval_s | expect_status",
    thresholdsHint: "Пороги детектора аномалий, JSON.",
    load: "Загрузить",
    save: "Сохранить",
    cancel: "Отмена",
    delete: "Удалить",
    busyModules: "модули…",
    busyWait: "ожидание",
    busyRequest: "запрос…",
    busyError: "ошибка",
    busyPoll: "опрос",
    busyReady: "готово",
    busyUnlockDecrypt: "unlock: расшифровка ключа",
    busyUnlockChallenge: "unlock: challenge",
    busyUnlockSign: "unlock: подпись",
    busyUnlockBootstrap: "unlock: bootstrap",
    busyLoadInvestigation: "загрузка: расследование",
    busyLoadDevices: "загрузка: устройства",
    busyLoadSessions: "загрузка: сессии",
    busyLoadPinger: "загрузка: пингер",
    busyLoadThresholds: "загрузка: пороги",
    busyLoadEvents: "загрузка: события",
    copied: "скопировано",
    copyFailed: "не удалось скопировать",
    unlockFirst: "сначала unlock",
    needKeyAndPass: "нужны файл ключа и passphrase",
    noDevices: "устройств нет — выдайте первый invite",
    noSessions: "активных сессий нет",
    noEvents: "событий нет",
    alerts: "алерты",
    banned: "banned",
    enrolled: "enrolled",
    pending: "pending",
    expired: "истёк",
    remainDH: "{d}д {h}ч",
    remainHM: "{h}ч {m}м",
    remainM: "{m}м",
    remainS: "{s}с",
    inviteUntil: "инвайт до {until} · осталось {remain}",
    inviteTtlHours: "инвайт действует {hours} ч",
    shownOnce: "показан только один раз",
    giveCodeAtPortal: "человек открывает {url} и вставляет этот код",
    reissued: "переиздан",
    assembled: "сборка",
    deleteConfirm: "Удалить {id}? Запись исчезнет из списка, доступ отзовётся.",
    unban: "Unban",
    ban: "Ban",
    reissue: "Reissue",
    assemble: "Собрать",
    assembleConfirm: "Сборка переиздаст устройство: старый доступ пропадёт. Для нового человека — Invite и код на /another/.",
    scriptFailed: "скрипт не загрузился",
    token: "token",
    client: "client",
    locale: "ru-RU",
  },
  en: {
    brandTag: "control plane · monitor",
    fileLabel: "key file",
    filePick: "Choose",
    fileNone: "none selected",
    passphrase: "passphrase",
    unlock: "Unlock + bootstrap",
    locked: "locked",
    collapseHeader: "collapse header",
    expandHeader: "expand header",
    devices: "Devices",
    comment: "comment",
    quotaGb: "quota, GiB",
    invite: "Invite",
    refresh: "Refresh",
    close: "close",
    copyHint: "copy",
    colClient: "client_id",
    colComment: "comment",
    colStatus: "status",
    colQuota: "traffic / quota",
    sessions: "Active sessions",
    investigation: "investigation mode",
    pollNote: "Nothing auto-refreshes. Use Refresh on the panel. Raw IP only in investigation mode.",
    colNode: "node",
    colEntrypoint: "entrypoint",
    colIp: "ip",
    colBytes: "window bytes",
    colLastSeen: "last_seen",
    events: "Events and alerts",
    unackedOnly: "unacked only",
    runDetector: "Run detector",
    config: "Configuration",
    pinger: "Pinger",
    thresholds: "Thresholds",
    pingerHint: "One target per line: name | url | interval_s | expect_status",
    thresholdsHint: "Anomaly detector thresholds, JSON.",
    load: "Load",
    save: "Save",
    cancel: "Cancel",
    delete: "Delete",
    busyModules: "modules…",
    busyWait: "waiting",
    busyRequest: "request…",
    busyError: "error",
    busyPoll: "polling",
    busyReady: "ready",
    busyUnlockDecrypt: "unlock: unwrap key",
    busyUnlockChallenge: "unlock: challenge",
    busyUnlockSign: "unlock: sign",
    busyUnlockBootstrap: "unlock: bootstrap",
    busyLoadInvestigation: "loading: investigation",
    busyLoadDevices: "loading: devices",
    busyLoadSessions: "loading: sessions",
    busyLoadPinger: "loading: pinger",
    busyLoadThresholds: "loading: thresholds",
    busyLoadEvents: "loading: events",
    copied: "copied",
    copyFailed: "copy failed",
    unlockFirst: "unlock first",
    needKeyAndPass: "key file and passphrase required",
    noDevices: "no devices — issue the first invite",
    noSessions: "no active sessions",
    noEvents: "no events",
    alerts: "alerts",
    banned: "banned",
    enrolled: "enrolled",
    pending: "pending",
    expired: "expired",
    remainDH: "{d}d {h}h",
    remainHM: "{h}h {m}m",
    remainM: "{m}m",
    remainS: "{s}s",
    inviteUntil: "invite until {until} · {remain} left",
    inviteTtlHours: "invite valid for {hours} h",
    shownOnce: "shown only once",
    giveCodeAtPortal: "the person opens {url} and pastes this code",
    reissued: "reissued",
    assembled: "build",
    deleteConfirm: "Delete {id}? The row will disappear and access will be revoked.",
    unban: "Unban",
    ban: "Ban",
    reissue: "Reissue",
    assemble: "Build",
    assembleConfirm: "Build reissues the device and revokes the old one. For a new person use Invite and the code on /another/.",
    scriptFailed: "script failed to load",
    token: "token",
    client: "client",
    locale: "en-GB",
  },
};

function detectLang() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "ru" || saved === "en") return saved;
  } catch {
    /* private mode */
  }
  const nav = (navigator.language || "ru").toLowerCase();
  return nav.startsWith("en") ? "en" : "ru";
}

let lang = detectLang();

export function currentLang() {
  return lang;
}

export function t(key, vars = {}) {
  const table = STRINGS[lang] || STRINGS.ru;
  let s = table[key] ?? STRINGS.ru[key] ?? key;
  for (const [k, v] of Object.entries(vars)) {
    s = s.split(`{${k}}`).join(String(v));
  }
  return s;
}

export function applyDomI18n(root = document) {
  document.documentElement.lang = lang;
  for (const el of root.querySelectorAll("[data-i18n]")) {
    el.textContent = t(el.dataset.i18n);
  }
  for (const el of root.querySelectorAll("[data-i18n-placeholder]")) {
    el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder));
  }
  for (const el of root.querySelectorAll("[data-i18n-title]")) {
    el.setAttribute("title", t(el.dataset.i18nTitle));
  }
  for (const el of root.querySelectorAll("[data-i18n-aria]")) {
    el.setAttribute("aria-label", t(el.dataset.i18nAria));
  }
  const htmlHint = root.querySelector("[data-i18n-html]");
  if (htmlHint) {
    /* not used; keep for one-off innerHTML snippets in JS */
  }
  syncLangButtons();
  syncCollapseLabel();
}

function syncLangButtons() {
  const ru = document.getElementById("lang-ru");
  const en = document.getElementById("lang-en");
  if (ru) ru.classList.toggle("is-active", lang === "ru");
  if (en) en.classList.toggle("is-active", lang === "en");
}

export function syncCollapseLabel() {
  const btn = document.getElementById("btn-topbar-toggle");
  if (!btn) return;
  const collapsed = document.body.classList.contains("topbar-collapsed");
  btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
  btn.setAttribute("aria-label", t(collapsed ? "expandHeader" : "collapseHeader"));
  btn.title = t(collapsed ? "expandHeader" : "collapseHeader");
}

export function setLang(next) {
  if (next !== "ru" && next !== "en") return;
  lang = next;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* ignore */
  }
  applyDomI18n();
  for (const fn of listeners) fn(lang);
}

export function onLangChange(fn) {
  listeners.push(fn);
}

export function initI18n() {
  applyDomI18n();
  document.getElementById("lang-ru")?.addEventListener("click", () => setLang("ru"));
  document.getElementById("lang-en")?.addEventListener("click", () => setLang("en"));
}
