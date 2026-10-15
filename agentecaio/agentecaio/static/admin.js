const $ = selector => document.querySelector(selector);
const state = { authenticated: false, offset: 0, total: 0, limit: 25, record: null, view: "overview" };
const fieldNames = ["title", "category", "discipline", "description", "publication_date", "event_date", "event_end_date", "start_time", "end_time", "deadline", "professor", "location", "modality", "institution", "workload", "requirements", "reference_link", "notes", "grade"];
const dateFields = new Set(["publication_date", "event_date", "event_end_date", "deadline"]);
const statusLabels = { rascunho: "Rascunho", em_revisao: "Em revisão", oficial: "Oficial", arquivada: "Arquivada", retirada: "Retirada" };
const statusOrder = ["rascunho", "em_revisao", "oficial", "arquivada", "retirada"];

function message(text, kind = "") {
  const target = $("#admin-message");
  target.textContent = text;
  target.dataset.kind = kind;
}

function csrfToken() {
  const entry = document.cookie.split(";").map(value => value.trim()).find(value => value.startsWith("caio_csrf="));
  return entry ? decodeURIComponent(entry.slice("caio_csrf=".length)) : "";
}

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRF-Token", csrfToken());
  const response = await fetch(path, { ...options, method, headers, credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) showLogin("Sua sessão expirou. Entre novamente.");
    throw new Error(data.detail || "Não foi possível concluir a operação.");
  }
  return data;
}

function showLogin(note = "") {
  state.authenticated = false;
  $("#admin-login").hidden = false;
  $("#admin-app").hidden = true;
  $("#logout").hidden = true;
  $("#login-message").textContent = note;
  $("#login-message").dataset.kind = note ? "error" : "";
  $("#login-token").value = "";
}

function showApp() {
  state.authenticated = true;
  $("#admin-login").hidden = true;
  $("#admin-app").hidden = false;
  $("#logout").hidden = false;
}

function setView(name) {
  state.view = name;
  document.querySelectorAll(".admin-tab").forEach(button => {
    const selected = button.dataset.view === name;
    button.setAttribute("aria-selected", String(selected));
  });
  document.querySelectorAll(".admin-view").forEach(section => {
    section.hidden = section.id !== `view-${name}`;
  });
}

function addOption(list, value, label = value) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  list.append(option);
}

async function loadCategories() {
  const [data, records] = await Promise.all([
    api("/api/admin/categories"),
    api("/api/admin/records?limit=100&offset=0"),
  ]);
  const list = $("#category-options");
  list.replaceChildren();
  data.items.forEach(item => addOption(list, item));
  const disciplines = $("#discipline-options");
  disciplines.replaceChildren();
  [...new Set(records.items.map(record => record.discipline).filter(Boolean))].forEach(item => addOption(disciplines, item));
}

function renderStats(stats) {
  const labels = [
    ["total", "Total"], ["rascunho", "Rascunhos"], ["em_revisao", "Em revisão"],
    ["oficial", "Oficiais"], ["arquivada", "Arquivados"], ["retirada", "Retirados"],
  ];
  const host = $("#admin-stats");
  host.replaceChildren();
  for (const [key, label] of labels) {
    const tile = document.createElement("div");
    tile.className = "admin-stat";
    const caption = document.createElement("span");
    caption.textContent = label;
    const number = document.createElement("strong");
    number.textContent = String(stats[key] ?? 0);
    tile.append(caption, number);
    host.append(tile);
  }
}

function recordDate(record) {
  const date = record.event_date || record.deadline;
  return date ? `${formatDateOnly(date)}${record.start_time ? ` · ${record.start_time}` : ""}` : "Sem data de evento";
}

function formatDateOnly(value) {
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}

function statusBadge(status) {
  const badge = document.createElement("span");
  badge.className = "admin-status";
  badge.dataset.status = status;
  badge.textContent = statusLabels[status] || status;
  return badge;
}

function button(label, action, id, className = "admin-button") {
  const control = document.createElement("button");
  control.type = "button";
  control.className = className;
  control.textContent = label;
  control.dataset.action = action;
  control.dataset.id = String(id);
  return control;
}

function actionsFor(record) {
  const actions = [button("Detalhes", "details", record.id, "admin-button quiet"), button("Histórico", "history", record.id, "admin-button quiet")];
  if (record.status !== "retirada") actions.push(button("Corrigir", "edit", record.id, "admin-button"));
  if (record.status === "rascunho") actions.push(button("Revisar", "review", record.id, "admin-button"));
  if (record.status === "em_revisao") actions.push(button("Publicar", "publish", record.id, "admin-button primary"));
  if (record.status === "oficial" && record.current_official) actions.push(button("Arquivar", "archive", record.id, "admin-button quiet"));
  if (!["retirada", "arquivada"].includes(record.status)) actions.push(button("Retirar", "withdraw", record.id, "admin-button danger"));
  return actions;
}

function renderRecord(record) {
  const row = document.createElement("article");
  row.className = "admin-record";
  const title = document.createElement("div");
  title.className = "admin-record-title";
  const heading = document.createElement("strong");
  heading.textContent = record.title;
  const subtitle = document.createElement("span");
  subtitle.textContent = [record.category, record.discipline].filter(Boolean).join(" · ") || "Sem categoria";
  title.append(heading, subtitle, statusBadge(record.status));

  const date = document.createElement("div");
  date.className = "admin-record-meta";
  date.textContent = recordDate(record);
  const professor = document.createElement("div");
  professor.className = "admin-record-meta";
  professor.textContent = record.professor || "Sem responsável informado";
  const version = document.createElement("div");
  version.className = "admin-record-meta record-version";
  version.textContent = `Versão ${record.version} · ${record.source}`;
  const controls = document.createElement("div");
  controls.className = "admin-record-actions";
  actionsFor(record).forEach(control => controls.append(control));
  row.append(title, date, professor, version, controls);
  return row;
}

function filterParams() {
  const params = new URLSearchParams();
  for (const [key, value] of new FormData($("#filter-form")).entries()) {
    if (String(value).trim()) params.set(key, String(value).trim());
  }
  params.set("limit", String(state.limit));
  params.set("offset", String(state.offset));
  return params;
}

async function loadRecords() {
  const data = await api(`/api/admin/records?${filterParams()}`);
  state.total = data.total;
  const list = $("#record-list");
  list.replaceChildren();
  data.items.forEach(record => list.append(renderRecord(record)));
  if (!data.items.length) {
    const empty = document.createElement("div");
    empty.className = "admin-empty";
    empty.textContent = "Nenhum registro encontrado com esses filtros.";
    list.append(empty);
  }
  const first = data.total ? data.offset + 1 : 0;
  const last = Math.min(data.offset + data.items.length, data.total);
  $("#record-count").textContent = `${first}–${last} de ${data.total} registros`;
  $("#previous-page").disabled = data.offset <= 0;
  $("#next-page").disabled = data.offset + data.items.length >= data.total;
}

async function loadOverview() {
  const [stats, recent] = await Promise.all([
    api("/api/admin/dashboard"),
    api("/api/admin/records?sort=updated_at&direction=desc&limit=6&offset=0"),
  ]);
  renderStats(stats);
  const host = $("#recent-records");
  host.replaceChildren();
  if (!recent.items.length) {
    const empty = document.createElement("p");
    empty.className = "admin-empty";
    empty.textContent = "Ainda não há registros no banco administrativo.";
    host.append(empty);
  } else recent.items.forEach(record => host.append(renderRecord(record)));
  const source = $("#source-note");
  source.textContent = stats.legacy_imported
    ? "Registros legados da Base do Google foram importados. O PDF no Foundry continua disponível como referência."
    : stats.legacy_import_ready
      ? "A Base do Google será importada quando as credenciais estiverem acessíveis; o PDF no Foundry continua como referência."
      : "Banco administrativo SQLite local. Nenhum registro da Base do Google foi importado; o PDF no Foundry continua como referência. Configure credenciais Google apenas se precisar migrar aquela planilha.";
}

async function loadAll() {
  try {
    await Promise.all([loadOverview(), loadRecords(), loadCategories()]);
    message("Alterações administrativas ficam registradas no histórico.");
  } catch (error) {
    message(error.message, "error");
  }
}

function formPayload() {
  const data = {};
  for (const name of fieldNames) data[name] = $(`#field-${name}`).value.trim();
  data.reason = $("#field-reason").value.trim();
  return data;
}

function setCategoryFields() {
  const category = $("#field-category").value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  document.querySelectorAll("[data-category-field]").forEach(field => {
    const allowed = field.dataset.categoryField.split(",").map(value => value.trim());
    const shouldShow = !category || allowed.some(value => category.includes(value));
    field.hidden = !shouldShow;
  });
}

function populateForm(record = {}) {
  for (const name of fieldNames) $(`#field-${name}`).value = record[name] || "";
  $("#field-reason").value = "";
  $("#record-status-label").textContent = record.id
    ? `${statusLabels[record.status] || record.status} · versão ${record.version}`
    : "Novo registro · rascunho";
  $("#record-modal-title").textContent = record.id ? "Corrigir informação" : "Novo registro";
  $("#record-publish").hidden = !record.id || !(record.current_official || record.has_official_ancestor);
  setCategoryFields();
}

function openRecordForm(record = null) {
  state.record = record;
  populateForm(record || {});
  $("#record-dialog").showModal();
}

function payloadToText(payload) {
  return fieldNames.filter(name => payload[name])
    .map(name => `${name}: ${dateFields.has(name) ? formatDateOnly(payload[name]) : payload[name]}`)
    .join("\n") || "Sem conteúdo preenchido.";
}

async function saveRecord() {
  const payload = formPayload();
  if (!payload.title || !payload.category) throw new Error("Preencha título e categoria.");
  let result;
  if (state.record?.id) {
    if (payloadToText(payload) === payloadToText(state.record)) return state.record;
    result = await api(`/api/admin/records/${state.record.id}`, { method: "PUT", body: JSON.stringify(payload) });
  } else {
    result = await api("/api/admin/records", { method: "POST", body: JSON.stringify(payload) });
  }
  state.record = result.item;
  populateForm(result.item);
  await Promise.all([loadRecords(), loadOverview()]);
  return result.item;
}

function buildPreview(record) {
  const preview = $("#publish-preview");
  preview.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = record.title;
  const category = document.createElement("p");
  category.textContent = [record.category, record.discipline].filter(Boolean).join(" · ");
  const body = document.createElement("pre");
  body.textContent = payloadToText(record);
  const source = document.createElement("p");
  source.className = "admin-subtle";
  source.textContent = `Fonte: ${record.source} · Versão ${record.version}`;
  preview.append(heading, category, body, source);
  $("#publish-confirm").dataset.id = String(record.id);
  $("#publish-confirm").dataset.updatedAt = record.updated_at;
  $("#publish-confirm").textContent = record.has_official_ancestor
    ? "Confirmar atualização oficial"
    : "Confirmar como oficial";
  $("#publish-dialog").showModal();
}

async function openHistory(id) {
  const data = await api(`/api/admin/records/${id}/history`);
  const host = $("#history-list");
  host.replaceChildren();
  if (!data.items.length) {
    const empty = document.createElement("p");
    empty.className = "admin-empty";
    empty.textContent = "Nenhuma alteração registrada.";
    host.append(empty);
  }
  for (const entry of data.items) {
    const article = document.createElement("article");
    article.className = "admin-history-entry";
    const heading = document.createElement("h3");
    heading.textContent = `${entry.action.replaceAll("_", " ")} · ${new Date(entry.changed_at).toLocaleString("pt-BR")}`;
    const meta = document.createElement("p");
    meta.className = "admin-subtle";
    meta.textContent = `${entry.actor} · ${statusLabels[entry.old_status] || entry.old_status || "—"} → ${statusLabels[entry.new_status] || entry.new_status}${entry.reason ? ` · Motivo: ${entry.reason}` : ""}`;
    article.append(heading, meta);
    const changed = fieldNames.filter(field => entry.before && (entry.before[field] || "") !== (entry.after[field] || ""));
    if (changed.length) {
      const changedFields = document.createElement("p");
      changedFields.className = "admin-changed-fields";
      changedFields.textContent = `Campos alterados: ${changed.join(", ")}`;
      article.append(changedFields);
    }
    const comparison = document.createElement("div");
    comparison.className = "admin-diff";
    for (const [label, snapshot] of [["Antes", entry.before], ["Depois", entry.after]]) {
      const section = document.createElement("section");
      const title = document.createElement("strong");
      title.textContent = label;
      const pre = document.createElement("pre");
      pre.textContent = payloadToText(snapshot || {});
      section.append(title, pre);
      comparison.append(section);
    }
    article.append(comparison);
    host.append(article);
  }
  $("#history-dialog").showModal();
}

async function showDetails(id) {
  const { item } = await api(`/api/admin/records/${id}`);
  const host = $("#details-content");
  host.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = item.title;
  const status = statusBadge(item.status);
  const list = document.createElement("dl");
  for (const field of fieldNames) {
    if (!item[field]) continue;
    const term = document.createElement("dt");
    term.textContent = field.replaceAll("_", " ");
    const value = document.createElement("dd");
    value.textContent = item[field];
    list.append(term, value);
  }
  const provenance = document.createElement("p");
  provenance.className = "admin-subtle";
  provenance.textContent = `Status: ${statusLabels[item.status]} · Versão ${item.version} · Origem: ${item.source}`;
  host.append(heading, status, list, provenance);
  $("#details-dialog").showModal();
}

async function runAction(action, id) {
  const { item } = await api(`/api/admin/records/${id}`);
  if (action === "edit") return openRecordForm(item);
  if (action === "details") return showDetails(id);
  if (action === "history") return openHistory(id);
  if (action === "publish") return buildPreview(item);
  const names = { review: "enviar para revisão", archive: "arquivar", withdraw: "retirar de circulação" };
  if (["archive", "withdraw"].includes(action) && !window.confirm(`Confirma ${names[action]} “${item.title}”?`)) return;
  const endpoint = { review: "review", archive: "archive", withdraw: "withdraw" }[action];
  const result = await api(`/api/admin/records/${id}/${endpoint}`, {
    method: "POST", body: JSON.stringify({ reason: $("#field-reason")?.value || "" }),
  });
  message(`${item.title}: ${statusLabels[result.item.status]}.`, "success");
  await Promise.all([loadRecords(), loadOverview()]);
}

$("#login-form").addEventListener("submit", async event => {
  event.preventDefault();
  message("Validando acesso…");
  try {
    await api("/api/admin/login", { method: "POST", body: JSON.stringify({ token: $("#login-token").value }) });
    showApp();
    await loadAll();
  } catch (error) {
    showLogin(error.message);
  }
});

$("#logout").addEventListener("click", async () => {
  try { await api("/api/admin/logout", { method: "POST", body: "{}" }); }
  catch (error) { message(error.message, "error"); }
  showLogin("Sessão encerrada.");
});

document.querySelectorAll(".admin-tab").forEach(tab => tab.addEventListener("click", () => setView(tab.dataset.view)));
$("#filter-form").addEventListener("submit", async event => { event.preventDefault(); state.offset = 0; await loadRecords(); });
$("#clear-filters").addEventListener("click", async () => { $("#filter-form").reset(); state.offset = 0; await loadRecords(); });
$("#filter-form").addEventListener("change", () => { state.offset = 0; loadRecords(); });
$("#previous-page").addEventListener("click", async () => { state.offset = Math.max(0, state.offset - state.limit); await loadRecords(); });
$("#next-page").addEventListener("click", async () => { state.offset += state.limit; await loadRecords(); });
$("#new-record").addEventListener("click", () => openRecordForm());
$("#new-record-overview").addEventListener("click", () => openRecordForm());
$("#field-category").addEventListener("input", setCategoryFields);

$("#record-form").addEventListener("submit", event => event.preventDefault());
$("#save-draft").addEventListener("click", async () => {
  try {
    const item = await saveRecord();
    message(`${item.title}: ${statusLabels[item.status] || item.status} salvo.`, "success");
    $("#record-dialog").close();
  } catch (error) { message(error.message, "error"); }
});
$("#send-review").addEventListener("click", async () => {
  try {
    let item = state.record;
    const payload = formPayload();
    if (!item || payloadToText(payload) !== payloadToText(item)) item = await saveRecord();
    if (item.status !== "rascunho") throw new Error("Para iniciar uma revisão, salve uma correção como rascunho primeiro.");
    const result = await api(`/api/admin/records/${item.id}/review`, { method: "POST", body: JSON.stringify({ reason: payload.reason }) });
    state.record = result.item;
    $("#record-dialog").close();
    message(`${item.title}: enviado para revisão.`, "success");
    await Promise.all([loadRecords(), loadOverview()]);
  } catch (error) { message(error.message, "error"); }
});

$("#record-publish").addEventListener("click", async () => {
  try {
    const before = state.record;
    const payload = formPayload();
    if (before?.current_official && payloadToText(payload) === payloadToText(before)) {
      throw new Error("Faça uma alteração antes de publicar uma atualização.");
    }
    const item = await saveRecord();
    if (item.status !== "rascunho" && item.status !== "em_revisao") {
      throw new Error("A atualização precisa estar salva como rascunho ou em revisão antes da publicação.");
    }
    $("#record-dialog").close();
    buildPreview(item);
  } catch (error) { message(error.message, "error"); }
});

$("#publish-confirm").addEventListener("click", async () => {
  const id = $("#publish-confirm").dataset.id;
  const expected = $("#publish-confirm").dataset.updatedAt;
  try {
    const result = await api(`/api/admin/records/${id}/publish`, {
      method: "POST", body: JSON.stringify({ confirm: true, expected_updated_at: expected }),
    });
    $("#publish-dialog").close();
    message(`${result.item.title}: versão ${result.item.version} publicada como oficial.`, "success");
    await Promise.all([loadRecords(), loadOverview()]);
  } catch (error) { message(error.message, "error"); }
});

for (const host of [$("#record-list"), $("#recent-records")]) {
  host.addEventListener("click", async event => {
    const control = event.target.closest("[data-action]");
    if (!control) return;
    try { await runAction(control.dataset.action, Number(control.dataset.id)); }
    catch (error) { message(error.message, "error"); }
  });
}

(async function init() {
  try {
    await api("/api/admin/session");
    showApp();
    await loadAll();
  } catch (error) {
    showLogin(error.message.includes("REPRESENTANTE_TOKEN") ? error.message : "Entre para acessar o painel administrativo.");
  }
})();
