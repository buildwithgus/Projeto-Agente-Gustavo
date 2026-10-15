const CATEGORIAS = {
  "Avisos": "Tem algum aviso importante da turma?",
  "Calendário": "Quando é o próximo feriado ou recesso?",
  "Esta semana": "O que tenho essa semana?",
  "Provas": "Quais provas eu tenho e quando são?",
  "Trabalhos": "Quais trabalhos tenho para entregar?",
  "Aulas": "Onde são as aulas dessa semana?",
  "Extensão Universitária": "Quais as informações de extensão universitária?",
  "Resumo": "Me explica rapidamente o que é "
};
const chat = document.getElementById("chat"), q = document.getElementById("q"), ok = document.getElementById("ok");
const brainStatusDot = document.getElementById("brain-status-dot");
const brainStatusLabel = document.getElementById("brain-status-label");
const brainStateCaption = document.getElementById("brain-state-caption");
const brainStateMap = {
  idle: { label: "IDLE", caption: "Cérebro em repouso", color: "#7ad8ff" },
  listening: { label: "LISTENING", caption: "Capturando voz", color: "#79d0ff" },
  processing: { label: "PROCESSING", caption: "Pulsos elétricos ativos", color: "#56d6fc" },
  retrieving: { label: "RETRIEVING", caption: "Consultando base acadêmica", color: "#78c2ff" },
  responding: { label: "RESPONDING", caption: "Estrutura respondendo", color: "#6ee7ff" },
  error: { label: "ERROR", caption: "Falha na operação", color: "#ff7c7c" }
};
let historico = JSON.parse(localStorage.getItem("caio_hist") || localStorage.getItem("rai_hist") || "[]");

function appendInlineMarkdown(parent, text) {
  const pattern = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  let inicio = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(inicio, match.index)));
    const token = match[0];
    const tag = token.startsWith("**") ? "strong" : token.startsWith("*") ? "em" : "code";
    const deslocamento = tag === "strong" ? 2 : 1;
    const elemento = document.createElement(tag);
    elemento.textContent = token.slice(deslocamento, -deslocamento);
    parent.append(elemento);
    inicio = match.index + token.length;
  }
  parent.append(document.createTextNode(text.slice(inicio)));
}

function fmt(markdown) {
  const fragmento = document.createDocumentFragment();
  const textoSeguro = String(markdown ?? "").replace(/\uE200(?:filecite|cite)\uE200turn\d+(?:file|search|news|video)\d+(?:\uE200turn\d+(?:file|search|news|video)\d+)*\uE201/g, "");
  const linhas = textoSeguro.replace(/\r\n?/g, "\n").split("\n");
  let paragrafo = [];
  const listas = [];

  const finalizarParagrafo = () => {
    if (!paragrafo.length) return;
    const elemento = document.createElement("p");
    paragrafo.forEach((linha, indice) => {
      if (indice) elemento.append(document.createElement("br"));
      appendInlineMarkdown(elemento, linha);
    });
    fragmento.append(elemento);
    paragrafo = [];
  };

  for (const linha of linhas) {
    if (!linha.trim()) {
      finalizarParagrafo();
      listas.length = 0;
      continue;
    }

    const titulo = linha.match(/^(#{1,3})\s+(.+?)\s*#*$/);
    const tituloNegrito = linha.match(/^\s*\*\*(.+)\*\*\s*$/);
    if (titulo || tituloNegrito) {
      finalizarParagrafo();
      listas.length = 0;
      const nivel = titulo ? Math.min(titulo[1].length + 1, 4) : 3;
      const elemento = document.createElement(`h${nivel}`);
      appendInlineMarkdown(elemento, titulo ? titulo[2] : tituloNegrito[1]);
      fragmento.append(elemento);
      continue;
    }

    const item = linha.match(/^(\s*)([-*+]|\d+[.)])\s+(.+)$/);
    if (item) {
      finalizarParagrafo();
      const indentacao = item[1].replace(/\t/g, "  ").length;
      const proximoTipo = /^\d/.test(item[2]) ? "ol" : "ul";
      while (listas.length && indentacao < listas[listas.length - 1].indentacao) listas.pop();

      let nivelLista = listas[listas.length - 1];
      if (!nivelLista || indentacao > nivelLista.indentacao) {
        const recipiente = nivelLista?.ultimoItem || fragmento;
        nivelLista = { indentacao, tipo: proximoTipo, elemento: document.createElement(proximoTipo), recipiente, ultimoItem: null };
        recipiente.append(nivelLista.elemento);
        listas.push(nivelLista);
      } else if (nivelLista.tipo !== proximoTipo) {
        listas.pop();
        const recipiente = nivelLista.recipiente;
        nivelLista = { indentacao, tipo: proximoTipo, elemento: document.createElement(proximoTipo), recipiente, ultimoItem: null };
        recipiente.append(nivelLista.elemento);
        listas.push(nivelLista);
      }
      const elemento = document.createElement("li");
      appendInlineMarkdown(elemento, item[3]);
      nivelLista.elemento.append(elemento);
      nivelLista.ultimoItem = elemento;
      continue;
    }

    listas.length = 0;
    paragrafo.push(linha);
  }

  finalizarParagrafo();
  return fragmento;
}

function setBrainState(state) {
  const config = brainStateMap[state] || brainStateMap.idle;
  if (brainStatusDot) brainStatusDot.style.background = config.color;
  if (brainStatusLabel) brainStatusLabel.textContent = config.label;
  if (brainStateCaption) brainStateCaption.textContent = config.caption;
  if (window.brainVisualizer && typeof window.brainVisualizer.setState === "function") {
    window.brainVisualizer.setState(state);
  }
}

function bolha(papel, texto, pendente, acompanhar = true) {
  const estavaNoFim = chat.scrollHeight - chat.clientHeight - chat.scrollTop < 80;
  const row = document.createElement("div");
  row.className = "msg-row " + papel;

  if (papel === "bot") {
    const avatar = document.createElement("img");
    avatar.src = "/static/avatar%20caio.png";
    avatar.alt = "Logo do C.A.I.O";
    avatar.className = "bot-avatar";
    row.appendChild(avatar);
  }

  const d = document.createElement("div");
  d.className = "msg" + (pendente ? " pendente" : "");
  d.append(fmt(texto));
  if (pendente) {
    const aviso = document.createElement("small");
    aviso.textContent = "Dúvida sinalizada ao representante.";
    d.append(aviso);
  }
  row.appendChild(d);
  chat.appendChild(row);
  if (acompanhar || estavaNoFim) chat.scrollTop = chat.scrollHeight;
}
function salvar() { localStorage.setItem("caio_hist", JSON.stringify(historico.slice(-40))); }

async function perguntar(texto) {
  bolha("user", texto); ok.disabled = true;
  setBrainState("processing");
  try {
    setBrainState("retrieving");
    const r = await fetch("/api/perguntar", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({pergunta: texto, historico})});
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "Erro");
    setBrainState("responding");
    bolha("bot", j.resposta, !j.respondida, false);
    historico.push({role: "user", content: texto}, {role: "assistant", content: j.resposta}); salvar();
  } catch (e) {
    setBrainState("error");
    bolha("bot", "Não consegui responder agora: " + e.message, false, false);
  }
  ok.disabled = false; q.focus();
  window.setTimeout(() => setBrainState("idle"), 650);
}

document.getElementById("form").onsubmit = e => { e.preventDefault(); const t = q.value.trim(); if (t) { q.value = ""; perguntar(t); } };
const chips = document.getElementById("chips");
for (const [nome, frase] of Object.entries(CATEGORIAS)) {
  const b = document.createElement("button"); b.type = "button"; b.textContent = nome;
  b.onclick = () => frase.endsWith("é ") ? (q.value = frase, q.focus()) : perguntar(frase);
  chips.appendChild(b);
}
if (historico.length) historico.forEach(m => bolha(m.role === "user" ? "user" : "bot", m.content, false, false));
else bolha("bot", "Olá! Sou o C.A.I.O, seu assistente acadêmico inteligente. Estou aqui para facilitar a rotina da representação de turma, ajudando você a consultar informações acadêmicas de forma rápida e organizada.\n\nVocê pode perguntar sobre avisos, calendário acadêmico, atividades desta semana, provas, trabalhos, aulas, extensão universitária e resumos das informações da turma.\n\nComo posso ajudar hoje?");
chat.scrollTop = chat.scrollHeight;
setBrainState("idle");
