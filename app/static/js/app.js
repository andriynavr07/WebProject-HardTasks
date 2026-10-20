const $ = (id) => document.getElementById(id);
let timer = null;

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
  } catch (e) { show(false); }
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

function fmtEta(t) {
  if (t.status !== "queued") return "";
  return t.eta_seconds === 0 ? "зараз" : "~" + Math.ceil(t.eta_seconds) + " с";
}

function summary(t) {
  if (t.status === "done" && t.type === "linear") return ` (похибка ${t.result.max_error.toExponential(1)}, ${t.result.seconds} с)`;
  if (t.status === "failed") return " — " + (t.error || "");
  return "";
}

async function refresh() {
  try {
    const tasks = await api("/api/tasks");
    const body = $("tasks");
    body.textContent = "";
    for (const t of tasks) {
      const tr = document.createElement("tr");
      const name = t.type === "linear" ? `СЛАР n=${t.params.n}` : `Зображення: ${t.params.filter}`;
      tr.innerHTML = `<td>${t.id}</td><td></td><td class="st-${t.status}">${t.status}</td>
        <td><span class="bar"><div style="width:${t.progress}%"></div></span> ${Math.round(t.progress)}%</td>
        <td>${fmtEta(t)}</td><td>${t.worker ? t.worker.split("-").slice(0, -1).join("-").slice(0, 12) : ""}</td><td></td>`;
      tr.children[1].textContent = name + summary(t);
      const cell = tr.children[6];
      if (t.status === "queued" || t.status === "running") {
        const b = document.createElement("button");
        b.className = "danger"; b.textContent = "Скасувати";
        b.onclick = () => api(`/api/tasks/${t.id}/cancel`, { method: "POST" }).catch((e) => ($("err").textContent = e.message));
        cell.append(b);
      } else if (t.status === "done" && t.type === "image") {
        const a = document.createElement("a");
        a.href = `/api/tasks/${t.id}/result`; a.target = "_blank"; a.textContent = "Результат";
        cell.append(a);
      }
      body.append(tr);
    }
  } catch (e) { if (e.status === 401) init(); }
}

async function createTask(path, options) {
  $("err").textContent = "";
  try { await api(path, { method: "POST", ...options }); refresh(); }
  catch (e) { $("err").textContent = e.message; }
}

$("btn-login").onclick = () => auth("login");
$("btn-register").onclick = () => auth("register");
$("lin-go").onclick = () => createTask("/api/tasks/linear", {
  headers: { "Content-Type": "application/json" }, body: JSON.stringify({ n: parseInt($("lin-n").value, 10) }),
});
$("img-go").onclick = () => {
  const f = $("img-file").files[0];
  if (!f) { $("err").textContent = "Оберіть файл"; return; }
  const fd = new FormData();
  fd.append("file", f);
  fd.append("filter", $("img-filter").value);
  fd.append("kernel", $("img-kernel").value);
  fd.append("passes", $("img-passes").value);
  createTask("/api/tasks/image", { body: fd });
};
init();
