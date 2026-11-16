// Partes comuns da conexão do WhatsApp: sessão criptografada no repositório
// e avisos para você pelo bot do Telegram (nada sensível vai para os logs,
// que são públicos).
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
export const ARQ_SESSAO = path.join(RAIZ, "data", "wa_sessao.enc");
export const ARQ_ESTADO = path.join(RAIZ, "data", "wa_estado.json");
export const PASTA_AUTH = path.join(RAIZ, ".wa_auth");

function chave() {
  const base = process.env.TELEGRAM_BOT_TOKEN;
  if (!base) throw new Error("falta TELEGRAM_BOT_TOKEN (usado como chave da sessão)");
  return crypto.scryptSync(base + ":whatsapp", "chocalho-wa", 32);
}

/** Lê a sessão criptografada e recria a pasta de autenticação. */
export function abrirSessao() {
  fs.rmSync(PASTA_AUTH, { recursive: true, force: true });
  fs.mkdirSync(PASTA_AUTH, { recursive: true });
  if (!fs.existsSync(ARQ_SESSAO)) return false;
  const bruto = Buffer.from(fs.readFileSync(ARQ_SESSAO, "utf8").trim(), "base64");
  const iv = bruto.subarray(0, 12), tag = bruto.subarray(12, 28), dados = bruto.subarray(28);
  const dec = crypto.createDecipheriv("aes-256-gcm", chave(), iv);
  dec.setAuthTag(tag);
  const arquivos = JSON.parse(Buffer.concat([dec.update(dados), dec.final()]).toString("utf8"));
  for (const [nome, conteudo] of Object.entries(arquivos)) {
    fs.writeFileSync(path.join(PASTA_AUTH, path.basename(nome)), conteudo, "utf8");
  }
  return true;
}

/** Criptografa a pasta de autenticação de volta para data/wa_sessao.enc. */
export function guardarSessao() {
  if (!fs.existsSync(PASTA_AUTH)) return;
  const arquivos = {};
  for (const nome of fs.readdirSync(PASTA_AUTH)) {
    arquivos[nome] = fs.readFileSync(path.join(PASTA_AUTH, nome), "utf8");
  }
  if (!arquivos["creds.json"]) return;
  const iv = crypto.randomBytes(12);
  const cif = crypto.createCipheriv("aes-256-gcm", chave(), iv);
  const dados = Buffer.concat([cif.update(JSON.stringify(arquivos), "utf8"), cif.final()]);
  const saida = Buffer.concat([iv, cif.getAuthTag(), dados]).toString("base64");
  fs.mkdirSync(path.dirname(ARQ_SESSAO), { recursive: true });
  fs.writeFileSync(ARQ_SESSAO + ".tmp", saida + "\n");
  fs.renameSync(ARQ_SESSAO + ".tmp", ARQ_SESSAO);
}

export function apagarSessao() {
  fs.rmSync(ARQ_SESSAO, { force: true });
  fs.rmSync(PASTA_AUTH, { recursive: true, force: true });
}

/** Mensagem para você no Telegram (chat do admin). */
export async function avisar(texto) {
  const token = process.env.TELEGRAM_BOT_TOKEN, chat = process.env.TELEGRAM_ADMIN_CHAT_ID;
  if (!token || !chat) return;
  try {
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: chat, text: texto, parse_mode: "HTML", disable_web_page_preview: true }),
    });
  } catch {
    /* sem aviso, segue */
  }
}

export function lerEstado() {
  try {
    return JSON.parse(fs.readFileSync(ARQ_ESTADO, "utf8"));
  } catch {
    return {};
  }
}

export function gravarEstado(e) {
  fs.mkdirSync(path.dirname(ARQ_ESTADO), { recursive: true });
  fs.writeFileSync(ARQ_ESTADO, JSON.stringify(e, null, 2) + "\n");
}

/** Código do convite a partir do link do grupo (chat.whatsapp.com/XXXX). */
export function codigoConvite(link) {
  const m = /chat\.whatsapp\.com\/(?:invite\/)?([\w-]+)/.exec(link || "");
  return m ? m[1] : null;
}

export const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

// Janela da meia-noite: nas datas especiais (Black Friday, 12.12) o grupo também recebe ofertas
// das 23h30 da véspera à 1h do dia. Mesmas datas do bot (bot/horario.py).
const DATAS_MEIA_NOITE = (process.env.DATAS_MEIA_NOITE ?? "2026-11-27,2026-12-12").split(/[,;]/).map((d) => d.trim())
  .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d));
export function naMeiaNoite(agora = new Date(), datas = DATAS_MEIA_NOITE) {
  const f = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(agora);
  const p = Object.fromEntries(f.map((x) => [x.type, x.value]));
  const dia = `${p.year}-${p.month}-${p.day}`;
  const hora = Number(p.hour), minuto = Number(p.minute);
  if (datas.includes(dia) && hora < 1) return true;
  const amanha = new Date(Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day) + 1)).toISOString().slice(0, 10);
  return datas.includes(amanha) && (hora > 23 || (hora === 23 && minuto >= 30));
}

// Ordem da fila do grupo: o limite diário é pequeno, então sai primeiro o que tem mais pontos
// (avisos como cupons e resumos valem 9; ofertas valem pela força do desconto). Empate: a mais antiga.
// As lojas continuam alternando: a melhor oferta da outra loja passa na frente, a não ser que haja um aviso.
export function ordenarFila(nomes, ler, ultimaLoja = "ml") {
  const itens = nomes.map((nome) => {
    const d = ler(nome) || {};
    return { nome, pontos: Number(d.pontos) || 0, loja: d.loja || "ml" };
  });
  itens.sort((a, b) => b.pontos - a.pontos || (a.nome < b.nome ? -1 : 1));
  const aviso = itens.length && itens[0].pontos >= 9;
  const outra = aviso ? null : itens.find((i) => i.loja !== ultimaLoja);
  const ordem = outra ? [outra, ...itens.filter((i) => i !== outra)] : itens;
  return ordem.map((i) => i.nome);
}
