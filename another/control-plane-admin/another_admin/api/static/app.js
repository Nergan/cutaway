/**
 * Админка фазы 3: монитор (сессии, алерты) + invite/reissue/сборка.
 * Подписи: Ed25519 (WebCrypto) + ML-DSA-65 (@noble/post-quantum).
 * SHA3-256 — @noble/hashes. Ключ только в RAM. CDN можно заменить вендором локально.
 */
import { sha3_256 } from "https://cdn.jsdelivr.net/npm/@noble/hashes@1.8.0/+esm";
import { ml_dsa65 } from "https://cdn.jsdelivr.net/npm/@noble/post-quantum@0.4.1/ml-dsa.js/+esm";

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

async function signEd25519(seed, message) {
  const key = await crypto.subtle.importKey("raw", seed, "Ed25519", false, ["sign"]);
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
  return json.result;
}

async function unlock() {
  showError("");
  const file = $("keyfile").files?.[0];
  const passphrase = $("passphrase").value;
  if (!file || !passphrase) throw new Error("нужны файл ключа и passphrase");
  const doc = JSON.parse(await file.text());
  const seeds = await unwrapKeyfile(doc, passphrase);
  session.seeds = seeds;
  const ch = await api("/admin/v1/challenge");
  const challenge = hexToBytes(ch.challenge_hex);
  const { sigEd, sigPq } = await hybridSign(seeds, bootstrapMessage(challenge));
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
  $("session-status").textContent = `ok · ${seeds.adminId} · seq ${session.lastSeq}`;
  $("session-status").className = "ok";
}

function renderDevices(devices) {
  const tb = $("devices");
  tb.innerHTML = "";
  for (const d of devices) {
    const tr = document.createElement("tr");
    const status = d.is_banned ? "BANNED" : d.is_enrolled ? "enrolled" : "pending";
    tr.innerHTML = `<td><code>${d.client_id}</code></td><td>${d.comment || ""}</td><td>${status}</td>
      <td>${d.bytes_used}/${d.quota_limit_bytes || "∞"}</td><td></td>`;
    const cell = tr.lastElementChild;
    if (!d.is_banned) {
      const ban = document.createElement("button");
      ban.textContent = "Ban";
      ban.onclick = async () => {
        try {
          await sendCommand({ op: "revoke", client_id: d.client_id });
          await refreshDevices();
        } catch (e) {
          showError(e);
        }
      };
      const reissue = document.createElement("button");
      reissue.textContent = "Reissue";
      reissue.onclick = async () => {
        try {
          const result = await sendCommand({ op: "reissue", client_id: d.client_id });
          $("last-token").innerHTML = `переиздан <code>${result.client_id}</code> token <code>${result.enrollment_token}</code>`;
          await refreshDevices();
        } catch (e) {
          showError(e);
        }
      };
      const build = document.createElement("button");
      build.textContent = "Собрать";
      build.onclick = async () => {
        try {
          const result = await sendCommand({
            op: "build_installer",
            client_id: d.client_id,
            platforms: ["windows/amd64", "linux/amd64", "android/arm64"],
          });
          const arts = (result.artifacts || [])
            .map((a) => `${a.platform}: ${a.compiled ? a.path : a.command}`)
            .join("\n");
          $("last-token").innerHTML =
            `сборка <code>${result.client_id}</code> token <code>${result.enrollment_token}</code>` +
            `<pre>${arts}</pre>`;
          await refreshDevices();
        } catch (e) {
          showError(e);
        }
      };
      cell.append(ban, reissue, build);
    }
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
  $("last-token").innerHTML = `client <code>${result.client_id}</code> token <code>${result.enrollment_token}</code> (показан один раз)`;
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
  for (const ev of result.events || []) {
    if (!ev.acked && ev.category === "anomaly") unackedAnomaly += 1;
    const li = document.createElement("li");
    li.textContent = `${ev.ts || ""} [${ev.category}] ${ev.client_id || ""} ${JSON.stringify(ev.detail || {})}`;
    if (!ev.acked && ev.event_id) {
      const btn = document.createElement("button");
      btn.textContent = "ack";
      btn.onclick = async () => {
        try {
          await sendCommand({ op: "ack_event", event_id: ev.event_id });
          await loadEvents();
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
  for (const s of result.sessions || []) {
    const tr = document.createElement("tr");
    const ip = s.ip || s.ip_hash || "";
    tr.innerHTML = `<td><code>${s.client_id || ""}</code></td><td>${s.node || ""}</td>
      <td>${s.entrypoint || ""}</td><td><code>${ip}</code></td>
      <td>${s.bytes_window || 0}</td><td>${s.last_seen || ""}</td>`;
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
    if (!session.seeds) return;
    pollTicks += 1;
    try {
      await refreshSessions();
      if (pollTicks % 6 === 0) {
        await sendCommand({ op: "evaluate_alerts" });
      }
      await loadEvents();
    } catch {
      /* сеть/seq — покажем при ручном действии */
    }
  }, 10000);
}

function bind(id, fn) {
  $(id).onclick = async () => {
    try {
      showError("");
      await fn();
    } catch (e) {
      showError(e);
    }
  };
}

bind("btn-unlock", async () => {
  await unlock();
  $("investigation").checked = false;
  await sendCommand({ op: "investigation_get" }).then((r) => {
    $("investigation").checked = !!r.enabled;
  }).catch(() => {});
  await refreshDevices();
  await refreshSessions();
  await loadPing();
  await loadThresholds();
  await loadEvents();
  startPolling();
});
bind("btn-refresh", refreshDevices);
bind("btn-invite", invite);
bind("btn-ping-load", loadPing);
bind("btn-ping-save", savePing);
bind("btn-events", loadEvents);
bind("btn-sessions", refreshSessions);
bind("btn-th-load", loadThresholds);
bind("btn-th-save", saveThresholds);
bind("btn-eval", evaluateAlerts);
$("investigation").onchange = async () => {
  try {
    showError("");
    await toggleInvestigation();
  } catch (e) {
    showError(e);
  }
};
