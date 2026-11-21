// Roda junto com o ciclo do bot: mantém o WhatsApp conectado, posta no grupo
// o que o bot coloca na fila (ofertas e cupons já publicados no Telegram) e
// apaga links que outras pessoas mandarem no grupo.
//
// Ritmo (para não parecer robô): no máximo WA_MAX_DIA posts por dia, espalhados pelo dia, com um intervalo
// sorteado entre WA_INTERVALO_MIN e WA_INTERVALO_MAX minutos (padrão 4 a 13), "digitando..." antes de cada um.
import fs from "node:fs";
import path from "node:path";

import makeWASocket, { Browsers, DisconnectReason, prepareWAMessageMedia, useMultiFileAuthState } from "@whiskeysockets/baileys";
import pino from "pino";

import { PASTA_AUTH, RAIZ, abrirSessao, anotarHistorico, anotarRadar, avisar, codigoConvite, cotaAteAgora, dormir, gravarEstado,
  guardarSessao, lerEstado, naMeiaNoite, ordenarFila, sortearIntervalo } from "./comum.mjs";

const FILA = path.resolve(RAIZ, process.env.WA_FILA || "fila_wa");
// Aquecimento automático: o ritmo sobe sozinho conforme o número ganha
// histórico. WA_MAX_DIA (variável do GitHub) trava um valor fixo.
const RAMPA = [ // [a partir do dia, posts por dia]; 21/11: o Leonardo pediu para acelerar (número conectado em 10/11)
  [0, 4], [4, 10], [8, 14], [11, 20], [18, 25], [25, 30],
];
const VALIDADE_ITEM = 3 * 60 * 60 * 1000; // oferta parada há mais de 3h na fila não sai
const FIM = Date.now() + Number(process.env.WA_HORAS || 5.6) * 3600 * 1000;
const HORA_INICIO = Number(process.env.WA_HORA_INICIO || 7);
const HORA_FIM = Number(process.env.WA_HORA_FIM || 23);
const horaLocal = () => Number(new Intl.DateTimeFormat("en-US", { timeZone: "America/Sao_Paulo", hour: "numeric",
  hourCycle: "h23" }).format(new Date()));
const MEIA_NOITE_EXTRA = 6; // posts da virada (Black Friday, 12.12) que não entram na conta do dia
const deDia = () => (horaLocal() >= HORA_INICIO && horaLocal() < HORA_FIM) || naMeiaNoite();
const RE_LINK = /(https?:\/\/|www\.|chat\.whatsapp\.com|\b[\w-]+\.(com|com\.br|net|ly|me)\/)/i;

let temSessao = false;
try {
  temSessao = abrirSessao();
} catch (e) {
  console.log("WhatsApp: não consegui abrir a sessão salva (a chave mudou?). Rode o “Conectar WhatsApp” de novo.");
  await avisar("⚠️ Não consegui abrir a sessão do WhatsApp. Rode o “Conectar WhatsApp” de novo.");
  process.exit(0);
}
if (!temSessao) {
  console.log("WhatsApp: ainda não conectado (rode o workflow “Conectar WhatsApp”).");
  process.exit(0);
}
fs.mkdirSync(FILA, { recursive: true });

const estado = lerEstado();
estado.inicio = estado.inicio || new Date().toISOString();
const diasConectado = Math.floor((Date.now() - Date.parse(estado.inicio)) / 86400000);
const degrau = RAMPA.filter(([d]) => diasConectado >= d).pop();
const MAX_DIA = Number(process.env.WA_MAX_DIA || degrau[1]);
const INTERVALO_MIN = Number(process.env.WA_INTERVALO_MIN || 4);
const INTERVALO_MAX = Math.max(INTERVALO_MIN, Number(process.env.WA_INTERVALO_MAX || 13));
estado.max_dia = MAX_DIA; // para o comando "fila" e a página da fila mostrarem o ritmo de hoje
estado.intervalo_min = INTERVALO_MIN;
estado.intervalo_max = INTERVALO_MAX;
const minutoLocal = () => Number(new Intl.DateTimeFormat("en-US", { timeZone: "America/Sao_Paulo", minute: "numeric" })
  .format(new Date()));
console.log(`WhatsApp: dia ${diasConectado + 1} conectado; até ${MAX_DIA} posts hoje, de ${INTERVALO_MIN} a ` +
  `${INTERVALO_MAX} min entre eles, espalhados das ${HORA_INICIO}h às ${HORA_FIM}h.`);
const hoje = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());
const { state, saveCreds } = await useMultiFileAuthState(PASTA_AUTH);
const logger = pino({ level: "silent" });
let sock = null, aberto = false, encerrando = false, tentativas = 0, dormindo = false;
let grupo = estado.grupo || null;
const admins = { quando: 0, lista: new Set() };

function salvarTudo() {
  try {
    guardarSessao();
  } catch (e) {
    console.log("Aviso: não salvei a sessão:", e?.message);
  }
  gravarEstado({ ...estado, grupo });
}

async function acharGrupo() {
  if (grupo) return grupo;
  const cod = codigoConvite(process.env.WHATSAPP_GRUPO);
  if (!cod) throw new Error("WHATSAPP_GRUPO sem link de convite");
  grupo = (await sock.groupGetInviteInfo(cod)).id;
  salvarTudo();
  return grupo;
}

async function contarMembros() {
  if (!grupo || !aberto) return;
  try {
    const meta = await sock.groupMetadata(grupo);
    estado.membros = estado.membros || {};
    estado.membros[hoje()] = meta.participants.length;
    const dias = Object.keys(estado.membros).sort();
    for (const d of dias.slice(0, -10)) delete estado.membros[d];
    estado.membros_em = new Date().toISOString();
  } catch (e) {
    console.log("Aviso: não consegui contar os membros do grupo:", e?.message);
  }
}

async function ehAdmin(jid) {
  if (Date.now() - admins.quando > 10 * 60 * 1000) {
    const meta = await sock.groupMetadata(grupo);
    admins.lista = new Set(meta.participants.filter((p) => p.admin).flatMap((p) => [p.id, p.lid, p.jid].filter(Boolean)));
    admins.quando = Date.now();
  }
  return admins.lista.has(jid);
}

function conectar() {
  sock = makeWASocket({ auth: state, logger, browser: Browsers.macOS("Chrome"), markOnlineOnConnect: false,
    syncFullHistory: false });
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", async (u) => {
    if (u.connection === "open") {
      aberto = true;
      tentativas = 0;
      console.log("WhatsApp conectado.");
      estado.conectado = true;
      if (estado.avisou_queda && estado.caiu_em) {
        const fora = Math.round((Date.now() - Date.parse(estado.caiu_em)) / 60000);
        await avisar(`✅ O WhatsApp do Chocalho voltou a conectar (ficou ${fora} min fora). Os posts no grupo seguem normais.`);
      }
      estado.caiu_em = null;
      estado.avisou_queda = false;
      try {
        await acharGrupo();
        await contarMembros();
      } catch (e) {
        console.log("Aviso: não achei o grupo:", e?.message);
      }
    }
    if (u.connection === "close") {
      aberto = false;
      if (encerrando || dormindo) return;
      const motivo = u.lastDisconnect?.error?.output?.statusCode;
      if (motivo === DisconnectReason.loggedOut) {
        console.log("WhatsApp desconectado pelo celular.");
        estado.conectado = false;
        if (estado.avisou_desconexao !== hoje()) {
          estado.avisou_desconexao = hoje();
          await avisar("⚠️ O WhatsApp do Chocalho foi desconectado. Para voltar, rode o workflow “Conectar WhatsApp”.");
        }
        fs.rmSync(path.join(RAIZ, "data", "wa_sessao.enc"), { force: true });
        gravarEstado({ ...estado, grupo });
        process.exit(0);
      }
      tentativas += 1;
      estado.caiu_em = estado.caiu_em || new Date().toISOString();
      const espera = Math.min(60000 * tentativas, 10 * 60000);
      console.log(`Conexão caiu (${motivo}); tentando de novo em ${Math.round(espera / 1000)}s.`);
      setTimeout(conectar, espera);
    }
  });
  // Radar do grupo: quem entra e quem sai, por hora (só a contagem)
  sock.ev.on("group-participants.update", ({ id, participants, action }) => {
    if (id !== grupo) return;
    const tipo = action === "add" ? "entrou" : action === "remove" ? "saiu" : null;
    if (tipo) anotarRadar(estado, tipo, (participants || []).length, hoje(), horaLocal());
  });
  // Anti-link: apaga links de quem não é administrador
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify" || !grupo) return;
    for (const m of messages) {
      if (m.key.remoteJid !== grupo || m.key.fromMe) continue;
      anotarRadar(estado, "mensagem", 1, hoje(), horaLocal());
      const msg = m.message || {};
      const texto = msg.conversation || msg.extendedTextMessage?.text || msg.imageMessage?.caption ||
        msg.videoMessage?.caption || "";
      if (!RE_LINK.test(texto)) continue;
      const autor = m.key.participant || m.participant;
      try {
        if (autor && !(await ehAdmin(autor))) {
          await sock.sendMessage(grupo, { delete: m.key });
          estado.apagados = estado.apagados || {};
          estado.apagados[hoje()] = (estado.apagados[hoje()] || 0) + 1;
          console.log("Link de participante apagado.");
        }
      } catch (e) {
        console.log("Aviso: não consegui apagar um link:", e?.message);
      }
    }
  });
}

// Arte gerada pelo bot fica na própria pasta da fila; some junto com o item
function apagarItem(caminho, item) {
  fs.rmSync(caminho, { force: true });
  const img = item?.imagem;
  if (img && !/^https?:/i.test(img) && path.resolve(img).startsWith(FILA)) fs.rmSync(img, { force: true });
}

// Menção oculta: todos do grupo recebem a notificação de menção, sem "@" no texto.
// Só em item com "mencionar" (comando `marcar` do Leonardo); nunca automático.
async function mencoes(item) {
  if (!item.mencionar) return {};
  try {
    const meta = await sock.groupMetadata(grupo);
    const ids = meta.participants.map((p) => p.id).filter(Boolean);
    return ids.length ? { mentions: ids } : {};
  } catch (e) {
    console.log("Aviso: não consegui ler os membros para a menção; vai sem marcar:", e?.message);
    return {};
  }
}

async function postar(item) {
  await acharGrupo();
  const extra = await mencoes(item);
  await sock.presenceSubscribe(grupo).catch(() => {});
  await sock.sendPresenceUpdate("composing", grupo).catch(() => {});
  await dormir(2500 + Math.random() * 4000);
  await sock.sendPresenceUpdate("paused", grupo).catch(() => {});
  // Texto com a prévia grande do link (foto + nome do produto), como nos grupos de ofertas grandes
  if (item.preview?.link && item.texto.includes(item.preview.link)) {
    try {
      const pv = item.preview;
      const info = { "canonical-url": pv.link, "matched-text": pv.link, title: pv.titulo || "", description: "" };
      if (pv.imagem) {
        const local = !/^https?:/i.test(pv.imagem);
        const { imageMessage } = await prepareWAMessageMedia({ image: local ? fs.readFileSync(pv.imagem) : { url: pv.imagem } },
          { upload: sock.waUploadToServer, mediaTypeOverride: "thumbnail-link", logger });
        info.jpegThumbnail = imageMessage?.jpegThumbnail ? Buffer.from(imageMessage.jpegThumbnail) : undefined;
        info.highQualityThumbnail = imageMessage || undefined;
      }
      await sock.sendMessage(grupo, { text: item.texto, linkPreview: info, ...extra });
      return;
    } catch (e) {
      console.log("Aviso: não consegui montar a prévia do link; vai como foto:", e?.message);
    }
  }
  if (item.imagem) {
    const local = !/^https?:/i.test(item.imagem);
    if (local && !fs.existsSync(item.imagem)) {
      await sock.sendMessage(grupo, { text: item.texto, ...extra });
    } else {
      await sock.sendMessage(grupo, { image: local ? fs.readFileSync(item.imagem) : { url: item.imagem },
        caption: item.texto, ...extra });
    }
  } else {
    await sock.sendMessage(grupo, { text: item.texto, ...extra });
  }
}

async function cuidarDaFila() {
  if (!aberto) return;
  let arquivos = ordenarFila(fs.readdirSync(FILA).filter((n) => n.endsWith(".json")).sort(), (n) => {
    try {
      return JSON.parse(fs.readFileSync(path.join(FILA, n), "utf8"));
    } catch {
      return {};
    }
  }, estado.ultima_loja || "ml", estado.ultima_categoria || null);
  let mudou = false;
  for (const nome of arquivos) {
    const caminho = path.join(FILA, nome);
    let item;
    try {
      item = JSON.parse(fs.readFileSync(caminho, "utf8"));
    } catch {
      fs.rmSync(caminho, { force: true });
      continue;
    }
    if (estado.dia !== hoje()) {
      estado.dia = hoje();
      estado.enviados = 0;
    }
    const virada = naMeiaNoite();
    if (estado.virada_dia !== hoje() && virada) {
      estado.virada_dia = hoje();
      estado.virada_enviados = 0;
    }
    const extraVirada = virada && (estado.virada_enviados || 0) < MEIA_NOITE_EXTRA;
    const velho = Date.now() - Date.parse(item.criado) > VALIDADE_ITEM;
    if (velho || (estado.enviados >= MAX_DIA && !extraVirada)) {
      anotarHistorico(estado, item, velho ? "venceu" : "limite", hoje());
      apagarItem(caminho, item); // velho demais ou limite do dia: não sai
      mudou = true;
      continue;
    }
    if (estado.proximo_em && Date.now() < Date.parse(estado.proximo_em)) break; // espera o intervalo sorteado
    if (!extraVirada && estado.enviados >= cotaAteAgora(MAX_DIA, horaLocal(), minutoLocal(), HORA_INICIO, HORA_FIM)) {
      break; // já saiu a parte do dia até agora: guarda o resto para a tarde e a noite
    }
    if (estado.pausado_ate && Date.now() < Date.parse(estado.pausado_ate)) {
      anotarHistorico(estado, item, "pausa", hoje());
      apagarItem(caminho, item); // em pausa de segurança: não posta
      mudou = true;
      continue;
    }
    try {
      await postar(item);
      anotarHistorico(estado, item, "enviado", hoje());
      if (extraVirada) estado.virada_enviados = (estado.virada_enviados || 0) + 1; // extra da data, fora da conta do dia
      else estado.enviados += 1;
      estado.ultimo = new Date().toISOString();
      estado.proximo_em = new Date(Date.now() + sortearIntervalo(INTERVALO_MIN, INTERVALO_MAX)).toISOString();
      estado.ultima_loja = item.loja || "ml";
      if (item.categoria) estado.ultima_categoria = item.categoria;
      console.log(`Postado no grupo do WhatsApp (${estado.enviados}/${MAX_DIA} hoje).`);
    } catch (e) {
      console.log("Aviso: não consegui postar no WhatsApp:", e?.message);
      anotarHistorico(estado, item, "erro", hoje());
      if (/463|timelock|restrict|forbidden|403/i.test(String(e?.message) + String(e?.output?.statusCode))) {
        estado.pausado_ate = new Date(Date.now() + 48 * 3600 * 1000).toISOString();
        await avisar("🛑 O WhatsApp sinalizou uma <b>restrição</b> no número do Chocalho. Pausei os posts no grupo " +
          "por 48h por segurança. Não use automação nem mande muitas mensagens nesse número enquanto isso.");
      }
    }
    apagarItem(caminho, item);
    salvarTudo();
    return; // um por vez
  }
  if (mudou) salvarTudo(); // descartes anotados no histórico: grava para a página da fila enxergar
}

async function encerrar() {
  if (encerrando) return;
  encerrando = true;
  try {
    await saveCreds();
  } catch {
    /* segue */
  }
  salvarTudo();
  try {
    sock?.end(undefined);
  } catch {
    /* segue */
  }
  process.exit(0);
}
process.on("SIGTERM", encerrar);
process.on("SIGINT", encerrar);

if (deDia()) conectar();
else dormindo = true;
let ultimoSalvo = Date.now();
while (Date.now() < FIM && !fs.existsSync(path.join(FILA, "PARAR"))) {
  if (!deDia() && !dormindo) {
    dormindo = true;
    salvarTudo();
    try {
      sock?.end(undefined);
    } catch {
      /* segue */
    }
    console.log("WhatsApp: desconectado durante a noite.");
  } else if (deDia() && dormindo) {
    dormindo = false;
    conectar();
  }
  if (dormindo) {
    for (const n of fs.readdirSync(FILA)) if (/\.(json|png)$/.test(n)) fs.rmSync(path.join(FILA, n), { force: true });
    await dormir(60000);
    continue;
  }
  if (!aberto && estado.caiu_em && !estado.avisou_queda && Date.now() - Date.parse(estado.caiu_em) > 10 * 60000) {
    estado.avisou_queda = true; // caiu e não voltou em 10 min: avisa uma vez; quando voltar, avisa de novo
    await avisar("⚠️ O WhatsApp do Chocalho caiu há mais de 10 min e está tentando reconectar sozinho. " +
      "Aviso quando voltar. Se passar de 1 h, rode o workflow “Conectar WhatsApp”.");
  }
  if (estado.pausado_ate && Date.now() >= Date.parse(estado.pausado_ate)) {
    estado.pausado_ate = null;
    await avisar("✅ Acabou a pausa de segurança do WhatsApp: o grupo volta a receber ofertas.");
  }
  await cuidarDaFila().catch((e) => console.log("Aviso:", e?.message));
  if (Date.now() - ultimoSalvo > 5 * 60 * 1000) {
    if (!estado.membros_em || Date.now() - Date.parse(estado.membros_em) > 60 * 60 * 1000) await contarMembros();
    salvarTudo();
    ultimoSalvo = Date.now();
  }
  await dormir(5000);
}
await encerrar();
