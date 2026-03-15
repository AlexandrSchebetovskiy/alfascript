// updates.js — update checking, about modal update section, download flow

let _updData     = null;
let _dlCancelled = false;

function checkUpdate() {
  setStatLbl("Проверяю обновления...", "");
  fetch("/api/check_update");
}

function onUpdResult(d) {
  _updData = d;
  if (d.error) {
    setStatLbl("Ошибка проверки обновлений", "warn");
  } else if (d.has_update) {
    $("upd-pill").style.display = "inline-flex";
    setStatLbl("! Требуется обновление multilaunch", "warn");
  } else if (d.has_heavy_update) {
    $("upd-pill").style.display = "inline-flex";
    setStatLbl("Требуется обновление компонентов", "warn");
  } else {
    setStatLbl("Версия актуальна ✓", "ok");
  }
  if (document.getElementById("m-about").classList.contains("show")) renderAboutUpd();
}

function renderAboutUpd() {
  const d = _updData;
  if (!d) { $("ab-upd-text").textContent = "Проверка..."; return; }

  // Reset
  $("ab-comp-list").style.display  = "none";
  $("ab-comp-rows").innerHTML      = "";
  $("ab-comp-total").style.display = "none";
  $("ab-cl-wrap").style.display    = "none";
  $("ab-cl-body").textContent      = "";
  $("ab-dl-btn").style.display     = "none";

  if (d.error) {
    $("ab-upd-icon").textContent       = "⚠";
    $("ab-upd-text").textContent       = "Ошибка проверки";
    $("ab-upd-text").style.color       = "var(--yellow)";
    return;
  }

  const localStr  = d.local_date ? "Текущий: " + d.local_date : "";
  const remoteStr = d.date       ? "Новый: "   + d.date       : "";

  if (d.has_update) {
    $("ab-upd-icon").textContent = "🔔";
    $("ab-upd-text").textContent = "! Требуется обновление multilaunch";
    $("ab-upd-text").style.color = "var(--yellow)";
    $("ab-upd-ver").textContent  = [localStr, remoteStr].filter(Boolean).join("   →   ");
    $("ab-upd-ver").style.display = "block";
  } else if (d.has_heavy_update) {
    $("ab-upd-icon").textContent = "🔔";
    $("ab-upd-text").textContent = "Требуется обновление компонентов";
    $("ab-upd-text").style.color = "var(--yellow)";
    if (d.local_date) { $("ab-upd-ver").textContent = "Билд: " + d.local_date; $("ab-upd-ver").style.display = "block"; }
    else              { $("ab-upd-ver").style.display = "none"; }
  } else {
    $("ab-upd-icon").textContent = "✓";
    $("ab-upd-text").textContent = "Версия актуальна";
    $("ab-upd-text").style.color = "var(--green)";
    if (d.local_date) { $("ab-upd-ver").textContent = "Билд: " + d.local_date; $("ab-upd-ver").style.display = "block"; }
    else              { $("ab-upd-ver").style.display = "none"; }
  }

  // Component rows
  const comps = d.standard || [];
  const heavy = d.heavy    || [];
  const rows  = $("ab-comp-rows");

  function makeRow(c, isHeavy) {
    const canCheck  = c.needs_update || c.not_installed;
    const statusColor = canCheck ? "var(--yellow)" : "var(--green)";
    let verStr = c.not_installed ? "не установлен"
      : c.needs_update           ? (c.local_ver || "?") + " → " + (c.remote_ver || "?")
      :                            "✓ " + (c.remote_ver || "актуален");

    const label = (isHeavy ? "💾 " : "") + (c.display_name || c.key);
    const row   = document.createElement("label");
    row.style.cssText = "display:flex;align-items:center;gap:10px;cursor:" + (canCheck ? "pointer" : "default")
      + ";padding:5px 8px;border-radius:6px;transition:background .15s" + (canCheck ? ";background:var(--glass)" : "");
    row.dataset.key = c.key;

    const cb = document.createElement("input");
    cb.type     = "checkbox";
    cb.checked  = canCheck;
    cb.disabled = !canCheck;
    cb.dataset.key = c.key;
    cb.style.cssText = "width:15px;height:15px;accent-color:var(--accent);flex-shrink:0;cursor:" + (canCheck ? "pointer" : "default");
    cb.addEventListener("change", updateDlBtn);

    const nameSpan = document.createElement("span");
    nameSpan.style.cssText = "flex:1;color:" + statusColor + ";overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
    nameSpan.textContent   = label;

    const verSpan = document.createElement("span");
    verSpan.style.cssText = "color:var(--muted);white-space:nowrap;font-size:11px";
    verSpan.textContent   = verStr;

    row.appendChild(cb); row.appendChild(nameSpan); row.appendChild(verSpan);
    rows.appendChild(row);
  }

  comps.forEach(c => makeRow(c, false));
  if (heavy.length && comps.length) {
    const sep = document.createElement("div");
    sep.style.cssText = "border-top:1px solid var(--border);margin:6px 0";
    rows.appendChild(sep);
  }
  heavy.forEach(c => makeRow(c, true));
  if (comps.length || heavy.length) $("ab-comp-list").style.display = "block";

  updateDlBtn();

  if (d.changelog) {
    $("ab-cl-body").textContent   = d.changelog;
    $("ab-cl-wrap").style.display = "block";
  }
}

function updateDlBtn() {
  const checked = $("ab-comp-rows").querySelectorAll("input[type=checkbox]:checked:not(:disabled)");
  const btn     = $("ab-dl-btn");
  if (checked.length > 0) {
    btn.style.display = "block";
    let totalMb = 0;
    checked.forEach(cb => {
      const all  = [...(_updData?.standard || []), ...(_updData?.heavy || [])];
      const comp = all.find(c => c.key === cb.dataset.key);
      if (comp) totalMb += comp.size_mb || 0;
    });
    btn.textContent = "⬇  Скачать и установить" + (totalMb > 0 ? `  (~${totalMb.toFixed(0)} МБ)` : "");
  } else {
    btn.style.display = "none";
  }
}

function startDownload() {
  if (!_updData) return;
  const checkedKeys = Array.from(
    $("ab-comp-rows").querySelectorAll("input[type=checkbox]:checked:not(:disabled)")
  ).map(cb => cb.dataset.key);
  if (!checkedKeys.length) return;

  const allComps  = [...(_updData.standard || []), ...(_updData.heavy || [])];
  const toUpdate  = allComps.filter(c => checkedKeys.includes(c.key));
  if (!toUpdate.length) return;

  _dlCancelled = false;
  $("ab-dl-btn").style.display    = "none";
  $("ab-dl-cancel").style.display = "block";
  $("ab-dl-wrap").style.display   = "block";
  $("ab-dl-bar").style.width      = "0%";
  $("ab-dl-bar").style.background = "var(--accent)";
  $("ab-dl-text").textContent     = "Подготовка…";

  fetch("/api/download_update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ components: toUpdate.map(c => c.key), remote_comp: allComps }),
  }).then(r => r.json()).then(d => {
    if (!d.ok) {
      $("ab-dl-cancel").style.display = "none";
      $("ab-dl-bar").style.background = "var(--red)";
      $("ab-dl-text").textContent     = "⚠  " + d.error;
      $("ab-dl-btn").style.display    = "block";
      $("ab-dl-btn").textContent      = "⬇  Повторить";
    }
  }).catch(() => {
    $("ab-dl-cancel").style.display = "none";
    $("ab-dl-text").textContent     = "⚠  Ошибка соединения";
    $("ab-dl-btn").style.display    = "block";
    $("ab-dl-btn").textContent      = "⬇  Повторить";
  });
}

function cancelDownload() {
  $("ab-dl-cancel").style.display = "none";
  $("ab-dl-text").textContent     = "Отмена...";
  fetch("/api/cancel_update", { method: "POST" }).then(r => r.json()).then(d => {
    if (d.ok) {
      $("ab-dl-text").textContent  = "⏹  Скачивание отменено. Файлы удалены.";
      $("ab-dl-bar").style.width   = "0%";
      $("ab-dl-btn").style.display = "block";
      $("ab-dl-btn").textContent   = "⬇  Скачать снова";
    }
  }).catch(() => {
    $("ab-dl-text").textContent  = "⏹  Отменено.";
    $("ab-dl-btn").style.display = "block";
    $("ab-dl-btn").textContent   = "⬇  Скачать снова";
  });
}

function applyDlProgress(d) {
  if (d.cancelled) {
    _dlCancelled = true;
    $("ab-dl-cancel").style.display = "none";
    $("ab-dl-bar").style.width      = "0%";
    $("ab-dl-text").textContent     = d.text || "⏹  Отменено.";
    $("ab-dl-btn").style.display    = "block";
    $("ab-dl-btn").textContent      = "⬇  Скачать снова";
    return;
  }
  if (_dlCancelled) return;

  if (d.text)   $("ab-dl-text").textContent = d.text;
  if (d.pct != null) $("ab-dl-bar").style.width = d.pct + "%";

  if (d.error) {
    $("ab-dl-bar").style.background = "var(--red)";
    $("ab-dl-cancel").style.display = "none";
    $("ab-dl-btn").style.display    = "block";
    $("ab-dl-btn").textContent      = "⬇  Повторить";
  }
  if (d.done) {
    $("ab-dl-cancel").style.display = "none";
    $("ab-dl-bar").style.width      = "100%";
    $("ab-dl-bar").style.background = "var(--green)";
    if (d.restart === false) {
      setStatLbl("Обновление установлено ✓", "ok");
      $("ab-dl-btn").style.display = "none";
      setTimeout(() => { checkUpdate(); }, 1500);
    }
  }
}

// Legacy — pill click
function openUpdModal() { openAbout(); }
