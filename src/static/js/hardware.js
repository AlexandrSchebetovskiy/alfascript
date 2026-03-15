// hardware.js — hardware info tooltip (load, position, silent background fetch)

let _hwLoaded = false;

function loadHwInfo() {
  if (_hwLoaded) return;
  fetch("/api/hw_info").then(r => r.json()).then(d => {
    if (!d.ready) return;
    _hwLoaded = true;
    _applyHwData(d);
    // If tooltip is currently visible, reposition after data fills in
    const t = $("hw-tip");
    if (t && t.style.display === "block") positionHwTip();
  });
}

function positionHwTip() {
  const wrap = $("hw-hover-wrap");
  const tip  = $("hw-tip");
  if (!wrap || !tip) return;
  const rect    = wrap.getBoundingClientRect();
  tip.style.top  = Math.max(8, rect.top - 20) + "px";
  tip.style.left = (rect.left - 340) + "px";
}

function _applyHwData(d) {
  _set("ht-cpu",  d.cpu  || "—");
  _set("ht-mb",   d.mb   || "—");
  _set("ht-ram",  d.ram  || "—");
  _set("ht-gpu",  d.gpu  || "—");
  _set("ht-bios", d.bios || "—");

  const dc = $("ht-disks"); if (!dc) return;
  dc.innerHTML = "";
  (d.disks || []).forEach(disk => {
    const row   = document.createElement("div");
    row.className = "disk-row";

    const kEl   = document.createElement("span");
    kEl.className   = "disk-k";
    kEl.textContent = disk.label;

    const infoEl = document.createElement("span");
    infoEl.className   = "disk-info";
    infoEl.textContent = disk.info;

    row.appendChild(kEl);
    row.appendChild(infoEl);

    if (disk.health) {
      const parts = [];
      const icon  = disk.health === "good" ? "✓" : disk.health === "bad" ? "✕" : "?";
      if (disk.pct   != null) parts.push(icon + " " + disk.pct + "%");
      if (disk.temp  != null) parts.push(disk.temp + "°C");
      if (disk.hours != null) parts.push(disk.hours + "ч");
      const sEl = document.createElement("span");
      sEl.className   = "disk-smart " + disk.health;
      sEl.textContent = parts.join("  ");
      row.appendChild(sEl);
    }
    dc.appendChild(row);
  });
}

// Silent background prefetch after 3 seconds
function _loadHwInfoSilent() {
  if (_hwLoaded) return;
  fetch("/api/hw_info").then(r => r.json()).then(d => {
    if (!d.ready) return;
    _hwLoaded = true;
    _applyHwData(d);
  });
}

// Wire up hover events once DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  // Move .hw-tip to <body> so backdrop-filter on #rpanel doesn't clip it
  const tip = $("hw-tip");
  if (tip) document.body.appendChild(tip);

  const wrap = $("hw-hover-wrap");
  if (wrap) {
    wrap.addEventListener("mouseenter", () => {
      loadHwInfo();
      positionHwTip();
      syncHwTipTheme();
      const t = $("hw-tip"); if (t) t.style.display = "block";
    });
    wrap.addEventListener("mouseleave", () => {
      const t = $("hw-tip"); if (t) t.style.display = "none";
    });
    wrap.addEventListener("mousemove", positionHwTip);
  }

  setTimeout(() => { if (!_hwLoaded) _loadHwInfoSilent(); }, 3000);
});
