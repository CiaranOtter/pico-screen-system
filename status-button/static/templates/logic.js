// ════ THEME ENGINE ════
// ════ PICO CTRL THEME ENGINE ════
// Shared snippet — include at the top of every page's <script> tag.
// Reads theme from localStorage, applies CSS vars, exposes applyTheme().

window.onload = function () {
  const hostname = window.location.hostname;
  document.getElementById("ipIn").value = hostname;
  console.log("Hostname detected:", hostname);
};

(function () {
  var DEFAULTS = {
    accent: "#00ff88",
    bg: "#03030a",
  };

  function hexToRgb(h) {
    h = h.replace("#", "");
    if (h.length === 3)
      h = h
        .split("")
        .map(function (c) {
          return c + c;
        })
        .join("");
    var n = parseInt(h, 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }

  function rgbToHex(r, g, b) {
    return (
      "#" +
      [r, g, b]
        .map(function (v) {
          return Math.max(0, Math.min(255, Math.round(v)))
            .toString(16)
            .padStart(2, "0");
        })
        .join("")
    );
  }

  function lighten(hex, amt) {
    var c = hexToRgb(hex);
    return rgbToHex(
      c.r + (255 - c.r) * amt,
      c.g + (255 - c.g) * amt,
      c.b + (255 - c.b) * amt,
    );
  }

  function darken(hex, amt) {
    var c = hexToRgb(hex);
    return rgbToHex(c.r * (1 - amt), c.g * (1 - amt), c.b * (1 - amt));
  }

  function withAlpha(hex, a) {
    var c = hexToRgb(hex);
    return "rgba(" + c.r + "," + c.g + "," + c.b + "," + a + ")";
  }

  function blendBg(hex, t) {
    // blend bg toward a very dark tinted version of accent
    var c = hexToRgb(hex),
      bg = hexToRgb(hex);
    // bg panel tint: barely visible accent hue
    return rgbToHex(
      Math.round(c.r * t),
      Math.round(c.g * t),
      Math.round(c.b * t),
    );
  }

  window.applyTheme = function (accent, bg) {
    accent = accent || DEFAULTS.accent;
    bg = bg || DEFAULTS.bg;

    var bgC = hexToRgb(bg);
    var panel = rgbToHex(bgC.r + 5, bgC.g + 5, bgC.b + 16);
    var bord = rgbToHex(bgC.r + 23, bgC.g + 23, bgC.b + 44);
    var bord2 = rgbToHex(bgC.r + 37, bgC.g + 37, bgC.b + 64);
    var act = lighten(accent, 0.18);
    var dim = withAlpha(accent, 0.28);
    var text = lighten(darken(accent, 0.1), 0.3);
    // derive a muted dim hex for non-rgba uses
    var dimHex = rgbToHex(
      Math.round(hexToRgb(accent).r * 0.32),
      Math.round(hexToRgb(accent).g * 0.32),
      Math.round(hexToRgb(accent).b * 0.32),
    );

    var r = document.documentElement.style;
    r.setProperty("--accent", accent);
    r.setProperty("--bg", bg);
    r.setProperty("--panel", panel);
    r.setProperty("--border", bord);
    r.setProperty("--bord2", bord2);
    r.setProperty("--act", act);
    r.setProperty("--dim", dimHex);
    r.setProperty("--text", text);
    r.setProperty("--ga", withAlpha(accent, 0.35));
    // update the top bar gradient
    var bar = document.getElementById("themeBar");
    if (bar)
      bar.style.background =
        "linear-gradient(90deg,transparent," + accent + ",transparent)";
  };

  window.loadTheme = function () {
    var t = {};
    try {
      t = JSON.parse(localStorage.getItem("picoTheme") || "{}");
    } catch {}
    var accent = t.accent || DEFAULTS.accent;
    var bg = t.bg || DEFAULTS.bg;
    window.applyTheme(accent, bg);
    return { accent: accent, bg: bg };
  };

  window.saveTheme = function (accent, bg) {
    localStorage.setItem(
      "picoTheme",
      JSON.stringify({ accent: accent, bg: bg }),
    );
    window.applyTheme(accent, bg);
  };

  window.THEME_DEFAULTS = DEFAULTS;

  // Apply immediately on load
  window.loadTheme();
})();

// ════ AUTH ════
const _picoAuth = (function () {
  try {
    return JSON.parse(sessionStorage.getItem("pico_auth") || "null");
  } catch {
    return null;
  }
})();
if (!_picoAuth || !_picoAuth.token) {
  window.location.href = "/login";
  throw new Error("unauthenticated");
}
const _origFetch = window.fetch;
window.fetch = function (url, opts) {
  opts = Object.assign({}, opts);
  opts.headers = Object.assign(
    { Authorization: "Bearer " + _picoAuth.token },
    opts.headers || {},
  );
  return _origFetch(url, opts);
};
document.getElementById("userBadge").textContent =
  (_picoAuth.name || "").toUpperCase() +
  " · " +
  (_picoAuth.role || "").toUpperCase();
async function doLogout() {
  try {
    await _origFetch("/logout", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + _picoAuth.token,
      },
      body: "{}",
    });
  } catch {}
  sessionStorage.removeItem("pico_auth");
  window.location.href = "/login";
}
// ════ CORE ════
let curSt = "green",
  curMd = "solid",
  curDp = "plain",
  pollT = null,
  schedDays = [];
let _lcdImageMode = false,
  _pvCvsForLCD = null;
const DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
function ip() {
  return document.getElementById("ipIn").value.trim() || "192.168.1.52";
}
function lg(m, t = "inf") {
  const el = document.getElementById("log"),
    n = new Date().toTimeString().slice(0, 8);
  const r = document.createElement("div");
  r.className = "lr";
  r.innerHTML = `<span class="lt">${n}</span><span class="lm ${t}">${m}</span>`;
  el.appendChild(r);
  el.scrollTop = el.scrollHeight;
}
function switchTab(t) {
  const names = ["ctrl", "draw", "btn", "sched"];
  document
    .querySelectorAll(".tab")
    .forEach((b, i) => b.classList.toggle("on", names[i] === t));
  document
    .querySelectorAll(".tab-panel")
    .forEach((p) => p.classList.toggle("on", p.id === `tab-${t}`));
  if (t === "sched") loadJobs();
  if (t === "btn") {
    renderSeq();
    renderAddSavedGrid();
  }
  if (t === "draw") renderSavesGrid();
}
function setSt(s) {
  const d = document.getElementById("sDot"),
    tx = document.getElementById("sTxt");
  d.className = "sdot";
  if (s === "online") {
    d.classList.add("on");
    tx.textContent = "ONLINE";
  } else if (s === "error") {
    d.classList.add("err");
    tx.textContent = "ERROR";
  } else if (s === "busy") {
    d.classList.add("bsy");
    tx.textContent = "BUSY";
  } else tx.textContent = "OFFLINE";
}
function updLCD() {
  if (_lcdImageMode) return;
  const scr = document.getElementById("lcdScr"),
    cnt = document.getElementById("lcdCnt");
  scr.className = "lcd-scr";
  scr.classList.add((curMd === "ring" ? "r" : "c") + curSt[0]);
  scr.style.backgroundImage = "";
  scr.style.backgroundSize = "";
  if (curDp === "finger") cnt.innerHTML = '<div class="lcd-fng">🖕</div>';
  else if (curDp === "message") {
    const t = document.getElementById("msgI").value || "...";
    cnt.innerHTML = `<div style="font-family:Orbitron,sans-serif;font-weight:900;font-size:${t.length > 7 ? "10px" : "14px"};color:white;text-align:center;padding:6px;line-height:1.3">${t.toUpperCase()}</div>`;
  } else cnt.innerHTML = "";
}
function showLCDImage(canvas) {
  const scr = document.getElementById("lcdScr"),
    cnt = document.getElementById("lcdCnt");
  scr.className = "lcd-scr";
  scr.style.backgroundImage = `url(${canvas.toDataURL("image/png")})`;
  scr.style.backgroundSize = "cover";
  scr.style.backgroundPosition = "center";
  cnt.innerHTML = "";
  _lcdImageMode = true;
  _pvCvsForLCD = canvas;
}
function clearLCDImage() {
  const scr = document.getElementById("lcdScr");
  scr.style.backgroundImage = "";
  scr.style.backgroundSize = "";
  _lcdImageMode = false;
  _pvCvsForLCD = null;
  updLCD();
}
function syncDev(d, mode) {
  if (curSt !== d.state) selSt(d.state);
  if (curMd !== mode) selMd(mode);
  const nd = d.show_middle_finger ? "finger" : d.message ? "message" : "plain";
  if (curDp !== nd) {
    selDp(nd);
    if (nd === "message" && d.message) {
      document.getElementById("msgI").value = d.message;
      onMsg();
    }
  }
  if (d.image_active || d.gif_active) {
    if (!_lcdImageMode) {
      _lcdImageMode = true;
      if (!_pvCvsForLCD) {
        const scr = document.getElementById("lcdScr"),
          cnt = document.getElementById("lcdCnt");
        scr.className = "lcd-scr";
        scr.style.backgroundImage = "";
        cnt.innerHTML = `<div style="font-family:Orbitron,sans-serif;font-size:9px;letter-spacing:3px;color:rgba(0,255,136,.5)">${d.gif_active ? "GIF" : "IMG"}</div>`;
      }
    }
  } else {
    if (_lcdImageMode && !_pvCvsForLCD) {
      _lcdImageMode = false;
      updLCD();
    }
  }
}
function startPoll() {
  if (pollT) return;
  document.getElementById("pollBtn").classList.add("ap");
  pollT = setInterval(async () => {
    try {
      const r1 = await fetch(`http://${ip()}/state`, {
        signal: AbortSignal.timeout(1000),
      });
      const d1 = await r1.json();
      const r2 = await fetch(`http://${ip()}/config`, {
        signal: AbortSignal.timeout(1000),
      });
      const d2 = await r2.json();
      syncDev(d1, d2.mode);
      setSt("online");
    } catch {
      setSt("error");
    }
  }, 600);
  lg("Polling started", "inf");
}
function stopPoll() {
  if (!pollT) return;
  clearInterval(pollT);
  pollT = null;
  document.getElementById("pollBtn").classList.remove("ap");
  lg("Polling stopped", "inf");
}
function togglePoll() {
  pollT ? stopPoll() : startPoll();
}
async function ping() {
  lg(`Pinging ${ip()}...`, "inf");
  setSt("busy");
  try {
    const r = await fetch(`http://${ip()}/health`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    setSt("online");
    lg(
      `Online · ${(d.uptime_ms / 1000).toFixed(1)}s · RAM ${d.free_ram || "?"}B`,
      "ok",
    );
    const rs = await fetch(`http://${ip()}/state`, {
      signal: AbortSignal.timeout(2000),
    });
    const ds = await rs.json();
    const rc = await fetch(`http://${ip()}/config`, {
      signal: AbortSignal.timeout(2000),
    });
    const dc = await rc.json();
    syncDev(ds, dc.mode);
    startPoll();
  } catch (e) {
    setSt("error");
    stopPoll();
    lg(`Ping failed: ${e.message}`, "err");
  }
}
async function rebootPico() {
  if (!confirm("Reboot the Pico?")) return;
  try {
    await fetch(`http://${ip()}/reboot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
      signal: AbortSignal.timeout(3000),
    });
    setSt("error");
    stopPoll();
    lg("Pico rebooting — wait 5s", "inf");
    setTimeout(() => ping(), 6000);
  } catch (e) {
    lg(`Reboot: ${e.message}`, "inf");
  }
}
async function syncTime() {
  const st = document.getElementById("timeSt");
  const now = new Date();
  const weekday = (now.getDay() + 6) % 7;
  const body = {
    year: now.getFullYear(),
    month: now.getMonth() + 1,
    day: now.getDate(),
    weekday,
    hour: now.getHours(),
    minute: now.getMinutes(),
    second: now.getSeconds(),
  };
  try {
    const r = await fetch(`http://${ip()}/time`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error);
    st.className = "sline ok";
    st.textContent = `✓ SYNCED ${String(d.hour).padStart(2, "0")}:${String(d.minute).padStart(2, "0")}`;
    lg("✓ Clock synced", "ok");
  } catch (e) {
    st.className = "sline err";
    st.textContent = `✗ ${e.message}`;
  }
}
async function getTime() {
  const st = document.getElementById("timeSt");
  try {
    const r = await fetch(`http://${ip()}/time`, {
      signal: AbortSignal.timeout(3000),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error);
    st.className = "sline ok";
    st.textContent = `${d.year}-${String(d.month).padStart(2, "0")}-${String(d.day).padStart(2, "0")} ${String(d.hour).padStart(2, "0")}:${String(d.minute).padStart(2, "0")}:${String(d.second).padStart(2, "0")}`;
  } catch (e) {
    st.className = "sline err";
    st.textContent = `✗ ${e.message}`;
  }
}
function selSt(s) {
  curSt = s;
  document.querySelectorAll(".sbtn").forEach((b) => b.classList.remove("on"));
  document.querySelector(`.sbtn.s${s[0]}`).classList.add("on");
  updLCD();
}
function selMd(m) {
  curMd = m;
  document.querySelectorAll(".mbtn").forEach((b) => b.classList.remove("on"));
  document.querySelector(`[data-m="${m}"]`).classList.add("on");
  updLCD();
}
function selDp(d) {
  curDp = d;
  document.querySelectorAll(".dbtn").forEach((b) => b.classList.remove("on"));
  const cls = d === "plain" ? ".dp" : d === "finger" ? ".df" : ".dm";
  document.querySelector(`.dbtn${cls}`).classList.add("on");
  const mp = document.getElementById("msgP");
  if (d === "message") {
    mp.classList.add("op");
    document.getElementById("msgI").focus();
  } else mp.classList.remove("op");
  updLCD();
}
function onMsg() {
  const v = document.getElementById("msgI").value,
    cc = document.getElementById("cc");
  cc.textContent = `${v.length} / 28`;
  cc.classList.toggle("w", v.length > 20);
  updLCD();
}
async function transmit() {
  if (_picoAuth.role !== "admin") {
    lg("Admin access required", "err");
    return;
  }
  const btn = document.getElementById("txBtn"),
    lbl = document.getElementById("txLbl");
  btn.disabled = true;
  lbl.innerHTML = '<span class="spin"></span>SENDING';
  const pay = { state: curSt };
  if (curDp === "finger") pay.show_middle_finger = true;
  if (curDp === "message") {
    const m = document.getElementById("msgI").value.trim();
    if (!m) {
      lg("Message empty", "err");
      btn.disabled = false;
      lbl.textContent = "TRANSMIT";
      return;
    }
    pay.message = m;
  }
  try {
    const r1 = await fetch(`http://${ip()}/state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pay),
      signal: AbortSignal.timeout(5000),
    });
    const d1 = await r1.json();
    if (!r1.ok) throw new Error(d1.error || `HTTP ${r1.status}`);
    const r2 = await fetch(`http://${ip()}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: curMd }),
      signal: AbortSignal.timeout(5000),
    });
    if (!r2.ok) {
      const d2 = await r2.json();
      throw new Error(d2.error || `HTTP ${r2.status}`);
    }
    clearLCDImage();
    setSt("online");
    lg(`✓ ${curSt}/${curMd}/${curDp}`, "ok");
  } catch (e) {
    setSt("error");
    lg(`✗ ${e.message}`, "err");
  } finally {
    btn.disabled = false;
    lbl.textContent = "TRANSMIT";
  }
}
async function clearMedia() {
  const st = document.getElementById("mediaClearSt");
  st.className = "sline inf";
  st.textContent = "CLEARING...";
  try {
    await fetch(`http://${ip()}/image`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: "clear" }),
      signal: AbortSignal.timeout(5000),
    });
    clearLCDImage();
    _pvCvsForLCD = null;
    st.className = "sline ok";
    st.textContent = "✓ CLEARED";
    lg("Media cleared", "ok");
  } catch (e) {
    st.className = "sline err";
    st.textContent = `✗ ${e.message}`;
    lg(`✗ ${e.message}`, "err");
  }
}
let srcImg = null,
  fitMd = "fill",
  rot = 0,
  fH = false,
  fV = false,
  pvCvs = null;
function onDragOv(e) {
  e.preventDefault();
  document.getElementById("dz").classList.add("ov");
}
function onDragLv() {
  document.getElementById("dz").classList.remove("ov");
}
function onDrop(e) {
  e.preventDefault();
  onDragLv();
  const f = e.dataTransfer.files[0];
  if (f && f.type.startsWith("image/")) loadFile(f);
}
function onFSel(e) {
  const f = e.target.files[0];
  if (f) loadFile(f);
}
function loadFile(file) {
  const rd = new FileReader();
  rd.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      srcImg = img;
      rot = 0;
      fH = false;
      fV = false;
      ["brS", "coS", "saS"].forEach(
        (id) => (document.getElementById(id).value = 100),
      );
      ["brV", "coV", "saV"].forEach(
        (id) => (document.getElementById(id).textContent = 100),
      );
      const sc = document.getElementById("srcC");
      sc.width = img.width;
      sc.height = img.height;
      sc.getContext("2d").drawImage(img, 0, 0);
      document.getElementById("imgC").classList.add("sh");
      document.getElementById("dz").style.display = "none";
      rendPv();
      lg(`Image: ${img.width}x${img.height}`, "ok");
    };
    img.src = e.target.result;
  };
  rd.readAsDataURL(file);
}
function setFit(m) {
  fitMd = m;
  ["Fill", "Fit", "Stretch"].forEach((n) =>
    document
      .getElementById(`fit${n}`)
      .classList.toggle("on", n.toLowerCase() === m),
  );
  rendPv();
}
function onAdj() {
  ["br", "co", "sa"].forEach((k) => {
    document.getElementById(`${k}V`).textContent = document.getElementById(
      `${k}S`,
    ).value;
  });
  rendPv();
}
function setRot(r) {
  rot = r;
  [0, 90, 180, 270].forEach((d) =>
    document.getElementById(`rot${d}`).classList.toggle("on", d === r),
  );
  rendPv();
}
function toggleFlip(ax) {
  if (ax === "h") fH = !fH;
  else fV = !fV;
  document.getElementById("flipH").classList.toggle("on", fH);
  document.getElementById("flipV").classList.toggle("on", fV);
  rendPv();
}
function rendPv() {
  if (!srcImg) return;
  const S = 240,
    off = document.createElement("canvas");
  off.width = S;
  off.height = S;
  const cx = off.getContext("2d");
  cx.fillStyle = "#000";
  cx.fillRect(0, 0, S, S);
  cx.save();
  cx.translate(S / 2, S / 2);
  if (fH) cx.scale(-1, 1);
  if (fV) cx.scale(1, -1);
  cx.rotate((rot * Math.PI) / 180);
  const iw = srcImg.width,
    ih = srcImg.height;
  let dw, dh, dx, dy;
  if (fitMd === "stretch") {
    dw = S;
    dh = S;
    dx = -S / 2;
    dy = -S / 2;
  } else if (fitMd === "fit") {
    const sc = Math.min(S / iw, S / ih);
    dw = iw * sc;
    dh = ih * sc;
    dx = -dw / 2;
    dy = -dh / 2;
  } else {
    const sc = Math.max(S / iw, S / ih);
    dw = iw * sc;
    dh = ih * sc;
    dx = -dw / 2;
    dy = -dh / 2;
  }
  cx.filter = `brightness(${document.getElementById("brS").value}%) contrast(${document.getElementById("coS").value}%) saturate(${document.getElementById("saS").value}%)`;
  cx.drawImage(srcImg, dx, dy, dw, dh);
  cx.restore();
  pvCvs = off;
  document
    .getElementById("pvC")
    .getContext("2d")
    .drawImage(off, 0, 0, 100, 100);
}
function cvs2b64(canvas) {
  const cx = canvas.getContext("2d"),
    px = cx.getImageData(0, 0, 240, 240).data,
    buf = new Uint8Array(240 * 240 * 2);
  let i = 0;
  for (let p = 0; p < px.length; p += 4) {
    const r = px[p],
      g = px[p + 1],
      b = px[p + 2];
    const c = ((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3);
    buf[i++] = (c >> 8) & 0xff;
    buf[i++] = c & 0xff;
  }
  let s = "";
  for (let j = 0; j < buf.length; j++) s += String.fromCharCode(buf[j]);
  return btoa(s);
}
async function sendChunks(canvas, progId, fillId, stId, _attempt = 0) {
  const st = document.getElementById(stId),
    pr = document.getElementById(progId),
    fi = document.getElementById(fillId);
  st.className = "sline inf";
  st.textContent = "CLEARING RAM...";
  try {
    await fetch(`http://${ip()}/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
      signal: AbortSignal.timeout(8000),
    });
  } catch (e) {
    lg(`Clear: ${e.message}`, "inf");
  }
  await new Promise((r) => setTimeout(r, 500));
  st.textContent = "CONVERTING...";
  await new Promise((r) => setTimeout(r, 30));
  const b64 = cvs2b64(canvas),
    CH = 2000,
    tot = Math.ceil(b64.length / CH);
  pr.classList.add("sh");
  lg(`Sending ${tot} chunks`, "inf");
  try {
    for (let i = 0; i < tot; i++) {
      fi.style.width = Math.round((i / tot) * 100) + "%";
      st.textContent = `SENDING ${i + 1}/${tot}...`;
      const r = await fetch(`http://${ip()}/upload_chunk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chunk: b64.slice(i * CH, (i + 1) * CH),
          index: i,
          total: tot,
        }),
        signal: AbortSignal.timeout(15000),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    }
    fi.style.width = "100%";
    st.className = "sline ok";
    st.textContent = "✓ SENT";
    lg("✓ Sent to Pico", "ok");
    if (canvas) showLCDImage(canvas);
  } catch (e) {
    const isMemErr =
      e.message.includes("Alloc failed") ||
      e.message.includes("Not enough RAM");
    if (_attempt === 0 && isMemErr) {
      st.className = "sline err";
      st.textContent = "LOW RAM — REBOOTING PICO...";
      lg("Low RAM — rebooting", "inf");
      try {
        await fetch(`http://${ip()}/reboot`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
          signal: AbortSignal.timeout(3000),
        });
      } catch {}
      st.textContent = "WAITING FOR REBOOT (15s)...";
      await new Promise((r) => setTimeout(r, 15000));
      await sendChunks(canvas, progId, fillId, stId, 1);
    } else {
      st.className = "sline err";
      st.textContent = `✗ ${e.message}`;
      lg(`✗ ${e.message}`, "err");
    }
  } finally {
    setTimeout(() => {
      pr.classList.remove("sh");
      fi.style.width = "0%";
    }, 1500);
  }
}
async function sendUpload() {
  if (!pvCvs) {
    lg("No image", "err");
    return;
  }
  await sendChunks(pvCvs, "upProg", "upFill", "upSt");
}
function clearUpload() {
  srcImg = null;
  pvCvs = null;
  document.getElementById("imgC").classList.remove("sh");
  document.getElementById("dz").style.display = "block";
  document.getElementById("fIn").value = "";
  document.getElementById("upSt").textContent = "";
  clearLCDImage();
}
const DC = document.getElementById("drawCanvas"),
  DX = DC.getContext("2d");
let dTool = "pen",
  dCol = "#ffffff",
  dSz = 4,
  drawing = false,
  lastX = 0,
  lastY = 0,
  snapSt = null,
  hist = [],
  showRing = true,
  bgC = "#000000";
DX.fillStyle = "#000000";
DX.fillRect(0, 0, 240, 240);
hist.push(DX.getImageData(0, 0, 240, 240));
function savHist() {
  hist.push(DX.getImageData(0, 0, 240, 240));
  if (hist.length > 30) hist.shift();
}
function undoDr() {
  if (hist.length > 1) {
    hist.pop();
    DX.putImageData(hist[hist.length - 1], 0, 0);
  }
}
function clearDr() {
  DX.fillStyle = bgC;
  DX.fillRect(0, 0, 240, 240);
  savHist();
}
function fillBg() {
  bgC = document.getElementById("bgCol").value;
  clearDr();
}
function toggleRing() {
  showRing = !showRing;
  const b = document.getElementById("rgBtn");
  b.textContent = showRing ? "◯ ON" : "◯ OFF";
  b.classList.toggle("on", showRing);
  document.getElementById("ringOv").style.display = showRing ? "block" : "none";
}
function setTool(t) {
  dTool = t;
  document
    .querySelectorAll(".dtrow .smbtn")
    .forEach((b) => b.classList.remove("on"));
  const tid = "t" + t.charAt(0).toUpperCase() + t.slice(1);
  const el = document.getElementById(tid);
  if (el) el.classList.add("on");
  document.getElementById("txtPanel").style.display =
    t === "text" ? "block" : "none";
  DC.style.cursor =
    t === "eyedrop"
      ? "crosshair"
      : t === "fill"
        ? "cell"
        : t === "text"
          ? "text"
          : "crosshair";
}
function setCol(c) {
  dCol = c;
  document
    .querySelectorAll(".csw")
    .forEach((s) => s.classList.toggle("on", s.dataset.c === c));
  document.getElementById("custCol").value = c;
}
function onSz() {
  dSz = parseInt(document.getElementById("szS").value);
  document.getElementById("szV").textContent = dSz;
  const d = document.getElementById("szDot"),
    sz = Math.min(dSz, 24);
  d.style.width = sz + "px";
  d.style.height = sz + "px";
}
function getPos(e) {
  const r = DC.getBoundingClientRect(),
    sx = 240 / r.width,
    sy = 240 / r.height;
  const cx = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
  const cy = (e.touches ? e.touches[0].clientY : e.clientY) - r.top;
  return [cx * sx, cy * sy];
}
function floodFill(sx, sy, fc) {
  sx = Math.floor(sx);
  sy = Math.floor(sy);
  const id = DX.getImageData(0, 0, 240, 240),
    d = id.data,
    idx = (sy * 240 + sx) * 4;
  const tr = d[idx],
    tg = d[idx + 1],
    tb = d[idx + 2];
  const fr = parseInt(fc.slice(1, 3), 16),
    fg = parseInt(fc.slice(3, 5), 16),
    fb2 = parseInt(fc.slice(5, 7), 16);
  if (tr === fr && tg === fg && tb === fb2) return;
  const st = [[sx, sy]];
  while (st.length) {
    const [x, y] = st.pop();
    if (x < 0 || x >= 240 || y < 0 || y >= 240) continue;
    const i = (y * 240 + x) * 4;
    if (d[i] !== tr || d[i + 1] !== tg || d[i + 2] !== tb) continue;
    d[i] = fr;
    d[i + 1] = fg;
    d[i + 2] = fb2;
    d[i + 3] = 255;
    st.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
  }
  DX.putImageData(id, 0, 0);
}
function pickCol(x, y) {
  const px = DX.getImageData(Math.floor(x), Math.floor(y), 1, 1).data;
  const h =
    "#" +
    [px[0], px[1], px[2]].map((v) => v.toString(16).padStart(2, "0")).join("");
  setCol(h);
  document.getElementById("custCol").value = h;
  setTool("pen");
}
function stampTxt(x, y) {
  const t = document.getElementById("drawTxt").value;
  if (!t) return;
  DX.save();
  DX.fillStyle = dCol;
  DX.font = `bold ${dSz * 4 + 8}px Orbitron,monospace`;
  DX.textAlign = "left";
  DX.fillText(t, x, y);
  DX.restore();
  savHist();
}
function onDrStart(e) {
  e.preventDefault();
  drawing = true;
  const [x, y] = getPos(e);
  lastX = x;
  lastY = y;
  if (dTool === "fill") {
    floodFill(x, y, dCol);
    savHist();
    return;
  }
  if (dTool === "eyedrop") {
    pickCol(x, y);
    return;
  }
  if (dTool === "text") {
    stampTxt(x, y);
    return;
  }
  if (["line", "rect", "circle"].includes(dTool)) {
    snapSt = [x, y];
    return;
  }
  DX.beginPath();
  DX.arc(x, y, dSz / 2, 0, Math.PI * 2);
  DX.fillStyle = dTool === "eraser" ? bgC : dCol;
  DX.fill();
}
function onDrMove(e) {
  e.preventDefault();
  if (!drawing) return;
  const [x, y] = getPos(e);
  if (dTool === "pen" || dTool === "eraser") {
    DX.beginPath();
    DX.moveTo(lastX, lastY);
    DX.lineTo(x, y);
    DX.strokeStyle = dTool === "eraser" ? bgC : dCol;
    DX.lineWidth = dSz;
    DX.lineCap = "round";
    DX.lineJoin = "round";
    DX.stroke();
    lastX = x;
    lastY = y;
  } else if (snapSt && ["line", "rect", "circle"].includes(dTool)) {
    DX.putImageData(hist[hist.length - 1], 0, 0);
    DX.strokeStyle = dCol;
    DX.lineWidth = dSz;
    DX.lineCap = "round";
    const [sx, sy] = snapSt;
    if (dTool === "line") {
      DX.beginPath();
      DX.moveTo(sx, sy);
      DX.lineTo(x, y);
      DX.stroke();
    } else if (dTool === "rect") {
      DX.strokeRect(sx, sy, x - sx, y - sy);
    } else {
      const rx = Math.abs(x - sx) / 2,
        ry = Math.abs(y - sy) / 2,
        cx = (sx + x) / 2,
        cy = (sy + y) / 2;
      DX.beginPath();
      DX.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      DX.stroke();
    }
  }
}
function onDrEnd() {
  if (!drawing) return;
  drawing = false;
  snapSt = null;
  savHist();
}
DC.addEventListener("mousedown", onDrStart);
DC.addEventListener("mousemove", onDrMove);
DC.addEventListener("mouseup", onDrEnd);
DC.addEventListener("mouseleave", onDrEnd);
DC.addEventListener("touchstart", onDrStart, { passive: false });
DC.addEventListener("touchmove", onDrMove, { passive: false });
DC.addEventListener("touchend", onDrEnd);
async function sendDraw() {
  await sendChunks(DC, "drProg", "drFill", "drSt");
}
function getSaves() {
  try {
    return JSON.parse(localStorage.getItem("picoDrawings") || "[]");
  } catch {
    return [];
  }
}
function putSaves(arr) {
  localStorage.setItem("picoDrawings", JSON.stringify(arr));
}
function openSaveDialog() {
  document.getElementById("saveNameI").value = "";
  document.getElementById("saveDialog").style.display = "block";
  document.getElementById("saveNameI").focus();
}
function closeSaveDialog() {
  document.getElementById("saveDialog").style.display = "none";
}
function confirmSave() {
  const name =
    document.getElementById("saveNameI").value.trim() ||
    "DRAWING " + Date.now();
  const dataUrl = DC.toDataURL("image/png");
  const saves = getSaves();
  saves.push({ id: Date.now(), name: name.toUpperCase(), dataUrl });
  putSaves(saves);
  closeSaveDialog();
  renderSavesGrid();
  lg(`Saved: ${name}`, "ok");
}
function openPhotoSaveDialog() {
  if (!pvCvs) {
    lg("No image loaded", "err");
    return;
  }
  document.getElementById("photoSaveNameI").value = "";
  document.getElementById("photoSaveDialog").style.display = "block";
  document.getElementById("photoSaveNameI").focus();
}
function closePhotoSaveDialog() {
  document.getElementById("photoSaveDialog").style.display = "none";
}
function confirmPhotoSave() {
  const name =
    document.getElementById("photoSaveNameI").value.trim() ||
    "PHOTO " + Date.now();
  const dataUrl = pvCvs.toDataURL("image/png");
  const saves = getSaves();
  saves.push({ id: Date.now(), name: name.toUpperCase(), dataUrl });
  putSaves(saves);
  closePhotoSaveDialog();
  renderSavesGrid();
  renderAddSavedGrid();
  lg(`Saved: ${name}`, "ok");
}
function deleteSave(id) {
  const saves = getSaves().filter((s) => s.id !== id);
  putSaves(saves);
  renderSavesGrid();
  renderAddSavedGrid();
  btnSequence = btnSequence.filter(
    (s) => !(s.type === "saved" && s.saveId === id),
  );
  renderSeq();
}
function loadSaveToCanvas(save) {
  const img = new Image();
  img.onload = () => {
    DX.clearRect(0, 0, 240, 240);
    DX.drawImage(img, 0, 0, 240, 240);
    savHist();
    lg(`Loaded: ${save.name}`, "ok");
  };
  img.src = save.dataUrl;
}
function renderSavesGrid() {
  const saves = getSaves(),
    grid = document.getElementById("savesGrid");
  if (!saves.length) {
    grid.innerHTML =
      '<div class="no-saves" style="grid-column:span 3">NO SAVED DRAWINGS</div>';
    return;
  }
  grid.innerHTML = saves
    .map(
      (s) =>
        `<div class="save-card" onclick="loadSaveToCanvas(getSaves().find(x=>x.id===${s.id}))"><img src="${s.dataUrl}"/><div class="save-name">${s.name}</div><button class="save-del" onclick="event.stopPropagation();deleteSave(${s.id})">✕</button></div>`,
    )
    .join("");
}
function renderAddSavedGrid() {
  const saves = getSaves(),
    grid = document.getElementById("addSavedGrid");
  if (!saves.length) {
    grid.innerHTML =
      '<div class="no-saves" style="grid-column:span 3">NO SAVED DRAWINGS</div>';
    return;
  }
  grid.innerHTML = saves
    .map(
      (s) =>
        `<div class="save-card" id="addSave_${s.id}" onclick="selectAddSave(${s.id})"><img src="${s.dataUrl}"/><div class="save-name">${s.name}</div></div>`,
    )
    .join("");
}
let selectedAddSave = null;
function selectAddSave(id) {
  selectedAddSave = id;
  document
    .querySelectorAll('[id^="addSave_"]')
    .forEach((el) => el.classList.remove("selected"));
  document.getElementById(`addSave_${id}`).classList.add("selected");
}
let btnSequence = [];
try {
  btnSequence = JSON.parse(localStorage.getItem("picoBtnSeq") || "[]");
} catch {}
let addScreenType = "colour",
  addColour = "red",
  addMode = "solid";
function setScreenType(t) {
  addScreenType = t;
  document.querySelectorAll(".stbtn").forEach((b) => b.classList.remove("on"));
  document
    .getElementById(`st${t.charAt(0).toUpperCase() + t.slice(1)}`)
    .classList.add("on");
  document.getElementById("addColourPanel").style.display =
    t === "colour" ? "block" : "none";
  document.getElementById("addMsgPanel").style.display =
    t === "message" ? "block" : "none";
  document.getElementById("addSavedPanel").style.display =
    t === "saved" ? "block" : "none";
}
function setAddCol(c) {
  addColour = c;
  document
    .querySelectorAll(".cpick")
    .forEach((el) => el.classList.toggle("on", el.dataset.col === c));
}
function setAddMode(m) {
  addMode = m;
  ["Solid", "Ring", "Flash"].forEach((n) =>
    document
      .getElementById(`addMd${n}`)
      .classList.toggle("on", n.toLowerCase() === m),
  );
}
function addToSeq() {
  const st = document.getElementById("addSt");
  let item = {};
  if (addScreenType === "colour") {
    item = {
      type: "colour",
      state: addColour,
      mode: addMode,
      name: `${addColour.toUpperCase()} ${addMode.toUpperCase()}`,
    };
  } else if (addScreenType === "finger") {
    item = {
      type: "finger",
      state: "red",
      mode: "solid",
      name: "MIDDLE FINGER",
    };
  } else if (addScreenType === "message") {
    const msg = document.getElementById("addMsgTxt").value.trim();
    if (!msg) {
      st.className = "sline err";
      st.textContent = "Message required";
      return;
    }
    item = {
      type: "message",
      state: addColour,
      mode: "solid",
      message: msg,
      name: `MSG: ${msg.toUpperCase()}`,
    };
  } else if (addScreenType === "saved") {
    if (!selectedAddSave) {
      st.className = "sline err";
      st.textContent = "Select a drawing";
      return;
    }
    const save = getSaves().find((s) => s.id === selectedAddSave);
    if (!save) {
      st.className = "sline err";
      st.textContent = "Drawing not found";
      return;
    }
    item = {
      type: "saved",
      saveId: selectedAddSave,
      name: save.name,
      dataUrl: save.dataUrl,
    };
  }
  item.id = Date.now();
  btnSequence.push(item);
  localStorage.setItem("picoBtnSeq", JSON.stringify(btnSequence));
  renderSeq();
  st.className = "sline ok";
  st.textContent = `✓ Added: ${item.name}`;
  lg(`Seq: added ${item.name}`, "ok");
}
function removeFromSeq(id) {
  btnSequence = btnSequence.filter((s) => s.id !== id);
  localStorage.setItem("picoBtnSeq", JSON.stringify(btnSequence));
  renderSeq();
}
function clearSeq() {
  btnSequence = [];
  localStorage.removeItem("picoBtnSeq");
  renderSeq();
  document.getElementById("seqSt").textContent = "";
}
function renderSeq() {
  const el = document.getElementById("btnSeq");
  if (!btnSequence.length) {
    el.innerHTML = '<div class="no-seq">NO SCREENS IN SEQUENCE</div>';
    return;
  }
  el.innerHTML = btnSequence
    .map((s, i) => {
      const preview =
        s.type === "saved"
          ? `<img src="${s.dataUrl}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;border:1px solid var(--bord2);"/>`
          : `<div class="seq-preview" style="background:${s.state === "red" ? "#bb0010" : s.state === "green" ? "#005522" : "#550077"}"></div>`;
      return `<div class="seq-item" draggable="true" ondragstart="onSeqDragStart(event,${i})" ondragover="onSeqDragOver(event)" ondrop="onSeqDrop(event,${i})"><span class="seq-drag">⠿</span>${preview}<div class="seq-info"><div class="seq-label">${i + 1}. ${s.name}</div><div class="seq-sub">${s.type.toUpperCase()}${s.message ? " · " + s.message.toUpperCase() : ""}</div></div><button class="seq-del" onclick="removeFromSeq(${s.id})">✕</button></div>`;
    })
    .join("");
}
let dragIdx = null;
function onSeqDragStart(e, i) {
  dragIdx = i;
  e.dataTransfer.effectAllowed = "move";
}
function onSeqDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
}
function onSeqDrop(e, targetIdx) {
  e.preventDefault();
  if (dragIdx === null || dragIdx === targetIdx) return;
  const item = btnSequence.splice(dragIdx, 1)[0];
  btnSequence.splice(targetIdx, 0, item);
  dragIdx = null;
  localStorage.setItem("picoBtnSeq", JSON.stringify(btnSequence));
  renderSeq();
}
async function pushSeqToPico() {
  const st = document.getElementById("seqSt");
  if (!btnSequence.length) {
    st.className = "sline err";
    st.textContent = "Sequence is empty";
    return;
  }
  st.className = "sline inf";
  st.textContent = "APPLYING...";
  lg(`Applying sequence (${btnSequence.length} items)`, "inf");
  try {
    let uploadSlot = 0;
    const withSlots = btnSequence.map((s) => ({
      ...s,
      _slot: s.type === "saved" ? uploadSlot++ : null,
    }));
    for (const s of withSlots) {
      if (s.type !== "saved" || !s.dataUrl) continue;
      st.textContent = `UPLOADING TO SLOT ${s._slot}...`;
      const canvas = document.createElement("canvas");
      canvas.width = 240;
      canvas.height = 240;
      const ctx = canvas.getContext("2d");
      await new Promise((res) => {
        const img = new Image();
        img.onload = () => {
          ctx.drawImage(img, 0, 0, 240, 240);
          res();
        };
        img.src = s.dataUrl;
      });
      try {
        await fetch(`http://${ip()}/clear`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({}),
          signal: AbortSignal.timeout(5000),
        });
      } catch (e) {
        lg(`Clear: ${e.message}`, "inf");
      }
      await new Promise((r) => setTimeout(r, 300));
      const b64 = cvs2b64(canvas),
        CH = 2000,
        tot = Math.ceil(b64.length / CH);
      for (let c = 0; c < tot; c++) {
        st.textContent = `SLOT ${s._slot} · ${c + 1}/${tot}`;
        const r = await fetch(`http://${ip()}/upload_chunk`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chunk: b64.slice(c * CH, (c + 1) * CH),
            index: c,
            total: tot,
            slot: s._slot,
          }),
          signal: AbortSignal.timeout(15000),
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
        if (c === tot - 1)
          lg(`✓ Slot ${s._slot} (${d.free_ram || "?"}B free)`, "ok");
      }
    }
    st.textContent = "SENDING SEQUENCE...";
    let sc2 = 0;
    const seqMeta = btnSequence.map((s) => ({
      index: s.type === "saved" ? sc2++ : 0,
      type: s.type,
      state: s.state || "green",
      mode: s.mode || "solid",
      message: s.message || null,
      hasSaved: s.type === "saved",
    }));
    const r = await fetch(`http://${ip()}/button_sequence`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sequence: seqMeta }),
      signal: AbortSignal.timeout(5000),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    st.className = "sline ok";
    st.textContent = `✓ ${d.count} SCREENS APPLIED`;
    lg("✓ Button sequence applied", "ok");
  } catch (e) {
    st.className = "sline err";
    st.textContent = `✗ ${e.message}`;
    lg(`✗ Seq: ${e.message}`, "err");
  }
}
function togDay(d) {
  const i = schedDays.indexOf(d);
  if (i === -1) schedDays.push(d);
  else schedDays.splice(i, 1);
  document
    .querySelectorAll(".dbtn2")
    .forEach((b) =>
      b.classList.toggle("on", schedDays.includes(parseInt(b.dataset.d))),
    );
}
function onScDisp() {
  document.getElementById("sMsgW").style.display =
    document.getElementById("sDp").value === "message" ? "block" : "none";
}
async function addJob() {
  const h = parseInt(document.getElementById("sHr").value),
    m = parseInt(document.getElementById("sMn").value);
  const st = document.getElementById("sSt").value,
    mo = document.getElementById("sMo").value;
  const di = document.getElementById("sDp").value,
    msg = document.getElementById("sMsg").value.trim() || null;
  const ss = document.getElementById("scSt");
  if (isNaN(h) || isNaN(m)) {
    ss.className = "sline err";
    ss.textContent = "Invalid time";
    return;
  }
  const pay = {
    hour: h,
    minute: m,
    days: schedDays.slice(),
    state: st,
    mode: mo,
    show_middle_finger: di === "finger",
    message: di === "message" ? msg : null,
  };
  try {
    const r = await fetch(`http://${ip()}/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pay),
      signal: AbortSignal.timeout(5000),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    ss.className = "sline ok";
    ss.textContent = `✓ Job #${d.id}`;
    lg(`✓ Job #${d.id}`, "ok");
    loadJobs();
  } catch (e) {
    ss.className = "sline err";
    ss.textContent = `✗ ${e.message}`;
    lg(`✗ ${e.message}`, "err");
  }
}
async function loadJobs() {
  try {
    const r = await fetch(`http://${ip()}/schedule`, {
      signal: AbortSignal.timeout(3000),
    });
    const d = await r.json();
    rendJobs(d.jobs || []);
  } catch (e) {
    lg(`Jobs: ${e.message}`, "err");
  }
}
function rendJobs(jobs) {
  const el = document.getElementById("jList");
  if (!jobs.length) {
    el.innerHTML = '<div class="nojobs">NO JOBS SCHEDULED</div>';
    return;
  }
  el.innerHTML = jobs
    .map((j) => {
      const h = String(j.hour).padStart(2, "0"),
        m = String(j.minute).padStart(2, "0");
      const days =
        j.days && j.days.length
          ? j.days.map((d) => DAYS[d]).join(" ")
          : "EVERY DAY";
      const dp = j.show_middle_finger
        ? "🖕"
        : j.message
          ? `💬 ${j.message.toUpperCase()}`
          : "🎨";
      const dc = j.state === "red" ? "r" : j.state === "green" ? "g" : "p";
      return `<div class="jcard ${j.enabled ? "" : "off"}"><div class="jtime">${h}:${m}</div><div class="jinfo"><div class="jmeta"><span class="jdot j${dc}"></span>${j.state.toUpperCase()}·${j.mode.toUpperCase()}·${dp}</div><div class="jdays">${days}</div></div><div class="jacts"><button class="jb tog" onclick="togJob(${j.id})">${j.enabled ? "OFF" : "ON"}</button><button class="jb del" onclick="delJob(${j.id})">DEL</button></div></div>`;
    })
    .join("");
}
async function togJob(id) {
  try {
    const r = await fetch(`http://${ip()}/schedule/${id}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(3000),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error);
    lg(`Job #${id} ${d.enabled ? "on" : "off"}`, "ok");
    loadJobs();
  } catch (e) {
    lg(`✗ ${e.message}`, "err");
  }
}
async function delJob(id) {
  try {
    const r = await fetch(`http://${ip()}/schedule/${id}`, {
      method: "DELETE",
      signal: AbortSignal.timeout(3000),
    });
    if (!r.ok) {
      const d = await r.json();
      throw new Error(d.error);
    }
    lg(`Job #${id} deleted`, "ok");
    loadJobs();
  } catch (e) {
    lg(`✗ ${e.message}`, "err");
  }
}
updLCD();
renderSavesGrid();
lg("Ready · enter IP and ping", "inf");
if (_picoAuth.role !== "admin") {
  document.getElementById("adminContent").style.display = "none";
  document.getElementById("viewerNote").style.display = "block";
  document.getElementById("rebootBtn").style.display = "none";
  const sLink = document.getElementById("settingsNavBtn");
  if (sLink) sLink.style.display = "none";
  setTimeout(() => ping(), 400);
}
