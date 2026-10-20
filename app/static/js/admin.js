const $ = (id) => document.getElementById(id);

function row(cells) {
  const tr = document.createElement("tr");
  for (const c of cells) { const td = document.createElement("td"); td.textContent = c; tr.append(td); }
  return tr;
}

async function load() {
  try {
    const r = await fetch("/api/admin/stats", { credentials: "same-origin" });
    if (r.status === 401 || r.status === 403) { $("err").textContent = "Потрібен вхід адміністратора (спочатку увійдіть на головній сторінці)."; return; }
    const d = await r.json();
    $("err").textContent = "";
    $("kpi").innerHTML = "";
    const items = [["Серверів", d.servers.length], ["У черзі", d.queued], ["Виконується", d.running],
                   ["Завершено", d.tasks.done || 0], ["Скасовано", d.tasks.cancelled || 0], ["Помилок", d.tasks.failed || 0]];
    for (const [k, v] of items) { const div = document.createElement("div"); div.innerHTML = `<b>${v}</b>${k}`; $("kpi").append(div); }
    $("servers").replaceChildren(...d.servers.map((s) => row([s.hostname, s.workers, s.busy, s.tasks.join(", ")])));
    $("events").replaceChildren(...d.events.map((e) => row([new Date(e.ts).toLocaleTimeString(), e.message])));
  } catch (e) { $("err").textContent = "Помилка завантаження"; }
}
load();
setInterval(load, 2000);
