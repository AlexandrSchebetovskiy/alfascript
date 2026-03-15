// state.js — SSE connection, state fetch, status/progress updates

const es = new EventSource("/api/stream");
es.onmessage = e => {
  const m = JSON.parse(e.data);
  if      (m.type === "status")       applyStatus(m.data);
  else if (m.type === "test_results") renderAida(m.data);
  else if (m.type === "update")       onUpdResult(m.data);
  else if (m.type === "upd_progress") applyDlProgress(m.data);
  else if (m.type === "log_window")   { _logOpen = !!m.data.open; setLogBtnActive(_logOpen); }
  else if (m.type === "state")        applySnippet(m.data);
};

function fetchState() {
  fetch("/api/state").then(r => r.json()).then(s => {
    if (s.thresholds) _thresholds = s.thresholds;

    setChip("ch-admin", s.is_admin ? "✓ Администратор" : "✗ Нет прав", s.is_admin);
    setChip("ch-ml", s.multilaunch || "multilaunch не найден", !!s.multilaunch);

    _set("si-os", s.os_ver || "—");

    // SDI — colour by freshness
    (function () {
      const el = $("si-sdi"); if (!el) return;
      if (!s.sdi_date) { el.textContent = "нет"; el.className = "si-v bad"; return; }
      el.textContent = s.sdi_date;
      const m = s.sdi_date.match(/(\d{2})\.(\d{4})/);
      if (m) {
        const sdiMs = new Date(parseInt(m[2]), parseInt(m[1]) - 1, 1).getTime();
        const diff  = (Date.now() - sdiMs) / (1000 * 60 * 60 * 24 * 30);
        el.className = "si-v " + (diff <= 3 ? "ok" : "warn");
      } else el.className = "si-v";
    })();

    // UAC
    (function () {
      const el = $("si-uac"); if (!el) return;
      const off = (s.uac_status === "Выключен");
      el.textContent = s.uac_status || "—";
      el.className   = "si-v " + (off ? "ok" : "bad click");
      el.onclick = off ? null : function () {
        if (!confirm("Отключить уведомления UAC?\n\nПолзунок будет переведён в положение \"Никогда не уведомлять\".")) return;
        fetch("/api/disable_uac", { method: "POST" }).then(r => r.json()).then(d => {
          if (d.ok) {
            el.textContent = d.uac_status;
            const nowOff   = (d.uac_status === "Выключен");
            el.className   = "si-v " + (nowOff ? "ok" : "bad click");
            el.onclick     = null;
          } else alert("Ошибка: " + d.error);
        });
      };
    })();

    // Defender exclusions
    (function () {
      const el = $("si-def"); if (!el) return;
      const st        = s.defender_excl || "—";
      const isOk      = (st === "Добавлены");
      const isPartial = (st === "Частично");
      const isDisabled= (st === "Отключён" || st === "—");
      el.textContent = st;
      el.className   = "si-v " + (isOk ? "ok" : isPartial ? "warn" : isDisabled ? "" : "bad click");
      el.onclick = (isOk || isDisabled) ? null : function () {
        if (!s.is_admin) { alert("Для добавления исключений требуются права администратора.\nПерезапустите ALFAscript от имени администратора."); return; }
        if (!confirm("Добавить в исключения Windows Defender:\n\n• Папка флешки\n• Папка распаковки (_MEIPASS)\n\nЭто ускорит работу и устранит ложные срабатывания.")) return;
        fetch("/api/add_defender_exclusions", { method: "POST" }).then(r => r.json()).then(d => {
          if (d.ok && d.disabled) { el.textContent = "Отключён"; el.className = "si-v"; el.onclick = null; }
          else if (d.ok)          { el.textContent = d.status;   el.className = "si-v ok"; el.onclick = null; }
          else alert("Ошибка: " + d.error);
        });
      };
    })();

    // Network
    (function () {
      const el = $("si-net"); if (!el) return;
      const ok     = (s.net_ok === "Подключена");
      el.textContent = ok ? "Подключена" : "Нет сети";
      el.className   = "si-v " + (ok ? "ok" : "bad");
    })();

    // Task checkboxes
    if (s.tasks) qsa(".trow").forEach(c => {
      if (s.tasks[c.dataset.bat] !== undefined)
        c.classList.toggle("on", !!s.tasks[c.dataset.bat]);
    });

    // Active preset highlight
    if (s.active_preset) qsa(".pset").forEach(b =>
      b.classList.toggle("on", b.dataset.preset === s.active_preset)
    );

    applySnippet(s);
    if (s.test_results) renderAida(s.test_results);
  });
}

function applySnippet(s) {
  if (s.running  !== undefined) { _running = s.running; syncBtn(); }
  if (s.progress !== undefined) setProgress(s.progress, s.status_type);
  if (s.status   !== undefined) setStatLbl(s.status,    s.status_type);
}

function applyStatus(d) {
  _running = d.running; syncBtn();
  if (!d.running && d.type === "done") {
    $("rbtn").textContent = "✓  Готово";
    $("rbtn").className   = "rbtn done";
    setTimeout(syncBtn, 3000);
  }
  if (d.step     !== undefined) $("step-lbl").textContent = d.step;
  if (d.progress !== undefined) setProgress(d.progress, d.type);
  if (d.text)                   setStatLbl(d.text, d.type);
}

function setProgress(pct, type) {
  const f = $("prog-bar");
  f.style.width = pct + "%";
  f.className   = "prog-bar" + (type === "done" || type === "ok" ? " ok" : type === "warn" ? " warn" : "");
}

function setStatLbl(text, type) {
  const e = $("stat-lbl");
  e.textContent = text;
  e.className   = "stat-lbl" + (
    type === "ok"   || type === "done"  ? " ok"  :
    type === "warn"                     ? " warn" :
    type === "err"  || type === "error" ? " err"  : ""
  );
}
