const $ = (id) => document.getElementById(id);
let timer = null;
let pickerSig = null;          
const resultCache = new Map();
const PAGE_SIZE = 8;
let page = 1;
let pagerSig = "";
let reqId = 0;

async function api(path, opts = {}) {
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  let data = null;
  try { data = await r.json(); } catch (e) { /* не JSON */ }
  if (!r.ok) {
    const err = new Error(typeof data?.detail === "string" ? data.detail : "Помилка запиту");
    err.status = r.status;
    throw err;
  }
  return data;
}

function show(loggedIn, me) {
  $("auth").classList.toggle("hidden", loggedIn);
  $("work").classList.toggle("hidden", !loggedIn);
  const box = $("userbox");
  box.textContent = "";
  if (loggedIn) {
    box.append(me.username);
    if (me.is_admin) {
      const a = document.createElement("a");
      a.href = "/admin"; a.textContent = "Адмін-панель";
      box.append(" ", a);
    }
    const b = document.createElement("button");
    b.textContent = "Вийти";
    b.onclick = async () => { await api("/api/logout", { method: "POST" }); init(); };
    box.append(b);
  }
}

async function init() {
  clearInterval(timer);
  try {
    const me = await api("/api/me");
    show(true, me);
    refresh();
    timer = setInterval(refresh, 1000);
  } catch (e) {
    resetResults();
    show(false);
  }
}

async function auth(kind) {
  $("auth-err").textContent = "";
  try {
    await api("/api/" + kind, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("username").value, password: $("password").value }),
    });
    init();
  } catch (e) { $("auth-err").textContent = e.status === 422 ? "Логін: 3–32 символи (літери/цифри), пароль: 6–72" : e.message; }
}

function fmtSec(x) {
  x = Math.ceil(x);
  return x >= 60 ? Math.floor(x / 60) + " хв " + (x % 60) + " с" : x + " с";
}

function fmtEta(t) {
  if (t.status === "queued" && t.eta_seconds != null) return t.eta_seconds === 0 ? "зараз" : "старт через ~" + fmtSec(t.eta_seconds);
  if (t.status === "running" && t.remaining_seconds != null) return "залишилось ~" + fmtSec(t.remaining_seconds);
  return "";
}

function summary(t) {
  if (t.status === "done" && t.type === "linear") return ` (похибка ${t.result.max_error.toExponential(1)}, ${t.result.seconds} с)`;
  if (t.status === "failed") return " — " + (t.error || "");
  return "";
}


function resetResults() {
  page = 1;
  pagerSig = "";
  $("pager").textContent = "";
  pickerSig = null;
  resultCache.clear();
  $("res-pick").textContent = "";
  $("res-pick").disabled = true;
  showMsg("Поки немає виконаних задач");
}

function showMsg(text) {
  const body = $("res-body");
  body.textContent = "";
  const p = document.createElement("p");
  p.className = "res-empty";
  p.textContent = text;
  body.append(p);
}

function subscript(i) {
  return "x" + String(i).replace(/\d/g, (d) => "₀₁₂₃₄₅₆₇₈₉"[d]);
}

function renderResult(r) {
  const body = $("res-body");
  body.textContent = "";

  const kpi = document.createElement("div");
  kpi.className = "kpi res-kpi";
  const tiles = [
    ["Розмір n", r.n],
    ["Час", r.seconds + " с"],
    ["Похибка", Number(r.max_error).toExponential(1)],
  ];
  for (const [label, value] of tiles) {
    const d = document.createElement("div");
    d.append(label);
    const b = document.createElement("b");
    b.textContent = value;
    d.append(b);
    kpi.append(d);
  }
  body.append(kpi);

  const values = r.first_values || [];
  if (values.length) {
    const h = document.createElement("h3");
    h.className = "res-sub";
    h.textContent = "Перші значення розв'язку";
    body.append(h);

    const table = document.createElement("table");
    table.className = "res-vals";
    const tbody = document.createElement("tbody");
    values.forEach((v, i) => {
      const tr = document.createElement("tr");
      const k = document.createElement("td");
      k.textContent = subscript(i + 1);
      const val = document.createElement("td");
      val.textContent = v;
      tr.append(k, val);
      tbody.append(tr);
    });
    table.append(tbody);
    body.append(table);
  }
}

async function loadResult(id) {
  if (resultCache.has(id)) { renderResult(resultCache.get(id)); return; }
  showMsg("Завантаження…");
  try {
    const r = await api(`/api/tasks/${id}/result`);
    resultCache.set(id, r);
    if ($("res-pick").value === id) renderResult(r);
  } catch (e) {
    if ($("res-pick").value === id) showMsg(e.message);
  }
}

function updatePicker(done) {
  const sig = done.map((t) => t.id).join(",");
  if (sig === pickerSig) return;
  pickerSig = sig;

  const sel = $("res-pick");
  const prev = sel.value;
  sel.textContent = "";

  if (!done.length) {
    sel.disabled = true;
    showMsg("Поки немає виконаних задач");
    return;
  }

  sel.disabled = false;
  for (const t of done) {
    const o = document.createElement("option");
    o.value = String(t.id);
    o.textContent = `#${t.id} · СЛАР n=${t.n}`;
    sel.append(o);
  }
  if (prev && done.some((t) => String(t.id) === prev)) sel.value = prev;   // зберігаємо вибір
  loadResult(sel.value);
}


function pageList(cur, total) {
  const set = new Set([1, total, cur - 1, cur, cur + 1]);
  const nums = [...set].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b);
  const out = [];
  nums.forEach((n, i) => {
    if (i && n - nums[i - 1] > 1) out.push("…");
    out.push(n);
  });
  return out;
}

function renderPager(cur, total) {
  const sig = cur + "/" + total;
  if (sig === pagerSig) return;
  pagerSig = sig;
  const nav = $("pager");
  nav.textContent = "";
  if (total <= 1) return;

  const mk = (label, target, opts = {}) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.disabled = !!opts.disabled;
    if (opts.active) { b.className = "active"; b.setAttribute("aria-current", "page"); }
    b.onclick = () => { page = target; refresh(); };
    return b;
  };
  nav.append(mk("‹ Назад", cur - 1, { disabled: cur <= 1 }));
  for (const n of pageList(cur, total)) {
    if (n === "…") {
      const g = document.createElement("span");
      g.className = "gap";
      g.textContent = "…";
      nav.append(g);
    } else {
      nav.append(mk(String(n), n, { active: n === cur }));
    }
  }
  nav.append(mk("Далі ›", cur + 1, { disabled: cur >= total }));
}

function renderTasks(tasks) {
  const body = $("tasks");
  body.textContent = "";
  for (const t of tasks) {
    const tr = document.createElement("tr");
    const name = t.type === "linear" ? `СЛАР n=${t.params.n}` : "";
    tr.innerHTML = `<td>${t.id}</td><td></td><td class="st-${t.status}">${t.status === "queued" && t.scaling ? "queued · Scale up" : t.status}</td>
      <td><span class="bar"><div style="width:${t.progress}%"></div></span> ${Math.round(t.progress)}%</td>
      <td>${fmtEta(t)}</td><td>${t.worker ? t.worker.split("-").slice(0, -1).join("-").slice(0, 12) : ""}</td><td></td>`;
    const text = name + summary(t);
    tr.children[1].textContent = text;
    tr.children[1].title = text;
    const cell = tr.children[6];
    if (t.status === "queued" || t.status === "running") {
      const b = document.createElement("button");
      b.className = "danger";
      b.textContent = "Скасувати";
      b.onclick = () => api(`/api/tasks/${t.id}/cancel`, {method: "POST"}).catch((e) => ($("err").textContent = e.message));
      cell.append(b);
    }
    body.append(tr);
  }
}

async function refresh() {
  const my = ++reqId;
  try {
    const [hist, done] = await Promise.all([
      api(`/api/tasks/history?page=${page}&per_page=${PAGE_SIZE}`),
      api("/api/tasks/done"),
    ]);
    if (my !== reqId) return;
    page = hist.page;
    renderTasks(hist.items);
    renderPager(hist.page, hist.pages);
    updatePicker(done);
  } catch (e) { if (e.status === 401) init(); }
}

async function createTask(path, options) {
  $("err").textContent = "";
  try { await api(path, { method: "POST", ...options }); refresh(); }
  catch (e) { $("err").textContent = e.message; }
}

$("btn-login").onclick = () => auth("login");
$("btn-register").onclick = () => auth("register");
$("res-pick").onchange = () => loadResult($("res-pick").value);
$("lin-go").onclick = () => createTask("/api/tasks/linear", {
  headers: { "Content-Type": "application/json" }, body: JSON.stringify({ n: parseInt($("lin-n").value, 10) }),
});
init();