const tokenEl = document.getElementById("token");
const platformEl = document.getElementById("platform");
const goEl = document.getElementById("go");
const statusEl = document.getElementById("status");
const downloadEl = document.getElementById("download");

const ERRORS = {
  "invalid or expired invite": "код неверен или просрочен",
  "builder unavailable": "сборка на сервере не настроена — напишите оператору",
  "too many requests": "слишком много попыток, подождите час",
  "unsupported platform": "эта система не поддерживается",
};

function appRoot() {
  const path = window.location.pathname;
  if (path.endsWith("/")) return path;
  const leaf = path.split("/").pop() || "";
  if (leaf.includes(".")) {
    return path.slice(0, path.lastIndexOf("/") + 1);
  }
  return `${path}/`;
}

const base = new URL(appRoot(), window.location.origin);

function setStatus(text, isError) {
  statusEl.hidden = !text;
  statusEl.textContent = text || "";
  statusEl.classList.toggle("err", Boolean(isError));
}

function api(path) {
  return new URL(path, base).toString();
}

function wait(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function humanError(detail) {
  if (typeof detail === "string" && ERRORS[detail]) return ERRORS[detail];
  if (typeof detail === "string") return detail;
  return "не удалось начать сборку";
}

async function poll(jobId, secret) {
  for (let i = 0; i < 90; i += 1) {
    const url = api(`public/v1/installer-jobs/${jobId}?secret=${encodeURIComponent(secret)}`);
    const res = await fetch(url);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(typeof body.detail === "string" ? humanError(body.detail) : "сборка не найдена");
    }
    if (body.status === "ready") {
      return body;
    }
    if (body.status === "failed") {
      throw new Error("сборка не удалась");
    }
    setStatus("Собирается… обычно 1–3 минуты. Не закрывайте вкладку.");
    await wait(4000);
  }
  throw new Error("сборка слишком долгая, попробуйте ещё раз");
}

goEl.addEventListener("click", async () => {
  const token = tokenEl.value.trim();
  if (!token) {
    setStatus("Вставьте код.", true);
    return;
  }
  goEl.disabled = true;
  downloadEl.hidden = true;
  setStatus("Отправляем код…");
  try {
    const res = await fetch(api("public/v1/redeem"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, platform: platformEl.value }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(humanError(body.detail));
    }
    const ready = await poll(body.job_id, body.download_secret);
    const href = api(
      `public/v1/installer-jobs/${body.job_id}/download?secret=${encodeURIComponent(body.download_secret)}`,
    );
    downloadEl.href = href;
    downloadEl.textContent = `Скачать ${ready.filename || "zip"}`;
    downloadEl.hidden = false;
    setStatus("Готово. Запустите another.exe из zip от имени администратора. Другие сетевые клиенты выключите.");
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    goEl.disabled = false;
  }
});
