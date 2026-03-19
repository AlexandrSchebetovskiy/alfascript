// tasks.js — task checkboxes, presets, run/stop

// ── Tasks ─────────────────────────────────────────────────
function toggleTask(c) {
  if (_running) return;
  c.classList.toggle("on");
  clearTimeout(window._st);
  window._st = setTimeout(syncTasks, 300);
}

function onDropdownChange(sel) {
  if (_running) { sel.value = sel.dataset.prev || ""; return; }
  sel.dataset.prev = sel.value;
  sel.closest(".trow").classList.toggle("on", sel.value !== "");
  clearTimeout(window._st);
  window._st = setTimeout(syncTasks, 300);
}

function syncTasks() {
  const t = {};
  qsa(".trow[data-bat]").forEach(c => {
    t[c.dataset.bat] = c.classList.contains("on");
  });
  qsa(".task-ddl").forEach(sel => {
    sel.querySelectorAll("option").forEach(opt => {
      if (opt.value) t[opt.value] = (opt.value === sel.value);
    });
  });
  fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tasks: t }),
  });
}

function selectAll() {
  qsa(".trow[data-bat]").forEach(c => {
    if (c.dataset.bat !== "99_testnotimelimit.bat") c.classList.add("on");
  });
  syncTasks();
}

function deselectAll() {
  qsa(".trow").forEach(c => c.classList.remove("on"));
  qsa(".task-ddl").forEach(sel => { sel.value = ""; });
  syncTasks();
}

// ── Presets ───────────────────────────────────────────────
function applyPreset(btn) {
  fetch("/api/preset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preset: btn.dataset.preset }),
  }).then(r => r.json()).then(d => {
    if (!d.ok) return;
    qsa(".trow[data-bat]").forEach(c =>
      c.classList.toggle("on", !!d.tasks[c.dataset.bat])
    );
    qsa(".task-ddl").forEach(sel => {
      let selected = "";
      sel.querySelectorAll("option").forEach(opt => {
        if (opt.value && d.tasks[opt.value]) selected = opt.value;
      });
      sel.value = selected;
      sel.closest(".trow").classList.toggle("on", selected !== "");
    });
    qsa(".pset").forEach(b => b.classList.remove("on"));
    btn.classList.add("on");
  });
}

// ── Run / Stop ────────────────────────────────────────────
function handleRun() {
  if (_running) {
    fetch("/api/stop", { method: "POST" });
    $("rbtn").textContent = "⏳  Отмена...";
    $("rbtn").disabled    = true;
    return;
  }
  fetch("/api/run", { method: "POST" })
    .then(r => r.json())
    .then(d => { if (!d.ok) setStatLbl(d.error || "Ошибка", "err"); });
}

function syncBtn() {
  const b = $("rbtn");
  b.disabled = false;
  if (_running) { b.textContent = "⏹  Отмена";    b.className = "rbtn stop"; }
  else          { b.textContent = "▶  Запустить"; b.className = "rbtn";      }
}
