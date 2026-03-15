// ui.js — shared helpers, modal helpers, log window, folder, about, AIDA, glitch

// ── Shared constants (injected from Jinja into index.html) ─
// const MULTILAUNCH = ...  (declared inline in index.html)
// const _SRV_VSTYLE = ...
// const _SRV_VMODE  = ...

let _running    = false;
let _thresholds = { cpu_warn:85, cpu_crit:95, gpu_warn:80, gpu_crit:90, vrm_warn:90, vrm_crit:110 };

// ── DOM helpers ───────────────────────────────────────────
const qs  = s  => document.querySelector(s);
const qsa = s  => document.querySelectorAll(s);
const $   = id => document.getElementById(id);

function _set(id, val) { const e = $(id); if (e) e.textContent = val; }
function escH(s) { return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function setChip(id, text, ok) {
  const e = $(id);
  e.innerHTML  = `<span class="chip-dot"></span>&nbsp;${escH(text)}`;
  e.className  = "chip " + (ok ? "ok" : "err");
}

// ── Modal helpers ─────────────────────────────────────────
function openM(id)  { $(id).classList.add("show");    }
function closeM(id) { $(id).classList.remove("show"); }

// ── Log window ────────────────────────────────────────────
let _logOpen = false;
let _logWin  = null;

function openLog() {
  if (window.pywebview) {
    pywebview.api.open_log();
  } else {
    if (_logOpen && _logWin && !_logWin.closed) {
      _logWin.close(); _logWin = null; _logOpen = false; setLogBtnActive(false);
    } else {
      _logWin = window.open("/log", "alfaLog", "width=480,height=680");
      if (_logWin) {
        _logOpen = true; setLogBtnActive(true);
        const _poll = setInterval(() => {
          if (_logWin && _logWin.closed) {
            clearInterval(_poll); _logWin = null; _logOpen = false; setLogBtnActive(false);
          }
        }, 500);
      }
    }
  }
}

function setLogBtnActive(on) {
  const b = $("btn-log"); if (!b) return;
  if (on) { b.style.background = "var(--accent)"; b.style.color = "#fff"; b.style.borderColor = "var(--accent)"; }
  else    { b.style.background = ""; b.style.color = ""; b.style.borderColor = ""; }
}

// ── Folder / About / Readme ───────────────────────────────
function openFolder() {
  if (MULTILAUNCH)
    fetch("/api/open_folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: MULTILAUNCH }),
    });
  else setStatLbl("multilaunch не найден", "err");
}

function openAbout() {
  openM("m-about");
  if (!_updData) checkUpdate();
  else           renderAboutUpd();
}

function openReadme() {
  fetch("/api/open_readme").then(r => r.json()).then(d => {
    if (!d.ok) setStatLbl(d.error || "README не найден", "err");
  });
}

// ── AIDA results ──────────────────────────────────────────
function tC(v, w, c) { if (!v) return ""; return v >= c ? "crit" : v >= w ? "warn" : "ok"; }

function setAV(id, text, cls) {
  const e = $(id); if (!e) return;
  e.textContent = text;
  e.className   = "av " + (cls || "");
}

function renderAida(d) {
  const { cpu_warn:CW, cpu_crit:CC, gpu_warn:GW, gpu_crit:GC, vrm_warn:VW, vrm_crit:VC } = _thresholds;
  $("aida-ph").style.display   = "none";
  $("aida-data").style.display = "block";

  setAV("a-cpu", d.cpu_max         ? d.cpu_max         + "°C" : "—", tC(d.cpu_max,         CW, CC));
  setAV("a-gpu", d.gpu_max         ? d.gpu_max         + "°C" : "—", tC(d.gpu_max,         GW, GC));
  setAV("a-hot", d.gpu_hotspot_max ? d.gpu_hotspot_max + "°C" : "—", tC(d.gpu_hotspot_max, GW, GC));
  setAV("a-vrm", d.vrm_max         ? d.vrm_max         + "°C" : "—", tC(d.vrm_max,         VW, VC));
  setAV("a-pwr", d.cpu_power_max   ? d.cpu_power_max   + " W" : "—", "");

  const thr = d.throttle;
  const te  = $("a-thr");
  te.textContent = thr ? `Да (${thr})` : "Нет";
  te.className   = "av " + (thr ? "crit" : "ok");

  $("a-dur").textContent = d.duration || "—";

  const cs = tC(d.cpu_max, CW, CC);
  const gs = tC(d.gpu_max, GW, GC);
  const w  = (thr || cs === "crit" || gs === "crit") ? "crit" : (cs === "warn" || gs === "warn") ? "warn" : "ok";
  const ve = $("a-verd");
  ve.className   = "a-verd " + w;
  ve.textContent = thr            ? `✕ Троттлинг (${thr})!`
    : w === "crit"                ? "✕ Критические темп.!"
    : w === "warn"                ? "⚠ Повышенные темп."
    :                               "✓ Температуры в норме";
}

// ── Logo glitch ───────────────────────────────────────────
const GLITCH_CHARS  = { A:["4","@","Λ","∆","Â"], L:["1","|","Ł","£"], F:["ƒ","₣","Ƒ"], A2:["4","@","Λ","∆","Â"] };
const GLITCH_COLORS = ["#ff4444","#ff9900","#00ffcc","#ff00ff","#ffffff","#ffff00"];

function glitchLoop() {
  const el   = $("logo-alfa");
  const orig = "ALFA";

  function runGlitch() {
    if (!el) return;
    const letters   = [...orig];
    let frame = 0;
    const maxFrames = random(5, 9);
    const interval  = setInterval(() => {
      frame++;
      const out = letters.map((ch, i) => {
        if (Math.random() < 0.4) {
          const set = i === 0 ? GLITCH_CHARS.A : i === 1 ? GLITCH_CHARS.L : i === 2 ? GLITCH_CHARS.F : GLITCH_CHARS.A2;
          const gc  = GLITCH_COLORS[Math.floor(Math.random() * GLITCH_COLORS.length)];
          return `<span style="color:${gc}">${set[Math.floor(Math.random() * set.length)]}</span>`;
        }
        return `<span style="color:var(--accent2)">${ch}</span>`;
      });
      el.innerHTML = out.join("");
      if (frame >= maxFrames) {
        clearInterval(interval);
        el.innerHTML = orig.split("").map(c => `<span style="color:var(--accent2)">${c}</span>`).join("");
        setTimeout(runGlitch, random(3000, 8000));
      }
    }, random(40, 80));
  }
  setTimeout(runGlitch, 2000);
}

function random(a, b) { return Math.floor(Math.random() * (b - a)) + a; }

// ── DOMContentLoaded init ─────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  fetchState();
  glitchLoop();
  applyAppearance(_SRV_VSTYLE, _SRV_VMODE, true);
});
