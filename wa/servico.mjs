// Roda junto com o ciclo do bot: mantém o WhatsApp conectado, posta no grupo
// o que o bot coloca na fila (ofertas e cupons já publicados no Telegram) e
// apaga links que outras pessoas mandarem no grupo.
//
// Ritmo (para não parecer robô): no máximo WA_MAX_DIA posts por dia, com pelo
// menos WA_INTERVALO_MIN minutos entre eles, "digitando..." antes de cada um.
import fs from "node:fs";
import path from "node:path";

import makeWASocket, { Browsers, DisconnectReason, prepareWAMessageMedia, useMultiFileAuthState } from "@whiskeysockets/baileys";
import pino from "pino";

import { PASTA_AUTH, RAIZ, abrirSessao, avisar, codigoConvite, dormir, gravarEstado, guardarSessao,
  lerEstado } from "./comum.mjs";

const FILA = path.resolve(RAIZ, process.env.WA_FILA || "fila_wa");
// Aquecimento automático: o ritmo sobe sozinho conforme o número ganha
// histórico. WA_MAX_DIA / WA_INTERVALO_MIN (variáveis do GitHub) travam um valor fixo.
const RAMPA = [ // [a partir do dia, posts por dia, minutos entre posts]
  [0, 4, 40], [7, 7, 30], [14, 10, 25], [21, 14, 20], [30, 20, 15],
];
const VALIDADE_ITEM = 3 * 60 * 60 * 1000; // oferta parada há mais de 3h na fila não sai
const FIM = Date.now() + Number(process.env.WA_HORAS || 5.6) * 3600 * 1000;
const HORA_INICIO = Number(process.env.WA_HORA_INICIO || 7);
const HORA_FIM = Number(process.env.WA_HORA_FIM || 23);
const horaLocal = () => Number(new Intl.DateTimeFormat("en-US", { timeZone: "America/Sao_Paulo", hour: "numeric",
  hourCycle: "h23" }).format(new Date()));
const deDia = () => horaLocal() >= HORA_INICIO && horaLocal() < HORA_FIM;
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
const INTERVALO = Number(process.env.WA_INTERVALO_MIN || degrau[2]) * 60 * 1000;
console.log(`WhatsApp: dia ${diasConectado + 1} conectado; até ${MAX_DIA} posts hoje, ${INTERVALO / 60000} min entre eles.`);
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
      const espera = Math.min(60000 * tentativas, 10 * 60000);
      console.log(`Conexão caiu (${motivo}); tentando de novo em ${Math.round(espera / 1000)}s.`);
      setTimeout(conectar, espera);
    }
  });
  // Anti-link: apaga links de quem não é administrador
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify" || !grupo) return;
    for (const m of messages) {
      if (m.key.remoteJid !== grupo || m.key.fromMe) continue;
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

async function postar(item) {
  await acharGrupo();
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
        const { imageMessage } = await prepareWAMessageMedia({ image: { url: pv.imagem } },
          { upload: sock.waUploadToServer, mediaTypeOverride: "thumbnail-link", logger });
        info.jpegThumbnail = imageMessage?.jpegThumbnail ? Buffer.from(imageMessage.jpegThumbnail) : undefined;
        info.highQualityThumbnail = imageMessage || undefined;
      }
      await sock.sendMessage(grupo, { text: item.texto, linkPreview: info });
      return;
    } catch (e) {
      console.log("Aviso: não consegui montar a prévia do link; vai como foto:", e?.message);
    }
  }
  if (item.imagem) {
    const local = !/^https?:/i.test(item.imagem);
    if (local && !fs.existsSync(item.imagem)) {
      await sock.sendMessage(grupo, { text: item.texto });
    } else {
      await sock.sendMessage(grupo, { image: local ? fs.readFileSync(item.imagem) : { url: item.imagem },
        caption: item.texto });
    }
  } else {
    await sock.sendMessage(grupo, { text: item.texto });
  }
}

async function cuidarDaFila() {
  if (!aberto) return;
  let arquivos = fs.readdirSync(FILA).filter((n) => n.endsWith(".json")).sort();
  // Alterna as lojas (Mercado Livre / Shopee): a mais antiga da outra loja passa na frente
  const lojaDe = (n) => {
    try {
      return JSON.parse(fs.readFileSync(path.join(FILA, n), "utf8")).loja || "ml";
    } catch {
      return "ml";
    }
  };
  const outra = arquivos.find((n) => lojaDe(n) !== (estado.ultima_loja || "ml"));
  if (outra) arquivos = [outra, ...arquivos.filter((n) => n !== outra)];
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
    if (Date.now() - Date.parse(item.criado) > VALIDADE_ITEM || estado.enviados >= MAX_DIA) {
      apagarItem(caminho, item); // velho demais ou limite do dia: não sai
      continue;
    }
    if (estado.ultimo && Date.now() - Date.parse(estado.ultimo) < INTERVALO) return; // espera o intervalo
    if (estado.pausado_ate && Date.now() < Date.parse(estado.pausado_ate)) {
      apagarItem(caminho, item); // em pausa de segurança: não posta
      continue;
    }
    try {
      await postar(item);
      estado.enviados += 1;
      estado.ultimo = new Date().toISOString();
      estado.ultima_loja = item.loja || "ml";
      console.log(`Postado no grupo do WhatsApp (${estado.enviados}/${MAX_DIA} hoje).`);
    } catch (e) {
      console.log("Aviso: não consegui postar no WhatsApp:", e?.message);
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
  await cuidarDaFila().catch((e) => console.log("Aviso:", e?.message));
  if (Date.now() - ultimoSalvo > 5 * 60 * 1000) {
    if (!estado.membros_em || Date.now() - Date.parse(estado.membros_em) > 60 * 60 * 1000) await contarMembros();
    salvarTudo();
    ultimoSalvo = Date.now();
  }
  await dormir(5000);
}
await encerrar();
