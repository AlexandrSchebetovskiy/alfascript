// extras.js — toolbar extras, programs modal, program launch, OCCT warning

// ── Extras ────────────────────────────────────────────────
function runExtra(bat, name) {
  const body = bat === "null" ? { bat: null, name } : { bat, name };
  fetch("/api/extra", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => r.json()).then(d => {
    if      (d.action === "softmgr")  openPrograms("/api/soft_programs");
    else if (d.action === "portmgr")  openPrograms("/api/diag_programs");
    else if (!d.ok)                   setStatLbl(d.error || "Ошибка", "err");
    else                              setStatLbl("▶ " + name, "ok");
  });
}

// ── Programs modal ────────────────────────────────────────
let _currentProgsApi    = null;
let _currentProgsFolder = null;

function openPrograms(apiUrl) {
  _currentProgsApi = apiUrl;
  $("m-progs-body").innerHTML = '<div class="prog-hint">Загрузка...</div>';
  $("m-progs-path").textContent = "";
  openM("m-progs");
  loadPrograms(apiUrl);
}

function refreshPrograms() {
  if (!_currentProgsApi) return;
  const btn = document.querySelector("#m-progs .hdr-ibt");
  if (btn) { btn.style.animation = "spin .5s linear"; setTimeout(() => btn.style.animation = "", 500); }
  loadPrograms(_currentProgsApi);
}

function loadPrograms(apiUrl) {
  fetch(apiUrl).then(r => r.json()).then(d => {
    $("m-progs-title").textContent = d.title || "Программы";
    _currentProgsFolder = d.folder || null;

    const pathEl = $("m-progs-path");
    if (d.folder) {
      pathEl.textContent  = "📁 " + d.folder;
      pathEl.title        = "Открыть папку";
      pathEl.style.display = "";
    } else {
      pathEl.style.display = "none";
    }

    const cnt = d.programs ? d.programs.length : 0;
    $("m-progs-title").textContent = (d.title || "Программы") + (cnt ? `  (${cnt})` : "");

    const body = $("m-progs-body");
    if (!d.programs || !d.programs.length) {
      body.innerHTML = '<div class="prog-hint">Программы не найдены.<br>Добавь папки с программами в:<br><b>'
        + escH(d.folder || "multilaunch/soft") + '</b></div>';
      return;
    }

    const grid = document.createElement("div");
    grid.className = "prog-grid";

    d.programs.forEach(p => {
      const card        = document.createElement("div");
      const notInstalled = p.installed === false;
      card.className    = "prog-card" + (notInstalled ? " prog-not-installed" : "");

      const ico = document.createElement("div");
      ico.className = "prog-ico";
      if (p.icon && !notInstalled) {
        const img   = document.createElement("img");
        img.src     = "/api/icon?path=" + encodeURIComponent(p.icon);
        img.width   = 32; img.height = 32;
        img.style.cssText = "object-fit:contain;border-radius:4px";
        img.onerror = () => { ico.innerHTML = ""; ico.textContent = "📦"; };
        ico.appendChild(img);
      } else {
        ico.textContent = notInstalled ? "💾" : "📦";
      }

      const lbl = document.createElement("div");
      lbl.className  = "prog-name";
      lbl.textContent = p.name;
      if (notInstalled) {
        const hint = document.createElement("div");
        hint.style.cssText = "font-size:8px;color:var(--muted);margin-top:2px";
        hint.textContent   = "не установлена";
        lbl.appendChild(hint);
      }

      card.appendChild(ico);
      card.appendChild(lbl);

      if (notInstalled) {
        card.title = "Программа не установлена. Загрузите её через раздел обновлений.";
        card.addEventListener("click", () => { closeM("m-progs"); openAbout(); });
      } else {
        card.addEventListener("click", () => launchProg(p.path, p.name));
      }

      grid.appendChild(card);
    });

    body.innerHTML = "";
    body.appendChild(grid);
  }).catch(() => {
    $("m-progs-body").innerHTML = '<div class="prog-hint">Ошибка загрузки списка</div>';
  });
}

function openProgsFolder() {
  if (_currentProgsFolder)
    fetch("/api/open_folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: _currentProgsFolder }),
    });
}

// ── Program launch ────────────────────────────────────────
function _doLaunchProg(path, name) {
  fetch("/api/launch_program", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  }).then(r => r.json()).then(d => {
    if (d.ok) { setStatLbl("▶ " + name, "ok"); closeM("m-progs"); }
    else      setStatLbl(d.error || "Ошибка запуска", "err");
  }).catch(e => setStatLbl("Ошибка: " + e, "err"));
}

function launchProg(path, name) {
  if (name && name.toLowerCase().indexOf("occt") !== -1) {
    showOcctWarning(path, name);
    return;
  }
  _doLaunchProg(path, name);
}

// ── OCCT warning ──────────────────────────────────────────
function showOcctWarning(path, name) {
  const old = document.getElementById("m-occt-warn");
  if (old) old.remove();

  const ov = document.createElement("div");
  ov.id = "m-occt-warn";
  ov.style.cssText = [
    "position:fixed", "inset:0", "z-index:9999",
    "background:rgba(0,0,0,.72)", "display:flex",
    "align-items:center", "justify-content:center",
  ].join(";");

  ov.innerHTML = `
    <div style="background:var(--glass);border:1px solid var(--border);border-radius:14px;
      padding:32px 28px 24px;max-width:420px;width:90%;
      box-shadow:0 24px 60px rgba(0,0,0,.5);text-align:center;font-family:inherit;">
      <div style="font-size:42px;margin-bottom:14px">⚠️</div>
      <div style="font-size:15px;font-weight:800;color:var(--text);margin-bottom:16px;line-height:1.4">ВНИМАНИЕ!</div>
      <div style="font-size:13px;color:var(--dim);line-height:1.65;margin-bottom:28px">
        Перед запуском OCCT убедитесь что в пределах <strong>16 км</strong> нет Мишани.<br><br>
        В противном случае возможны <em>неконтролируемые</em> запуски OCCT с неадекватными настройками
        и фантомные проблемы с компьютером включая <strong>BSOD</strong> и краши приложений.
      </div>
      <div style="display:flex;flex-direction:column;gap:10px">
        <button id="occt-yes" style="background:var(--accent);color:#fff;border:none;border-radius:8px;
          padding:12px 16px;font-size:12px;font-weight:700;cursor:pointer;font-family:inherit;line-height:1.4">
          Иван сказал хотя бы раз в неделю запускать
        </button>
        <button id="occt-no" style="background:var(--glass2);color:var(--dim);border:1px solid var(--border);
          border-radius:8px;padding:12px 16px;font-size:12px;font-weight:700;cursor:pointer;font-family:inherit;line-height:1.4">
          Ну нахер! Я чувствую он рядом
        </button>
      </div>
    </div>`;

  document.body.appendChild(ov);
  document.getElementById("occt-yes").onclick = () => { ov.remove(); _doLaunchProg(path, name); };
  document.getElementById("occt-no").onclick  = () => ov.remove();
  ov.addEventListener("click", e => { if (e.target === ov) ov.remove(); });
}
