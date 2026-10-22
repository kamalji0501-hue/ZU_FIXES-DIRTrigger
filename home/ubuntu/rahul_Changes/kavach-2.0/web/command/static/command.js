(() => {
  const $ = (id) => document.getElementById(id);
  const loginGate = $("loginGate");
  const app = $("app");
  let timer = null;
  /** @type {Record<string, {booked:number|null, running:number|null, error?:string, asof?:number}>} */
  const pnlSplitById = Object.create(null);
  let pnlSplitAllBusy = false;
  /** @type {any} */
  let lastSnap = null;

  /** Always fill the real browser window (same as big screen). No centered/scaled box. */
  function fitCommand() {
    if (!app) return;
    const root = document.documentElement;
    root.setAttribute("data-fit", "native");
    root.style.setProperty("--cc-fit", "1");
    [
      "position", "left", "top", "right", "bottom", "width", "height",
      "maxHeight", "margin", "transform", "transformOrigin", "zoom",
    ].forEach((k) => { app.style[k] = ""; });
    sizeGridRows();
  }

  /** Lock each grid row so 2×5 (10 cards) fills the scrollport; scroll for the rest. */
  function sizeGridRows() {
    const sc = $("instanceScroll");
    if (!sc) return;
    const rootStyle = getComputedStyle(document.documentElement);
    const gapRaw = rootStyle.getPropertyValue("--cc-grid-gap").trim();
    const rowsRaw = rootStyle.getPropertyValue("--cc-rows").trim();
    const gap = Number.parseFloat(gapRaw) || 4;
    const rows = Math.max(1, Number.parseInt(rowsRaw, 10) || 2);
    const h = sc.clientHeight;
    if (h < 40) return;
    const rowH = Math.max(100, (h - gap * (rows - 1)) / rows);
    sc.style.setProperty("--cc-row-h", `${rowH}px`);
  }

  function showToast(msg, ok) {
    const el = $("toast");
    el.textContent = msg;
    el.className = "toast " + (ok ? "ok" : "bad");
    el.hidden = false;
    setTimeout(() => { el.hidden = true; }, 2800);
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    let data = {};
    try { data = await res.json(); } catch (_) {}
    return { res, data };
  }

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("command_theme", theme);
    $("themeToggle").querySelectorAll("button[data-theme]").forEach((b) => {
      b.classList.toggle("on", b.dataset.theme === theme);
    });
  }

  function tickClock() {
    try {
      const fmt = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
      const dfmt = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
      $("clock").textContent = fmt.format(new Date());
      $("clockDate").textContent = dfmt.format(new Date()) + " IST";
    } catch (_) {}
  }

  function fmtNum(v, d = 0) {
    if (v == null || v === "" || Number.isNaN(Number(v))) return "—";
    return Number(v).toLocaleString("en-IN", {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    });
  }

  function pnlClass(v) {
    const n = Number(v);
    if (!Number.isFinite(n) || n === 0) return "";
    return n > 0 ? "pos" : "neg";
  }

  /** Low % = dark green → mid amber → high % = strong red */
  function gaugeColor(pct) {
    const p = Math.max(0, Math.min(100, Number(pct) || 0)) / 100;
    // dark green #166534 → lime #65a30d → amber #d97706 → red #b91c1c
    const stops = [
      [0.0, [22, 101, 52]],
      [0.35, [101, 163, 13]],
      [0.65, [217, 119, 6]],
      [1.0, [185, 28, 28]],
    ];
    let a = stops[0];
    let b = stops[stops.length - 1];
    for (let i = 0; i < stops.length - 1; i++) {
      if (p >= stops[i][0] && p <= stops[i + 1][0]) {
        a = stops[i];
        b = stops[i + 1];
        break;
      }
    }
    const t = (p - a[0]) / Math.max(0.0001, b[0] - a[0]);
    const rgb = a[1].map((c, i) => Math.round(c + (b[1][i] - c) * t));
    return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
  }

  function gauge(pct, label) {
    const p = Math.max(0, Math.min(100, Number(pct) || 0));
    const color = gaugeColor(p);
    return `<div class="gauge" style="--pct:${p};--gcolor:${color}"><div><strong>${fmtNum(p, 0)}%</strong><span>${label}</span></div></div>`;
  }

  function cardHtml(inst) {
    if (inst.empty) {
      return `
        <article class="card glass inst-card empty">
          <div class="card-head">
            <span class="tag">SLOT ${inst.slot || "?"}</span>
            <h2 class="desk-name muted">Waiting for instance…</h2>
          </div>
          <p class="placeholder-copy">Register instance #${inst.slot || "?"} in command registry — card fills automatically.</p>
        </article>`;
    }
    const subOk = String(inst.subscription_status || "").toUpperCase() === "ACTIVE";
    return `
      <article class="card glass inst-card live" data-id="${inst.id || ""}">
        <div class="card-head">
          <span class="tag">#${inst.slot || inst.server_tag || "?"}</span>
          <h2 class="desk-name">${inst.label || inst.id || "Instance"}</h2>
          ${inst.aws_account ? `<span class="alias">${inst.aws_account}</span>` : ""}
        </div>
        <div class="card-body">
          <section class="panel health-panel health-top">
            <h3 class="panel-title">Health</h3>
            <div class="gauges row4">
              ${gauge(inst.cpu_pct, "CPU")}
              ${gauge(inst.ram_pct, "RAM")}
              ${gauge(inst.disk_pct, "DISK")}
              ${gauge(inst.feeder_cpu_pct, "FEED")}
            </div>
          </section>
          <div class="panel-row">
            <section class="panel auth-panel">
              <h3 class="panel-title">Authorization</h3>
              <div class="kv-board kv-board-7">
                <div class="kv"><span title="Max sell lots (Directional)">Dir Sell</span><b>${fmtNum(inst.directional_sell_lots ?? inst.directional_lots, 0)}</b></div>
                <div class="kv"><span title="Max ATO lots (Directional)">Dir ATO</span><b>${fmtNum(inst.directional_ato_lots, 0)}</b></div>
                <div class="kv"><span title="Max sell lots (Batman)">Bat Sell</span><b>${fmtNum(inst.batman_sell_lots ?? inst.batman_lots, 0)}</b></div>
                <div class="kv"><span title="Max ATO lots (Batman)">Bat ATO</span><b>${fmtNum(inst.batman_ato_lots, 0)}</b></div>
                <div class="kv"><span title="Subscription">Sub</span><b class="${subOk ? "pos" : "neg"}">${inst.subscription_status || "—"}</b></div>
                <div class="kv"><span title="Start date">Start</span><b>${inst.subscription_start || "—"}</b></div>
                <div class="kv"><span title="End date">End</span><b>${inst.subscription_end || "—"}</b></div>
              </div>
            </section>
            <section class="panel pnl-panel-wrap">
              <div class="pnl-panel">
                <div class="pnl-big">
                  <div class="pnl-day-row">
                    <span>Day PnL</span>
                    <strong class="${pnlClass(inst.day_pnl)}">${fmtNum(inst.day_pnl, 2)}</strong>
                  </div>
                  ${pnlSplitHtml(inst)}
                </div>
              </div>
            </section>
          </div>
        </div>
      </article>`;
  }

  function pnlSplitHtml(inst) {
    if (inst.empty) return "";
    const id = String(inst.id || "");
    const split = pnlSplitById[id];
    let booked = "—";
    let running = "—";
    let total = "—";
    let bookedCls = "";
    let runningCls = "";
    let totalCls = "";
    if (split && !split.error) {
      const b = Number(split.booked);
      const r = Number(split.running);
      const t = Number.isFinite(b) && Number.isFinite(r) ? b + r : Number(split.total);
      booked = fmtNum(b, 2);
      running = fmtNum(r, 2);
      total = Number.isFinite(t) ? fmtNum(t, 2) : "—";
      bookedCls = pnlClass(b);
      runningCls = pnlClass(r);
      totalCls = pnlClass(t);
    }
    return `<div class="pnl-split">
      <div class="pnl-split-cells">
        <div class="pnl-split-cell"><span>Booked</span><b class="${bookedCls}">${booked}</b></div>
        <div class="pnl-split-cell"><span>Running</span><b class="${runningCls}">${running}</b></div>
        <div class="pnl-split-cell"><span>Total</span><b class="${totalCls}">${total}</b></div>
      </div>
    </div>`;
  }

  function updateHeaderSplitTotals() {
    let bookedSum = 0;
    let runningSum = 0;
    let n = 0;
    Object.keys(pnlSplitById).forEach((id) => {
      const s = pnlSplitById[id];
      if (!s || s.error) return;
      const b = Number(s.booked);
      const r = Number(s.running);
      if (!Number.isFinite(b) || !Number.isFinite(r)) return;
      bookedSum += b;
      runningSum += r;
      n += 1;
    });
    const totalSum = bookedSum + runningSum;
    const bookedEl = $("totalBooked");
    const runningEl = $("totalRunning");
    const sumEl = $("totalSplitSum");
    const countEl = $("totalSplitCount");
    if (bookedEl) {
      bookedEl.textContent = n ? fmtNum(bookedSum, 2) : "—";
      bookedEl.className = "total-pnl-sub " + (n ? pnlClass(bookedSum) : "");
    }
    if (runningEl) {
      runningEl.textContent = n ? fmtNum(runningSum, 2) : "—";
      runningEl.className = "total-pnl-sub " + (n ? pnlClass(runningSum) : "");
    }
    if (sumEl) {
      sumEl.textContent = n ? fmtNum(totalSum, 2) : "—";
      sumEl.className = "total-pnl-sub " + (n ? pnlClass(totalSum) : "");
    }
    if (countEl) {
      countEl.textContent = n === 1 ? "from 1 server" : `from ${n} servers`;
    }
  }

  function applySplitResult(id, data) {
    if (!id) return;
    if (data && data.ok) {
      const b = Number(data.booked);
      const r = Number(data.running);
      pnlSplitById[id] = {
        booked: b,
        running: r,
        total: Number.isFinite(Number(data.total)) ? Number(data.total) : (b + r),
        asof: Number(data.asof) || (Date.now() / 1000),
      };
    } else {
      pnlSplitById[id] = {
        booked: null,
        running: null,
        total: null,
        error: (data && data.error) || "failed",
      };
    }
    const card = document.querySelector(`.inst-card[data-id="${id.replace(/"/g, "")}"]`);
    if (!card) return;
    // Re-paint only the split block if card still exists after a full render
    const wrap = card.querySelector(".pnl-big");
    if (!wrap) return;
    const day = wrap.querySelector(".pnl-day-row");
    const old = wrap.querySelector(".pnl-split");
    const fake = { id, empty: false, reachable: true };
    const html = pnlSplitHtml(fake);
    if (old) old.outerHTML = html;
    else if (day) day.insertAdjacentHTML("afterend", html);
    else wrap.insertAdjacentHTML("beforeend", html);
    updateHeaderSplitTotals();
  }

  async function fetchDeskPnl(id) {
    const { res, data } = await api("/api/command/desk-pnl", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
    applySplitResult(id, res.ok ? data : { ok: false, error: (data && data.error) || "http_" + res.status });
    return data;
  }

  async function fetchAllDeskPnl() {
    if (pnlSplitAllBusy) return;
    const btn = $("pnlSplitAllBtn");
    pnlSplitAllBusy = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Updating…";
    }
    try {
      const { res, data } = await api("/api/command/desk-pnl-all", {
        method: "POST",
        body: "{}",
      });
      if (!res.ok || !data.ok) {
        showToast((data && data.error) || "Refresh Total PNL failed", false);
        return;
      }
      const results = data.results || {};
      Object.keys(results).forEach((id) => applySplitResult(id, results[id]));
      updateHeaderSplitTotals();
      const n = Object.keys(results).length;
      showToast(`Total PNL refreshed (${n} desks)`, true);
    } finally {
      pnlSplitAllBusy = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Refresh Total PNL";
      }
    }
  }

  function render(snap) {
    lastSnap = snap;
    const instances = snap.instances || [];
    const slots = snap.slots || 15;
    const live = snap.live_count ?? instances.filter((i) => !i.empty && i.reachable).length;
    let totalPnl = 0;
    let pnlServers = 0;
    for (const inst of instances) {
      if (inst.empty) continue;
      const n = Number(inst.day_pnl);
      // Only desks with real P/L (positive or negative) contribute
      if (!Number.isFinite(n) || n === 0) continue;
      totalPnl += n;
      pnlServers += 1;
    }
    const totalEl = $("totalPnl");
    const countEl = $("totalPnlCount");
    if (totalEl) {
      totalEl.textContent = pnlServers ? fmtNum(totalPnl, 2) : "—";
      totalEl.className = "total-pnl " + pnlClass(pnlServers ? totalPnl : null);
    }
    if (countEl) {
      countEl.textContent = pnlServers === 1
        ? "from 1 server"
        : `from ${pnlServers} servers`;
    }
    $("instanceGrid").innerHTML = instances.map(cardHtml).join("");
    $("liveLabel").textContent = `${live} live · ${slots} slots`;
    const age = snap.updated_at ? new Date(snap.updated_at * 1000).toLocaleTimeString() : "—";
    $("updatedAt").textContent = "Updated " + age;
    updateHeaderSplitTotals();
    requestAnimationFrame(sizeGridRows);
  }

  async function loadSnap(extra = "") {
    const { res, data } = await api("/api/command/snapshot" + extra);
    if (res.status === 401) {
      showApp(false);
      return;
    }
    if (!data.ok && !data.instances) {
      showToast(data.error || "Snapshot failed", false);
      return;
    }
    render(data);
  }

  function showApp(on) {
    loginGate.hidden = on;
    app.hidden = !on;
    if (on) {
      fitCommand();
      loadSnap();
      if (timer) clearInterval(timer);
      timer = setInterval(() => loadSnap(), 15000);
    } else if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  async function boot() {
    setTheme(localStorage.getItem("command_theme") || "day");
    document.documentElement.removeAttribute("data-skin");
    document.documentElement.removeAttribute("data-grid");
    document.documentElement.removeAttribute("data-layout");
    localStorage.removeItem("command_skin");
    localStorage.removeItem("command_grid");
    localStorage.removeItem("command_layout");
    fitCommand();
    window.addEventListener("resize", fitCommand);
    tickClock();
    setInterval(tickClock, 1000);
    const { res } = await api("/api/command/me");
    showApp(res.ok);
  }

  $("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("loginErr").hidden = true;
    const { res, data } = await api("/api/command/login", {
      method: "POST",
      body: JSON.stringify({ password: $("pw").value }),
    });
    if (!res.ok) {
      $("loginErr").textContent = data.error || "Login failed";
      $("loginErr").hidden = false;
      return;
    }
    showApp(true);
  });

  $("logoutBtn").addEventListener("click", async () => {
    await api("/api/command/logout", { method: "POST", body: "{}" });
    showApp(false);
  });

  $("themeToggle").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-theme]");
    if (b) setTheme(b.dataset.theme);
  });

  function broadcastDesks() {
    const snap = lastSnap || {};
    return (snap.instances || []).filter((i) => i && !i.empty && i.id);
  }

  function updateBroadcastDeskCount() {
    const box = $("broadcastDeskList");
    const countEl = $("broadcastDeskCount");
    if (!box || !countEl) return;
    const boxes = [...box.querySelectorAll('input[type="checkbox"][data-desk-id]')];
    const n = boxes.filter((c) => c.checked).length;
    const total = boxes.length;
    countEl.textContent = n === total && total > 0
      ? `All ${total} desks`
      : `${n} of ${total} selected`;
    const sendBtn = $("broadcastSend");
    if (sendBtn && !sendBtn.disabled) {
      sendBtn.textContent = n === total && total > 0 ? "Send to all desks" : `Send to ${n} desk${n === 1 ? "" : "s"}`;
    }
  }

  function fillBroadcastDesks() {
    const box = $("broadcastDeskList");
    if (!box) return;
    const desks = broadcastDesks();
    if (!desks.length) {
      box.innerHTML = `<span class="muted">No desks loaded yet — close and Desk Refresh first.</span>`;
      updateBroadcastDeskCount();
      return;
    }
    box.innerHTML = desks.map((d) => {
      const id = String(d.id || "").replace(/"/g, "");
      const label = String(d.label || id);
      const live = d.reachable ? "" : " (down)";
      return `<label><input type="checkbox" data-desk-id="${id}" checked /> ${label}${live}</label>`;
    }).join("");
    box.querySelectorAll('input[type="checkbox"]').forEach((c) => {
      c.addEventListener("change", updateBroadcastDeskCount);
    });
    updateBroadcastDeskCount();
  }

  function setBroadcastSelection(all) {
    const box = $("broadcastDeskList");
    if (!box) return;
    box.querySelectorAll('input[type="checkbox"][data-desk-id]').forEach((c) => {
      c.checked = !!all;
    });
    updateBroadcastDeskCount();
  }

  function selectedBroadcastDeskIds() {
    const box = $("broadcastDeskList");
    if (!box) return [];
    return [...box.querySelectorAll('input[type="checkbox"][data-desk-id]:checked')]
      .map((c) => c.getAttribute("data-desk-id") || "")
      .filter(Boolean);
  }

  function openBroadcast() {
    const modal = $("broadcastModal");
    const res = $("broadcastResult");
    if (res) {
      res.hidden = true;
      res.textContent = "";
    }
    fillBroadcastDesks();
    if (modal) modal.hidden = false;
  }

  function closeBroadcast() {
    const modal = $("broadcastModal");
    if (modal) modal.hidden = true;
  }

  function fileToB64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const s = String(reader.result || "");
        const i = s.indexOf(",");
        resolve(i >= 0 ? s.slice(i + 1) : s);
      };
      reader.onerror = () => reject(new Error("read_failed"));
      reader.readAsDataURL(file);
    });
  }

  async function sendBroadcast() {
    const textEl = $("broadcastText");
    const sevEl = $("broadcastSeverity");
    const fileEl = $("broadcastFile");
    const sendBtn = $("broadcastSend");
    const resEl = $("broadcastResult");
    const text = (textEl && textEl.value || "").trim();
    if (!text) {
      showToast("Enter a message", false);
      return;
    }
    const deskIds = selectedBroadcastDeskIds();
    if (!deskIds.length) {
      showToast("Select at least one desk", false);
      return;
    }
    const payload = {
      text,
      severity: (sevEl && sevEl.value) || "orange",
      filename: "",
      content_type: "",
      content_b64: "",
      desk_ids: deskIds,
    };
    if (fileEl && fileEl.files && fileEl.files[0]) {
      const f = fileEl.files[0];
      if (f.size > 1000000) {
        showToast("File too large (max 1 MB)", false);
        return;
      }
      payload.filename = f.name || "attachment";
      payload.content_type = f.type || "";
      try {
        payload.content_b64 = await fileToB64(f);
      } catch (_) {
        showToast("Could not read file", false);
        return;
      }
    }
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.textContent = "Sending…";
    }
    try {
      const { res, data } = await api("/api/command/broadcast", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!res.ok || !data.ok) {
        showToast((data && data.error) || "Broadcast failed", false);
        if (resEl) {
          resEl.hidden = false;
          resEl.textContent = (data && data.error) || ("http_" + res.status);
        }
        return;
      }
      const lines = (data.results || []).map((r) => {
        const name = r.label || r.id || "?";
        return r.ok ? `OK  ${name}` : `FAIL ${name}: ${r.error || "error"}`;
      });
      if (resEl) {
        resEl.hidden = false;
        resEl.textContent = `Sent ${data.ok_count || 0}/${data.count || 0}\n` + lines.join("\n");
      }
      showToast(`Broadcast sent (${data.ok_count || 0} ok, ${data.fail_count || 0} fail)`, true);
      if (textEl) textEl.value = "";
      if (fileEl) fileEl.value = "";
    } finally {
      if (sendBtn) {
        sendBtn.disabled = false;
        updateBroadcastDeskCount();
      }
    }
  }

  $("refreshBtn").addEventListener("click", () => loadSnap("?refresh=1"));
  $("pnlSplitAllBtn").addEventListener("click", () => fetchAllDeskPnl());
  if ($("broadcastBtn")) $("broadcastBtn").addEventListener("click", openBroadcast);
  if ($("broadcastClose")) $("broadcastClose").addEventListener("click", closeBroadcast);
  if ($("broadcastSend")) $("broadcastSend").addEventListener("click", sendBroadcast);
  if ($("broadcastSelectAll")) $("broadcastSelectAll").addEventListener("click", () => setBroadcastSelection(true));
  if ($("broadcastSelectNone")) $("broadcastSelectNone").addEventListener("click", () => setBroadcastSelection(false));
  if ($("broadcastModal")) {
    $("broadcastModal").addEventListener("click", (e) => {
      if (e.target === $("broadcastModal")) closeBroadcast();
    });
  }
  boot();
})();
