import { t, syncCollapseLabel } from "./i18n.js";

/**
 * Раскладка админки: перетаскивание границ панелей и вкладки в «Конфигурации».
 * Ничего не знает про API и ключи — только про геометрию и localStorage.
 */

const STORAGE_KEY = "another-admin-layout";
const TOPBAR_KEY = "another-admin-topbar";

// Не даём утащить границу так, чтобы панель исчезла совсем.
const MIN_RATIO = 15;
const MAX_RATIO = 85;

const workspace = document.getElementById("workspace");

const layout = {
  col: 60,
  row: 52,
};

function clamp(value) {
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, value));
}

function apply() {
  workspace.style.setProperty("--col-left", `${layout.col}%`);
  workspace.style.setProperty("--row-top", `${layout.row}%`);
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
  } catch {
    /* приватный режим или переполненное хранилище — не повод падать */
  }
}

function restore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (Number.isFinite(saved.col)) layout.col = clamp(saved.col);
    if (Number.isFinite(saved.row)) layout.row = clamp(saved.row);
  } catch {
    /* мусор в хранилище — просто берём значения по умолчанию */
  }
}

function startDrag(splitter, event) {
  const axis = splitter.dataset.resize;
  if (!axis) return;

  event.preventDefault();
  splitter.setPointerCapture(event.pointerId);
  splitter.classList.add("is-dragging");
  document.body.classList.add("is-resizing");
  if (axis === "row") document.body.classList.add("is-resizing-row");

  const onMove = (moveEvent) => {
    const box = workspace.getBoundingClientRect();
    if (axis === "col") {
      layout.col = clamp(((moveEvent.clientX - box.left) / box.width) * 100);
    } else {
      layout.row = clamp(((moveEvent.clientY - box.top) / box.height) * 100);
    }
    apply();
  };

  const onEnd = () => {
    splitter.removeEventListener("pointermove", onMove);
    splitter.removeEventListener("pointerup", onEnd);
    splitter.removeEventListener("pointercancel", onEnd);
    splitter.classList.remove("is-dragging");
    document.body.classList.remove("is-resizing", "is-resizing-row");
    save();
  };

  splitter.addEventListener("pointermove", onMove);
  splitter.addEventListener("pointerup", onEnd);
  splitter.addEventListener("pointercancel", onEnd);
}

if (workspace) {
  restore();
  apply();

  for (const splitter of document.querySelectorAll(".splitter")) {
    splitter.addEventListener("pointerdown", (event) => startDrag(splitter, event));
    // Двойной щелчок возвращает границу на место.
    splitter.addEventListener("dblclick", () => {
      if (splitter.dataset.resize === "col") layout.col = 60;
      else layout.row = 52;
      apply();
      save();
    });
  }
}

const keyfile = document.getElementById("keyfile");
const keyfileName = document.getElementById("keyfile-name");
if (keyfile && keyfileName) {
  keyfile.addEventListener("change", () => {
    const picked = keyfile.files?.[0]?.name;
    keyfileName.textContent = picked || t("fileNone");
    keyfileName.classList.toggle("is-set", Boolean(picked));
    if (picked) keyfileName.removeAttribute("data-i18n");
    else keyfileName.setAttribute("data-i18n", "fileNone");
  });
}

function applyTopbar() {
  let collapsed = false;
  try {
    collapsed = localStorage.getItem(TOPBAR_KEY) === "collapsed";
  } catch {
    /* ignore */
  }
  document.body.classList.toggle("topbar-collapsed", collapsed);
  syncCollapseLabel();
}

function toggleTopbar() {
  const next = !document.body.classList.contains("topbar-collapsed");
  document.body.classList.toggle("topbar-collapsed", next);
  try {
    localStorage.setItem(TOPBAR_KEY, next ? "collapsed" : "expanded");
  } catch {
    /* ignore */
  }
  syncCollapseLabel();
}

applyTopbar();
document.getElementById("btn-topbar-toggle")?.addEventListener("click", toggleTopbar);

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => {
    const group = tab.closest(".panel");
    if (!group) return;
    for (const other of group.querySelectorAll(".tab")) {
      other.classList.toggle("is-active", other === tab);
    }
    for (const pane of group.querySelectorAll(".tab-pane")) {
      pane.classList.toggle("is-active", pane.dataset.pane === tab.dataset.tab);
    }
  });
}
