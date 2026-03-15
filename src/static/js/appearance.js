// appearance.js — visual theme application, Matrix canvas, theme picker modal

let _matrixRAF = null;
let _curVstyle = _SRV_VSTYLE;
let _curVmode  = _SRV_VMODE;

const _DARK_THEMES  = new Set(["default","void","matrix","sunset","ember","neon","abyss","blood","aurora","coal"]);
const _LIGHT_THEMES = new Set(["latte","ocean","frost","meadow","sakura","cloud","peach","mint","lavender","gold"]);

function applyAppearance(vs, vm, skipSave) {
  vs = vs || "default"; vm = vm || "dark";
  _curVstyle = vs; _curVmode = vm;

  const app = document.getElementById("app");
  if (app) {
    if (vs === "default") app.removeAttribute("data-vstyle");
    else                  app.setAttribute("data-vstyle", vs);
    if (vm === "light")   app.setAttribute("data-vmode", "light");
    else                  app.removeAttribute("data-vmode");
  }

  // Background layers
  const bg = $("vstyle-bg");
  if (bg) {
    Array.from(bg.children).forEach(el => { el.style.display = "none"; el.classList.remove("light-mode"); });
    const active = bg.querySelector(".vbg-" + vs);
    if (active) {
      active.style.display = "block";
      if (vm === "light") active.classList.add("light-mode");
    }
  }

  // Matrix canvas
  const mc = $("vstyle-matrix-canvas");
  if (vs === "matrix") {
    if (mc) { mc.classList.add("vactive"); startMatrix(mc); }
  } else {
    if (mc) mc.classList.remove("vactive");
    if (_matrixRAF) { cancelAnimationFrame(_matrixRAF); _matrixRAF = null; }
  }

  if (!skipSave)
    fetch("/api/vstyle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vstyle: vs, vmode: vm }),
    });

  syncAppearanceUI(vs, vm);
  syncHwTipTheme();
}

function syncAppearanceUI(vs, vm) {
  qsa(".vstyle-item").forEach(i => i.classList.toggle("on", i.dataset.vs === vs));
  switchThemeTab(_LIGHT_THEMES.has(vs) ? "light" : "dark");
}

function switchThemeTab(tab) {
  $("ttab-dark") ?.classList.toggle("on", tab === "dark");
  $("ttab-light")?.classList.toggle("on", tab === "light");
  $("tpanel-dark") ?.classList.toggle("on", tab === "dark");
  $("tpanel-light")?.classList.toggle("on", tab === "light");
}

function setVstyleForced(vs, vm) { applyAppearance(vs, vm); }
function setVstyle(vs)           { applyAppearance(vs, _LIGHT_THEMES.has(vs) ? "light" : "dark"); }
function setVmode(vm)            { applyAppearance(_curVstyle, vm); }

function openThemeModal() { openM("m-theme"); syncAppearanceUI(_curVstyle, _curVmode); }

// ── Matrix canvas ─────────────────────────────────────────
function startMatrix(canvas) {
  if (_matrixRAF) { cancelAnimationFrame(_matrixRAF); _matrixRAF = null; }
  if (startMatrix._resizeFn) window.removeEventListener("resize", startMatrix._resizeFn);

  const ctx       = canvas.getContext("2d");
  const FONT_SIZE = 15;
  const CHARS     = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン01";

  let cols = [];

  function initCols() {
    const count = Math.floor(canvas.width / FONT_SIZE);
    cols = Array.from({ length: count }, (_, i) => cols[i] || {
      y:     Math.random() * -50,
      speed: 0.015 + Math.random() * 0.035,
      next:  Math.random() * 60,
      head:  CHARS[Math.floor(Math.random() * CHARS.length)],
      trail: Math.floor(8 + Math.random() * 20),
    });
  }

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
    ctx.fillStyle = "#000500";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    initCols();
  }

  resize();

  let frame = 0;
  function draw() {
    ctx.fillStyle = "rgba(0,5,0,0.06)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = `${FONT_SIZE}px "JetBrains Mono",monospace`;

    cols.forEach((col, i) => {
      const x = i * FONT_SIZE;
      if (col.next > 0) { col.next--; return; }
      col.y += col.speed;

      const headY = Math.floor(col.y) * FONT_SIZE;
      if (headY > 0 && headY < canvas.height) {
        if (frame % 20 === 0) col.head = CHARS[Math.floor(Math.random() * CHARS.length)];
        ctx.fillStyle = "#e0ffe0";
        ctx.fillText(col.head, x, headY);
      }

      for (let t = 1; t < col.trail; t++) {
        const ty = (Math.floor(col.y) - t) * FONT_SIZE;
        if (ty < 0) continue;
        const alpha  = 1 - t / col.trail;
        const bright = Math.floor(alpha * 200 + 20);
        ctx.fillStyle = `rgba(0,${bright},0,${(alpha * 0.9).toFixed(2)})`;
        ctx.fillText(CHARS[Math.floor((i * 137 + t * 31 + frame * 0.3) % CHARS.length)], x, ty);
      }

      if (Math.floor(col.y) * FONT_SIZE > canvas.height + col.trail * FONT_SIZE) {
        col.y     = 0;
        col.speed = 0.015 + Math.random() * 0.035;
        col.next  = Math.floor(Math.random() * 120);
        col.trail = Math.floor(8 + Math.random() * 20);
      }
    });

    frame++;
    _matrixRAF = requestAnimationFrame(draw);
  }

  startMatrix._resizeFn = resize;
  window.addEventListener("resize", resize);
  draw();
}

// ── HW tip theme sync ─────────────────────────────────────
function syncHwTipTheme() {
  const tip = $("hw-tip"); if (!tip) return;
  const app = document.getElementById("app"); if (!app) return;
  const cs  = getComputedStyle(app);
  ["--bg","--glass","--glass2","--border","--accent","--accent-g","--accent2",
   "--text","--dim","--muted","--green","--yellow","--red","--mono"].forEach(v => {
    const val = cs.getPropertyValue(v);
    if (val) tip.style.setProperty(v, val);
  });
}
