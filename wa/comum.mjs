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
// Ordem da fila: mais pontos primeiro; aviso (9+) na frente de tudo; senão alterna a loja e, dentro disso,
// evita repetir a categoria da última oferta (rodízio aprovado em 17/11). Espelhado em bot/fila_pagina.py.
export function ordenarFila(nomes, ler, ultimaLoja = "ml", ultimaCategoria = null) {
  const itens = nomes.map((nome) => {
    const d = ler(nome) || {};
    return { nome, pontos: Number(d.pontos) || 0, loja: d.loja || "ml", categoria: d.categoria || null };
  });
  itens.sort((a, b) => b.pontos - a.pontos || (a.nome < b.nome ? -1 : 1));
  const aviso = itens.length && itens[0].pontos >= 9;
  let outra = null;
  if (!aviso) {
    const daOutraLoja = itens.filter((i) => i.loja !== ultimaLoja);
    const base = daOutraLoja.length ? daOutraLoja : itens;
    outra = base.find((i) => !ultimaCategoria || i.categoria !== ultimaCategoria) || base[0] || null;
  }
  const ordem = outra ? [outra, ...itens.filter((i) => i !== outra)] : itens;
  return ordem.map((i) => i.nome);
}

// Histórico do dia para a página da fila (bot/fila_pagina.py): o que saiu no grupo e o que ficou de fora, e por quê.
// resultado: "enviado" | "venceu" (mais de 3 h na fila) | "limite" (limite de posts do dia) | "pausa" | "erro".
export function nomeDoItem(item) {
  const linhas = String(item?.texto || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const nome = linhas.slice(1).find((l) => !l.includes("R$") && !l.includes("http") && !/^[_*]/.test(l));
  return (nome || linhas[0] || "(sem texto)").slice(0, 80);
}

export function anotarHistorico(estado, item, resultado, dia, agora = new Date()) {
  if (!estado.historico || estado.historico.dia !== dia) estado.historico = { dia, itens: [] };
  const link = /https?:\/\/\S+/.exec(String(item?.texto || ""));
  estado.historico.itens.push({ h: agora.toISOString(), n: nomeDoItem(item), l: item?.loja || "ml", r: resultado,
    k: link ? link[0] : null, p: Number(item?.pontos) || 0 });
  if (estado.historico.itens.length > 200) estado.historico.itens = estado.historico.itens.slice(-200);
  return estado.historico;
}

// Ritmo do grupo. Intervalo sorteado entre um post e outro (fixo parece robô) e o limite do dia espalhado pelas horas:
// até agora só pode ter saído a fração do dia que já passou (sempre pelo menos 1). Assim o grupo recebe oferta de
// manhã, à tarde e à noite, em vez de gastar o limite inteiro de manhã.
export function sortearIntervalo(minimo = 4, maximo = 13, sorte = Math.random) {
  return Math.round((minimo + (maximo - minimo) * sorte()) * 60000);
}

export function cotaAteAgora(maxDia, hora, minuto = 0, inicio = 7, fim = 23) {
  const passou = Math.min(Math.max(hora + minuto / 60 - inicio, 0), fim - inicio);
  return Math.min(maxDia, Math.max(1, Math.ceil((maxDia * passou) / (fim - inicio))));
}

// Radar do grupo: entradas, saídas e mensagens por hora (só contagens: nenhum número nem texto é guardado).
// estado.radar = { "AAAA-MM-DD": { "HH": [entradas, saídas, mensagens] } }, últimos 45 dias.
export function anotarRadar(estado, tipo, quantos, dia, hora) {
  const i = { entrou: 0, saiu: 1, mensagem: 2 }[tipo];
  if (i === undefined || !quantos) return estado.radar;
  estado.radar = estado.radar || {};
  const h = String(hora).padStart(2, "0");
  const d = (estado.radar[dia] = estado.radar[dia] || {});
  d[h] = d[h] || [0, 0, 0];
  d[h][i] += quantos;
  for (const velho of Object.keys(estado.radar).sort().slice(0, -45)) delete estado.radar[velho];
  return estado.radar;
}
