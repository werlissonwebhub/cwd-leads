"use strict";

// Ícones simples (traço), no estilo Feather.
const ICONES = {
  estrela: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  local: '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  telefone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
  whatsapp: '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
  instagram: '<rect x="2" y="2" width="20" height="20" rx="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/>',
  pesquisa: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  site: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  mapa: '<polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>',
};

const ETIQUETAS = { sem_site: "Sem site", rede_social: "Só rede social", tem_site: "Tem site" };

const $ = (id) => document.getElementById(id);
const numero = new Intl.NumberFormat("pt-BR");
const nota = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

// Aparelho (não o tamanho da tela): decide como abrir o WhatsApp e o telefone.
const EH_IPHONE = /iPhone|iPad|iPod/i.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const EH_ANDROID = /Android/i.test(navigator.userAgent);
const EH_CELULAR = EH_IPHONE || EH_ANDROID;
const TELA_PEQUENA = window.matchMedia("(max-width: 760px)");

// Os resultados ficam só aqui, na memória da página (nada é salvo).
const estado = {
  resultados: [], busca: "", filtros: new Set(), buscando: false, esgotado: false,
  usoVeioDaBusca: false, // a resposta da busca traz o contador mais novo
  loginNecessario: false,
};

function el(tag, classe, texto) {
  const elemento = document.createElement(tag);
  if (classe) elemento.className = classe;
  if (texto !== undefined) elemento.textContent = texto;
  return elemento;
}

function icone(nome) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icone");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONES[nome];
  return svg;
}

function plural(n, singular, varios) {
  return `${numero.format(n)} ${n === 1 ? singular : varios}`;
}

function comMaiuscula(texto) {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

// ---------- Conversa com o servidor ----------

async function chamarApi(caminho, corpo) {
  const opcoes = { credentials: "same-origin" };
  if (corpo !== undefined) {
    opcoes.method = "POST";
    opcoes.headers = { "Content-Type": "application/json" };
    opcoes.body = JSON.stringify(corpo);
  }
  const resposta = await fetch(caminho, opcoes);
  const dados = await resposta.json().catch(() => ({}));
  const detalhe = dados.detail && !Array.isArray(dados.detail) && typeof dados.detail === "object" ? dados.detail : {};
  if (resposta.status === 401 && detalhe.login) mostrarLogin("Sua sessão terminou. Entre de novo.");
  return { ok: resposta.ok, status: resposta.status, dados, detalhe };
}

// ---------- Login ----------

function mostrarMensagemLogin(texto) {
  $("mensagem-login").textContent = texto;
  $("mensagem-login").hidden = !texto;
}

function mostrarLogin(aviso = "") {
  limparResultados();
  $("tela-app").hidden = true;
  $("tela-login").hidden = false;
  $("senha").value = "";
  mostrarMensagemLogin(aviso);
  $("senha").focus();
}

function mostrarApp() {
  $("tela-login").hidden = true;
  $("tela-app").hidden = false;
  $("rodape").hidden = !estado.loginNecessario;
  carregarUso();
  avisarComoInstalar();
}

async function entrar(evento) {
  evento.preventDefault();
  const botao = $("botao-entrar");
  botao.disabled = true;
  botao.textContent = "Entrando…";
  try {
    const { ok, detalhe } = await chamarApi("/api/login", { senha: $("senha").value });
    if (ok) {
      estado.loginNecessario = true;
      mostrarApp();
      return;
    }
    mostrarMensagemLogin(detalhe.mensagem ? comMaiuscula(detalhe.mensagem) : "Não foi possível entrar.");
    $("senha").select();
  } catch {
    mostrarMensagemLogin("Sem conexão com o servidor. Confira a internet.");
  } finally {
    botao.disabled = false;
    botao.textContent = "Entrar";
  }
}

async function sair() {
  try {
    await chamarApi("/api/sair", {});
  } catch {
    // mesmo sem resposta, volta para a tela de login
  }
  mostrarLogin("Você saiu deste aparelho.");
}

// ---------- Contador de consultas ----------

function mostrarUso(uso) {
  $("uso-hoje").textContent = uso.hoje;
  $("uso-limite").textContent = uso.limite_dia;
  $("uso-barra").style.width = `${Math.min(100, (uso.hoje / Math.max(uso.limite_dia, 1)) * 100)}%`;
  $("uso").title = `No mês: ${uso.mes} de ${uso.limite_mes} consultas`;
  estado.esgotado = uso.hoje >= uso.limite_dia || uso.mes >= uso.limite_mes;
  $("uso").classList.toggle("esgotado", estado.esgotado);
  atualizarBotao();
}

function atualizarBotao() {
  const botao = $("botao-buscar");
  botao.disabled = estado.buscando || estado.esgotado;
  botao.classList.toggle("girando", estado.buscando);
  botao.textContent = estado.buscando ? "Buscando…" : estado.esgotado ? "Limite atingido" : "Buscar";
}

async function carregarUso() {
  try {
    const { ok, status, dados, detalhe } = await chamarApi("/api/uso");
    if (status === 401) return; // a tela de login já apareceu
    if (!ok) throw new Error(detalhe.mensagem);
    if (!estado.usoVeioDaBusca) mostrarUso(dados);
  } catch (erro) {
    mostrarMensagem(erro.message ? comMaiuscula(erro.message) : "Não consegui ler o contador de consultas.");
  }
}

// ---------- Mensagens ----------

function mostrarMensagem(texto) {
  $("mensagem").textContent = texto;
  $("mensagem").hidden = false;
}

function esconderMensagem() {
  $("mensagem").hidden = true;
}

// ---------- Busca ----------

async function buscar(evento) {
  evento.preventDefault();
  const pedido = {
    nicho: $("nicho").value.trim(),
    cidade: $("cidade").value.trim(),
    paginas: Number($("paginas").value),
  };
  estado.buscando = true;
  atualizarBotao();
  esconderMensagem();
  try {
    const { ok, status, dados, detalhe } = await chamarApi("/api/buscar", pedido);
    if (dados.uso || detalhe.uso) estado.usoVeioDaBusca = true;
    if (!ok) {
      if (status === 401 && detalhe.login) return; // a tela de login já apareceu
      if (detalhe.uso) mostrarUso(detalhe.uso);
      mostrarMensagem(
        detalhe.mensagem ? comMaiuscula(detalhe.mensagem) : "Confira o nicho e a cidade (mínimo de 2 letras cada)."
      );
      return;
    }
    estado.resultados = dados.resultados;
    estado.busca = dados.busca;
    mostrarUso(dados.uso);
    desenhar();
    recolherBusca(pedido);
  } catch {
    mostrarMensagem("Não consegui falar com o servidor. Confira a internet.");
  } finally {
    estado.buscando = false;
    atualizarBotao();
  }
}

// No celular, depois de buscar, o formulário vira uma barra compacta no topo.
function recolherBusca(pedido) {
  if (!TELA_PEQUENA.matches) return;
  $("form-busca").classList.add("recolhida");
  $("busca-compacta-texto").textContent = `${pedido.nicho} · ${pedido.cidade}`;
  $("busca-compacta").hidden = false;
  document.activeElement?.blur(); // fecha o teclado
  window.scrollTo({ top: 0 });
}

function abrirBusca() {
  $("form-busca").classList.remove("recolhida");
  $("busca-compacta").hidden = true;
  window.scrollTo({ top: 0 });
  $("nicho").focus();
}

function limparResultados() {
  estado.resultados = [];
  estado.busca = "";
  $("lista").replaceChildren();
  $("resultados").hidden = true;
  $("filtros").hidden = true;
  $("inicio").hidden = false;
  $("form-busca").classList.remove("recolhida");
  $("busca-compacta").hidden = true;
}

// ---------- Filtros ----------

function filtrar(lista) {
  const notaMinima = Number($("nota-min").value);
  const avaliacoesMinimas = Math.max(0, Number($("avaliacoes-min").value) || 0);
  const filtrados = lista.filter(
    (r) =>
      (estado.filtros.size === 0 || estado.filtros.has(r.situacao_site)) &&
      (r.nota ?? 0) >= notaMinima &&
      r.avaliacoes >= avaliacoesMinimas
  );
  // "Prioridade" já vem ordenada do servidor.
  if ($("ordem").value === "avaliacoes") {
    filtrados.sort((a, b) => b.avaliacoes - a.avaliacoes || (b.nota ?? 0) - (a.nota ?? 0));
  }
  return filtrados;
}

function alternarFiltro(evento) {
  const chip = evento.currentTarget;
  const filtro = chip.dataset.filtro;
  if (estado.filtros.has(filtro)) estado.filtros.delete(filtro);
  else estado.filtros.add(filtro);
  chip.setAttribute("aria-pressed", estado.filtros.has(filtro));
  desenhar();
}

function alternarMaisFiltros() {
  const aberto = $("filtros-extras").classList.toggle("aberto");
  $("botao-mais-filtros").setAttribute("aria-expanded", aberto);
}

function atualizarRotuloMaisFiltros() {
  const ativos = [
    Number($("nota-min").value) > 0,
    Number($("avaliacoes-min").value) > 0,
    $("ordem").value !== "prioridade",
  ].filter(Boolean).length;
  $("botao-mais-filtros").textContent = ativos ? `Mais filtros (${ativos})` : "Mais filtros";
}

// ---------- Cards ----------

function botaoLink(url, texto, nomeIcone, dica, classeExtra = "", novaAba = true) {
  const link = el("a", `botao-acao ${classeExtra}`.trim());
  link.href = url;
  if (novaAba) {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
  link.title = dica;
  link.append(icone(nomeIcone), texto);
  return link;
}

// No celular, abre direto o app do WhatsApp; no computador, o wa.me.
function botaoWhatsapp(r) {
  const dica = r.whatsapp_provavel ? "Provável WhatsApp (número de celular)" : "WhatsApp informado pelo lugar";
  if (EH_ANDROID && r.whatsapp_numero) {
    // Intent do Android: abre o app; se não houver WhatsApp instalado, o Chrome abre o wa.me.
    const intent = `intent://send?phone=${r.whatsapp_numero}#Intent;scheme=whatsapp;` +
      `S.browser_fallback_url=${encodeURIComponent(r.whatsapp)};end`;
    return botaoLink(intent, "WhatsApp", "whatsapp", dica, "botao-whatsapp", false);
  }
  if (EH_IPHONE && r.whatsapp_numero) {
    return botaoLink(`whatsapp://send?phone=${r.whatsapp_numero}`, "WhatsApp", "whatsapp", dica, "botao-whatsapp", false);
  }
  return botaoLink(r.whatsapp, "WhatsApp", "whatsapp", dica, "botao-whatsapp");
}

function linhaInfo(nomeIcone, conteudo) {
  const linha = el("p", "card-info");
  const texto = el("span");
  texto.append(conteudo);
  linha.append(icone(nomeIcone), texto);
  return linha;
}

function criarCard(r) {
  const card = el("article", "card");
  card.dataset.placeId = r.place_id; // para salvar leads na próxima etapa

  card.append(el("span", `etiqueta etiqueta-${r.situacao_site}`, ETIQUETAS[r.situacao_site]));
  card.append(el("h3", "card-nome", r.nome));

  const avaliacao = el("p", "card-nota");
  if (r.nota != null) {
    avaliacao.append(icone("estrela"), el("strong", "", nota.format(r.nota)));
    avaliacao.append(el("span", "suave", `· ${plural(r.avaliacoes, "avaliação", "avaliações")}`));
  } else {
    avaliacao.append(el("span", "suave", "Sem avaliações"));
  }
  card.append(avaliacao);

  card.append(linhaInfo("local", r.endereco || "Endereço não informado"));
  let numeroTelefone = r.telefone || "Sem telefone";
  if (EH_CELULAR && r.telefone_link) {
    numeroTelefone = el("a", "", r.telefone); // toque para ligar
    numeroTelefone.href = r.telefone_link;
  }
  const telefone = linhaInfo("telefone", numeroTelefone);
  if (r.whatsapp_provavel) telefone.lastElementChild.append(el("span", "selo", "provável WhatsApp"));
  card.append(telefone);

  const acoes = el("div", "card-acoes");
  if (r.whatsapp) acoes.append(botaoWhatsapp(r));
  if (r.instagram_perfil) {
    acoes.append(botaoLink(r.instagram, "Instagram", "instagram", "Abrir o perfil no Instagram"));
  } else {
    acoes.append(botaoLink(r.instagram, "Instagram", "pesquisa", "Procurar o Instagram no Google"));
  }
  if (r.site) acoes.append(botaoLink(r.site, "Site", "site", "Abrir o site"));
  if (r.maps) acoes.append(botaoLink(r.maps, "Maps", "mapa", "Abrir no Google Maps"));
  card.append(acoes);

  return card;
}

function desenhar() {
  const todos = estado.resultados;
  const visiveis = filtrar(todos);
  const contar = (situacao) => todos.filter((r) => r.situacao_site === situacao).length;

  let resumo =
    `${plural(todos.length, "resultado", "resultados")} para “${estado.busca}” · ` +
    `${numero.format(contar("sem_site"))} sem site · ${numero.format(contar("rede_social"))} só rede social`;
  if (visiveis.length !== todos.length) resumo += ` · mostrando ${numero.format(visiveis.length)}`;
  $("resumo").textContent = resumo;

  const lista = $("lista");
  lista.replaceChildren(...visiveis.map(criarCard));
  if (!visiveis.length) {
    const texto = todos.length
      ? "Nenhum resultado com esses filtros."
      : "O Google não encontrou nada para essa busca. Tente outras palavras.";
    lista.append(el("p", "lista-vazia", texto));
  }

  atualizarRotuloMaisFiltros();
  $("inicio").hidden = true;
  $("filtros").hidden = false;
  $("resultados").hidden = false;
}

// ---------- Instalar na tela inicial (PWA) ----------

let pedidoDeInstalacao = null;

function avisoFechado() {
  try {
    return localStorage.getItem("cwd-aviso-instalar-fechado") === "1";
  } catch {
    return false;
  }
}

function fecharAviso() {
  $("aviso-instalar").hidden = true;
  try {
    localStorage.setItem("cwd-aviso-instalar-fechado", "1");
  } catch {
    // sem armazenamento: o aviso só volta na próxima visita
  }
}

function mostrarAvisoInstalar(texto, comBotao) {
  if (avisoFechado()) return;
  $("aviso-instalar-texto").textContent = texto;
  $("botao-instalar").hidden = !comBotao;
  $("aviso-instalar").hidden = false;
}

function avisarComoInstalar() {
  const instalado = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  // O iPhone não tem botão automático de instalar: mostra o caminho manual.
  if (!instalado && EH_IPHONE) {
    mostrarAvisoInstalar("Para instalar: toque em Compartilhar e depois em “Adicionar à Tela de Início”.", false);
  }
}

// Android/Chrome: o navegador avisa que dá para instalar; mostramos o botão.
window.addEventListener("beforeinstallprompt", (evento) => {
  if (EH_IPHONE) return; // no iPhone vale o caminho manual (Compartilhar)
  evento.preventDefault();
  pedidoDeInstalacao = evento;
  mostrarAvisoInstalar("Instale o CWD Leads como app.", true);
});

window.addEventListener("appinstalled", () => {
  $("aviso-instalar").hidden = true;
});

async function instalar() {
  if (!pedidoDeInstalacao) return;
  pedidoDeInstalacao.prompt();
  await pedidoDeInstalacao.userChoice;
  pedidoDeInstalacao = null;
  $("aviso-instalar").hidden = true;
}

// ---------- Início ----------

async function iniciar() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  try {
    const { ok, dados, detalhe } = await chamarApi("/api/sessao");
    if (!ok) {
      mostrarLogin(detalhe.mensagem ? comMaiuscula(detalhe.mensagem) : "Não consegui verificar o acesso.");
      return;
    }
    estado.loginNecessario = dados.login_necessario;
    if (dados.logado) mostrarApp();
    else mostrarLogin();
  } catch {
    mostrarLogin("Sem conexão com o servidor. Confira a internet e recarregue a página.");
  }
}

$("form-login").addEventListener("submit", entrar);
$("botao-sair").addEventListener("click", sair);
$("form-busca").addEventListener("submit", buscar);
$("busca-compacta").addEventListener("click", abrirBusca);
$("botao-mais-filtros").addEventListener("click", alternarMaisFiltros);
$("botao-instalar").addEventListener("click", instalar);
$("fechar-aviso").addEventListener("click", fecharAviso);
document.querySelectorAll(".chip[data-filtro]").forEach((chip) => chip.addEventListener("click", alternarFiltro));
["nota-min", "ordem"].forEach((id) => $(id).addEventListener("change", desenhar));
$("avaliacoes-min").addEventListener("input", desenhar);
TELA_PEQUENA.addEventListener("change", (evento) => {
  if (!evento.matches) {
    $("form-busca").classList.remove("recolhida");
    $("busca-compacta").hidden = true;
  }
});

// Avisa antes de fechar/recarregar: os resultados (que gastaram consultas) se perderiam.
window.addEventListener("beforeunload", (evento) => {
  if (estado.resultados.length) evento.preventDefault();
});

iniciar();
