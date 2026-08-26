/**
 * Админка фазы 3: монитор (сессии, алерты) + invite/reissue/сборка.
 * Подписи: Ed25519 (WebCrypto) + ML-DSA-65 (@noble/post-quantum).
 * SHA3-256 — @noble/hashes. Приватный ключ существует только в RAM.
 */
// Крипта по умолчанию из vendor/ (без CDN). Если Space ещё не получил эти
// файлы — синк на HF однажды упал, и панель осталась с 404 — берём те же
// версии с jsdelivr, чтобы Unlock не зависел от доставки статики.
const { ml_dsa65, sha3_256 } = await import("./vendor/noble-crypto.js").catch(async () => {
  const [hashes, pq] = await Promise.all([
    import("https://cdn.jsdelivr.net/npm/@noble/hashes@1.8.0/sha3/+esm"),
    import("https://cdn.jsdelivr.net/npm/@noble/post-quantum@0.4.1/ml-dsa.js/+esm"),
  ]);
  console.warn("another-admin: vendor/ недоступен, крипта с jsdelivr");
  return { sha3_256: hashes.sha3_256, ml_dsa65: pq.ml_dsa65 };
});

const GIGABYTE = 1024 ** 3;
const ZERO_HEAD = "00".repeat(32);

// Админка может быть смонтирована под префиксом (например /another/admin/ в
// монорепозитории cutaway). Префикс выводим из собственного URL, чтобы один и
// тот же файл работал и на корне домена, и под mount'ом.
const API_BASE = (() => {
  const match = window.location.pathname.match(/^(.*?)\/admin(?:\/|$)/);
  return match ? match[1] : "";
})();

let session = {
  keyfile: null,
  passphrase: "",
  seeds: null, // { ed: Uint8Array, pq: Uint8Array, adminId }
  lastSeq: 0,
  chainHex: ZERO_HEAD,
};

const $ = (id) => document.getElementById(id);
const errorEl = $("error");

function showError(err) {
  errorEl.textContent = err ? String(err.message || err) : "";
}

let busyDepth = 0;
let busyLabel = "";
let pollTick = false;
let lastBusyError = false;

function renderBusy() {
  const beacon = $("busy-beacon");
  const label = $("busy-label");
  const bar = $("busy-bar");
  if (!beacon || !label || !bar) return;
  if (busyDepth > 0) {
    beacon.dataset.state = "busy";
    label.textContent = busyLabel || "запрос…";
    bar.classList.add("is-on");
    document.body.classList.add("is-busy");
  } else if (lastBusyError) {
    beacon.dataset.state = "error";
    label.textContent = "ошибка";
    bar.classList.remove("is-on");
    document.body.classList.remove("is-busy");
  } else if (pollTick) {
    beacon.dataset.state = "poll";
    label.textContent = "опрос";
    bar.classList.remove("is-on");
    document.body.classList.remove("is-busy");
  } else if (session.seeds) {
    beacon.dataset.state = "idle";
    label.textContent = "готово";
    bar.classList.remove("is-on");
    document.body.classList.remove("is-busy");
  } else {
    beacon.dataset.state = "locked";
    label.textContent = "ожидание";
    bar.classList.remove("is-on");
    document.body.classList.remove("is-busy");
  }
}

function setBusyLabel(text) {
  busyLabel = text;
  renderBusy();
}

async function withBusy(label, fn) {
  busyDepth += 1;
  busyLabel = label;
  lastBusyError = false;
  showError("");
  renderBusy();
  try {
    return await fn();
  } catch (err) {
    lastBusyError = true;
    throw err;
  } finally {
    busyDepth = Math.max(0, busyDepth - 1);
    renderBusy();
  }
}

function concatBytes(parts) {
  const len = parts.reduce((s, p) => s + p.length, 0);
  const out = new Uint8Array(len);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

function hexToBytes(hex) {
  if (hex.length % 2 !== 0) throw new Error("odd hex");
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function bytesToHex(bytes) {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

// Комментарии и детали событий приходят из Mongo и попадают в innerHTML.
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);
}

function codeCopy(text) {
  const value = String(text ?? "");
  if (!value) return "";
  return `<code class="copyable" data-copy="${esc(value)}" title="копировать">${esc(value)}</code>`;
}

let toastTimer = 0;
function showToast(text) {
  const el = $("toast");
  if (!el) return;
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    el.hidden = true;
  }, 1600);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast("скопировано");
  } catch {
    showToast("не удалось скопировать");
  }
}

function showReveal(html) {
  $("last-token-body").innerHTML = html;
  $("last-token").hidden = false;
}

function hideReveal() {
  $("last-token").hidden = true;
  $("last-token-body").innerHTML = "";
}

function askConfirm({ text, okLabel = "Удалить" }) {
  return new Promise((resolve) => {
    const overlay = $("confirm-dialog");
    const ok = $("confirm-ok");
    const cancel = $("confirm-cancel");
    $("confirm-text").textContent = text;
    ok.textContent = okLabel;
    overlay.hidden = false;
    ok.focus();
    const done = (yes) => {
      overlay.hidden = true;
      ok.onclick = null;
      cancel.onclick = null;
      overlay.onclick = null;
      document.removeEventListener("keydown", onKey);
      resolve(yes);
    };
    const onKey = (e) => {
      if (e.key === "Escape") done(false);
      if (e.key === "Enter") done(true);
    };
    ok.onclick = () => done(true);
    cancel.onclick = () => done(false);
    overlay.onclick = (e) => {
      if (e.target === overlay) done(false);
    };
    document.addEventListener("keydown", onKey);
  });
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KiB", "MiB", "GiB", "TiB", "PiB"];
  let size = bytes;
  let unit = -1;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[unit]}`;
}

function emptyRow(table, columns, text) {
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = columns;
  td.className = "table-empty";
  td.textContent = text;
  tr.append(td);
  table.append(tr);
}

function u64be(n) {
  const b = new Uint8Array(8);
  new DataView(b.buffer).setBigUint64(0, BigInt(n), false);
  return b;
}

function canonicalJson(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(",")}}`;
}

function bodyHash(body) {
  const bytes = new TextEncoder().encode(canonicalJson(body));
  return sha3_256(bytes);
}

function commandMessage(seq, chainHead, hashed) {
  const prefix = new TextEncoder().encode("another-admin-v1|");
  return concatBytes([prefix, u64be(seq), chainHead, hashed]);
}

function bootstrapMessage(challenge) {
  const prefix = new TextEncoder().encode("another-admin-v1-bootstrap|");
  return concatBytes([prefix, challenge]);
}

async function deriveAesKey(passphrase, salt, iterations) {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt"],
  );
}

async function unwrapKeyfile(doc, passphrase) {
  if (doc.v !== 1 || doc.kdf !== "pbkdf2-sha256") throw new Error("unsupported keyfile");
  const salt = hexToBytes(doc.salt_hex);
  const nonce = hexToBytes(doc.nonce_hex);
  const wrapped = hexToBytes(doc.wrapped_hex);
  const key = await deriveAesKey(passphrase, salt, doc.iterations || 200000);
  const plain = new Uint8Array(await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, wrapped));
  if (plain.length !== 64) throw new Error("bad unwrapped length");
  return {
    adminId: doc.admin_id,
    ed: plain.slice(0, 32),
    pq: plain.slice(32),
  };
}

// RFC 8410 §10.3: OneAsymmetricKey для Ed25519. WebCrypto принимает приватный
// Ed25519 только как pkcs8/jwk; формат raw зарезервирован за публичным ключом.
// importKey("raw", seed, "Ed25519", false, ["sign"]) поэтому падает с
// DOMException "Cannot create a key using the specified key usages" — браузер
// видит 32 байта как public key, а public key не может иметь usage "sign".
// Обёртка: INTEGER 0 + OID 1.3.101.112 + вложенный OCTET STRING с seed.
function ed25519SeedToPkcs8(seed) {
  if (seed.length !== 32) throw new Error("ed25519 seed must be 32 bytes");
  const pkcs8 = new Uint8Array(48);
  pkcs8.set([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);
  pkcs8.set(seed, 16);
  return pkcs8;
}

async function signEd25519(seed, message) {
  const key = await crypto.subtle.importKey("pkcs8", ed25519SeedToPkcs8(seed), "Ed25519", false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("Ed25519", key, message));
}

function signMldsa(seed, message) {
  const keys = ml_dsa65.keygen(seed);
  return ml_dsa65.sign(keys.secretKey, message);
}

async function hybridSign(seeds, message) {
  const sigEd = await signEd25519(seeds.ed, message);
  const sigPq = signMldsa(seeds.pq, message);
  return { sigEd, sigPq };
}

async function api(path, init) {
  const res = await fetch(API_BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = { raw: text };
  }
  if (!res.ok) {
    const detail = json?.detail || text || res.statusText;
    throw new Error(`${res.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return json;
}

let commandQueue = Promise.resolve();

async function sendCommand(body) {
  const run = commandQueue.then(() => sendCommandNow(body));
  commandQueue = run.catch(() => {});
  return run;
}

async function sendCommandNow(body) {
  if (!session.seeds) throw new Error("сначала unlock");
  // Подпись маячка задаёт withBusy / setBusyLabel, не перетираем её именем op.
  const seq = session.lastSeq + 1;
  const chain = hexToBytes(session.chainHex);
  const hashed = bodyHash(body);
  const msg = commandMessage(seq, chain, hashed);
  const { sigEd, sigPq } = await hybridSign(session.seeds, msg);
  const json = await api("/admin/v1/command", {
    method: "POST",
    body: JSON.stringify({
      admin_id: session.seeds.adminId,
      seq,
      chain_head_prev_hex: session.chainHex,
      body,
      sig_ed_hex: bytesToHex(sigEd),
      sig_pq_hex: bytesToHex(sigPq),
    }),
  });
  session.lastSeq = json.last_seq;
  session.chainHex = json.chain_head_hex;
  // Счётчик в шапке — единственный видимый признак, что цепочка команд движется.
  $("session-status").textContent = `${session.seeds.adminId} · seq ${session.lastSeq}`;
  return json.result;
}

async function unlock() {
  showError("");
  const file = $("keyfile").files?.[0];
  const passphrase = $("passphrase").value;
  if (!file || !passphrase) throw new Error("нужны файл ключа и passphrase");
  setBusyLabel("unlock: расшифровка ключа");
  const doc = JSON.parse(await file.text());
  const seeds = await unwrapKeyfile(doc, passphrase);
  session.seeds = seeds;
  setBusyLabel("unlock: challenge");
  const ch = await api("/admin/v1/challenge");
  const challenge = hexToBytes(ch.challenge_hex);
  setBusyLabel("unlock: подпись");
  const { sigEd, sigPq } = await hybridSign(seeds, bootstrapMessage(challenge));
  setBusyLabel("unlock: bootstrap");
  const boot = await api("/admin/v1/bootstrap", {
    method: "POST",
    body: JSON.stringify({
      admin_id: seeds.adminId,
      challenge_hex: ch.challenge_hex,
      sig_ed_hex: bytesToHex(sigEd),
      sig_pq_hex: bytesToHex(sigPq),
    }),
  });
  session.lastSeq = boot.last_seq;
  session.chainHex = boot.chain_head_hex;
  $("session-status").textContent = `${seeds.adminId} · seq ${session.lastSeq}`;
  $("session-status").className = "session-status ok";
}

function statusBadge(device) {
  if (device.is_banned) return '<span class="badge badge-danger">banned</span>';
  if (device.is_enrolled) return '<span class="badge badge-ok">enrolled</span>';
  return '<span class="badge badge-idle">pending</span>';
}

function quotaCell(device) {
  const used = formatBytes(device.bytes_used);
  if (!device.quota_limit_bytes) return `${used} / ∞`;
  const share = Math.min(100, (Number(device.bytes_used) / device.quota_limit_bytes) * 100);
  const level = share >= 100 ? " is-full" : share >= 80 ? " is-warn" : "";
  return (
    `${used} / ${formatBytes(device.quota_limit_bytes)}` +
    `<div class="meter${level}"><span style="width:${share.toFixed(1)}%"></span></div>`
  );
}

function deviceBtn(label, className, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = className;
  btn.textContent = label;
  btn.onclick = async () => {
    try {
      await withBusy(label.toLowerCase(), onClick);
    } catch (e) {
      showError(e);
    }
  };
  return btn;
}

function renderDevices(devices) {
  const tb = $("devices");
  tb.innerHTML = "";
  if (!devices.length) {
    emptyRow(tb, 5, "устройств нет — выдайте первый invite");
    return;
  }
  for (const d of devices) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${codeCopy(d.client_id)}</td>
      <td class="cell-wrap">${esc(d.comment || "")}</td>
      <td>${statusBadge(d)}</td>
      <td class="cell-num">${quotaCell(d)}</td><td class="cell-actions"></td>`;
    const cell = tr.lastElementChild;
    if (d.is_banned) {
      cell.append(deviceBtn("Unban", "btn btn-sm", async () => {
        await sendCommand({ op: "unban", client_id: d.client_id });
        await refreshDevices();
      }));
    } else {
      cell.append(
        deviceBtn("Ban", "btn btn-sm btn-danger", async () => {
          await sendCommand({ op: "revoke", client_id: d.client_id });
          await refreshDevices();
        }),
        deviceBtn("Reissue", "btn btn-sm", async () => {
          const result = await sendCommand({ op: "reissue", client_id: d.client_id });
          showReveal(
            `переиздан ${codeCopy(result.client_id)} · token ${codeCopy(result.enrollment_token)}`,
          );
          await refreshDevices();
        }),
        deviceBtn("Собрать", "btn btn-sm", async () => {
          const result = await sendCommand({
            op: "build_installer",
            client_id: d.client_id,
            platforms: ["windows/amd64", "linux/amd64", "android/arm64"],
          });
          const arts = (result.artifacts || [])
            .map((a) => `${a.platform}: ${a.compiled ? a.path : a.command}`)
            .join("\n");
          showReveal(
            `сборка ${codeCopy(result.client_id)} · token ${codeCopy(result.enrollment_token)}` +
              `<pre>${esc(arts)}</pre>`,
          );
          await refreshDevices();
        }),
      );
    }
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn btn-sm btn-danger";
    remove.textContent = "Delete";
    remove.onclick = async () => {
      const ok = await askConfirm({
        text: `Удалить ${d.client_id}? Запись исчезнет из списка, доступ отзовётся.`,
        okLabel: "Удалить",
      });
      if (!ok) return;
      try {
        await withBusy("delete", async () => {
          await sendCommand({ op: "delete", client_id: d.client_id });
          await refreshDevices();
        });
      } catch (e) {
        showError(e);
      }
    };
    cell.append(remove);
    tb.append(tr);
  }
}

async function refreshDevices() {
  const result = await sendCommand({ op: "list_devices" });
  renderDevices(result.devices || []);
}

async function invite() {
  const comment = $("invite-comment").value.trim();
  const gb = Number($("invite-quota").value);
  const quota = gb > 0 ? Math.floor(gb * GIGABYTE) : 0;
  const result = await sendCommand({ op: "invite", comment, quota_limit_bytes: quota });
  showReveal(
    `client ${codeCopy(result.client_id)} · token ${codeCopy(result.enrollment_token)}` +
      ` — показан только один раз`,
  );
  await refreshDevices();
}

async function loadPing() {
  const result = await sendCommand({ op: "ping_targets_get" });
  $("ping-text").value = (result.targets || [])
    .map((t) => `${t.name} | ${t.url} | ${t.interval_s} | ${t.expect_status}`)
    .join("\n");
}

async function savePing() {
  const targets = $("ping-text")
    .value.split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, url, interval, status] = line.split("|").map((s) => s.trim());
      return {
        name,
        url,
        interval_s: Number(interval || 300),
        expect_status: Number(status || 200),
      };
    });
  await sendCommand({ op: "ping_targets_set", targets });
}

async function loadEvents() {
  const result = await sendCommand({
    op: "events",
    unacked_only: $("unacked-only").checked,
    limit: 50,
  });
  const ul = $("events");
  ul.innerHTML = "";
  let unackedAnomaly = 0;
  const events = result.events || [];
  if (!events.length) {
    const li = document.createElement("li");
    li.className = "table-empty";
    li.textContent = "событий нет";
    ul.append(li);
  }
  for (const ev of events) {
    if (!ev.acked && ev.category === "anomaly") unackedAnomaly += 1;
    const li = document.createElement("li");
    li.className = "log-row";
    if (ev.category === "anomaly") li.classList.add("is-anomaly");
    if (ev.acked) li.classList.add("is-acked");
    li.innerHTML =
      `<span class="log-ts">${esc(ev.ts || "")}</span>` +
      `<span class="log-cat">${esc(ev.category)}</span>` +
      `<span class="log-client">${codeCopy(ev.client_id || "")}</span>` +
      `<span class="log-detail">${esc(JSON.stringify(ev.detail || {}))}</span>`;
    if (!ev.acked && ev.event_id) {
      const btn = document.createElement("button");
      btn.className = "btn btn-sm";
      btn.textContent = "ack";
      btn.onclick = async () => {
        try {
          await withBusy("ack", async () => {
            await sendCommand({ op: "ack_event", event_id: ev.event_id });
            await loadEvents();
          });
        } catch (e) {
          showError(e);
        }
      };
      li.append(" ", btn);
    }
    ul.append(li);
  }
  const bell = $("bell");
  if (unackedAnomaly > 0) {
    bell.textContent = `алерты: ${unackedAnomaly}`;
    bell.className = "bell warn";
  } else {
    bell.textContent = session.seeds ? "алерты: 0" : "";
    bell.className = "bell";
  }
}

async function refreshSessions() {
  const result = await sendCommand({ op: "sessions" });
  const tb = $("sessions");
  tb.innerHTML = "";
  const sessions = result.sessions || [];
  if (!sessions.length) {
    emptyRow(tb, 6, "активных сессий нет");
    return;
  }
  for (const s of sessions) {
    const tr = document.createElement("tr");
    const ip = s.ip || s.ip_hash || "";
    tr.innerHTML = `<td>${codeCopy(s.client_id || "")}</td><td>${esc(s.node || "")}</td>
      <td>${esc(s.entrypoint || "")}</td><td>${codeCopy(ip)}</td>
      <td class="cell-num">${formatBytes(s.bytes_window || 0)}</td><td>${esc(s.last_seen || "")}</td>`;
    tb.append(tr);
  }
}

async function toggleInvestigation() {
  await sendCommand({ op: "investigation_set", enabled: $("investigation").checked });
  await refreshSessions();
}

async function loadThresholds() {
  const result = await sendCommand({ op: "alert_thresholds_get" });
  $("thresholds-text").value = JSON.stringify(result.thresholds || {}, null, 2);
}

async function saveThresholds() {
  const thresholds = JSON.parse($("thresholds-text").value || "{}");
  await sendCommand({ op: "alert_thresholds_set", thresholds });
}

async function evaluateAlerts() {
  await sendCommand({ op: "evaluate_alerts" });
  await loadEvents();
}

let pollTimer = null;
let pollTicks = 0;

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTicks = 0;
  pollTimer = setInterval(async () => {
    if (!session.seeds || busyDepth > 0 || pollTick) return;
    pollTicks += 1;
    pollTick = true;
    renderBusy();
    try {
      await refreshSessions();
      if (pollTicks % 6 === 0) {
        await sendCommand({ op: "evaluate_alerts" });
      }
      await loadEvents();
      lastBusyError = false;
    } catch {
      /* сеть/seq — покажем при ручном действии */
    } finally {
      pollTick = false;
      renderBusy();
    }
  }, 10000);
}

function bind(id, label, fn) {
  $(id).onclick = async () => {
    try {
      await withBusy(label, fn);
    } catch (e) {
      showError(e);
    }
  };
}

$("last-token-close").onclick = hideReveal;
document.addEventListener("click", (e) => {
  const hit = e.target.closest("[data-copy]");
  if (!hit) return;
  e.preventDefault();
  copyText(hit.getAttribute("data-copy") || "");
});

$("passphrase").addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  $("btn-unlock").click();
});

bind("btn-unlock", "unlock", async () => {
  await unlock();
  $("investigation").checked = false;
  setBusyLabel("загрузка: расследование");
  await sendCommand({ op: "investigation_get" }).then((r) => {
    $("investigation").checked = !!r.enabled;
  }).catch(() => {});
  setBusyLabel("загрузка: устройства");
  await refreshDevices();
  setBusyLabel("загрузка: сессии");
  await refreshSessions();
  setBusyLabel("загрузка: пингер");
  await loadPing();
  setBusyLabel("загрузка: пороги");
  await loadThresholds();
  setBusyLabel("загрузка: события");
  await loadEvents();
  startPolling();
});
bind("btn-refresh", "устройства", refreshDevices);
bind("btn-invite", "invite", invite);
bind("btn-ping-load", "пингер", loadPing);
bind("btn-ping-save", "сохранить пингер", savePing);
bind("btn-events", "события", loadEvents);
bind("btn-sessions", "сессии", refreshSessions);
bind("btn-th-load", "пороги", loadThresholds);
bind("btn-th-save", "сохранить пороги", saveThresholds);
bind("btn-eval", "детектор", evaluateAlerts);
$("investigation").onchange = async () => {
  try {
    await withBusy("расследование", toggleInvestigation);
  } catch (e) {
    showError(e);
  }
};

clearTimeout(window.__adminBoot);
document.body.classList.add("is-ready");
renderBusy();
