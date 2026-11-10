// Conecta o WhatsApp do Chocalho como "aparelho conectado" usando código de
// pareamento (sem QR). O código vai para você pelo Telegram; você digita no
// celular em Aparelhos conectados → Conectar com número de telefone.
import makeWASocket, { Browsers, DisconnectReason, useMultiFileAuthState } from "@whiskeysockets/baileys";
import pino from "pino";

import { PASTA_AUTH, apagarSessao, avisar, codigoConvite, dormir, guardarSessao } from "./comum.mjs";

const numero = (process.env.WA_NUMERO || "").replace(/\D/g, "");
if (numero.length < 12) {
  await avisar("⚠️ Para conectar o WhatsApp, crie o segredo <b>WA_NUMERO</b> no GitHub com o número do Chocalho (ex.: 5511999998888).");
  console.log("Falta o segredo WA_NUMERO.");
  process.exit(1);
}

apagarSessao();
const { state, saveCreds } = await useMultiFileAuthState(PASTA_AUTH);
const logger = pino({ level: "silent" });
const LIMITE = Date.now() + 8 * 60 * 1000;
let pediuCodigo = false;
let pronto = false;

function conectar() {
  const sock = makeWASocket({ auth: state, logger, browser: Browsers.macOS("Chrome"), markOnlineOnConnect: false,
    syncFullHistory: false });
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", async (u) => {
    if (u.qr && !pediuCodigo && !state.creds.registered) {
      pediuCodigo = true;
      try {
        const codigo = await sock.requestPairingCode(numero);
        const bonito = codigo.length === 8 ? `${codigo.slice(0, 4)}-${codigo.slice(4)}` : codigo;
        await avisar(
          `📲 <b>Código para conectar o WhatsApp do Chocalho:</b>\n\n<code>${bonito}</code>\n\n` +
          "No celular do Chocalho: WhatsApp → ⋮ (ou Configurações) → <b>Aparelhos conectados</b> → " +
          "<b>Conectar um aparelho</b> → <b>Conectar com número de telefone</b> e digite o código.\n" +
          "Ele vale por poucos minutos.");
        console.log("Código de pareamento enviado para você no Telegram.");
      } catch (e) {
        console.log("Não consegui pedir o código:", e?.message);
        await avisar(`⚠️ Não consegui gerar o código do WhatsApp: ${e?.message}`);
        process.exit(1);
      }
    }
    if (u.connection === "open") {
      pronto = true;
      let nomeGrupo = "";
      const cod = codigoConvite(process.env.WHATSAPP_GRUPO);
      if (cod) {
        try {
          nomeGrupo = (await sock.groupGetInviteInfo(cod)).subject || "";
        } catch {
          /* segue */
        }
      }
      console.log("WhatsApp conectado. Esperando a sincronização inicial...");
      await dormir(20000);
      await saveCreds();
      guardarSessao();
      await avisar(`✅ <b>WhatsApp conectado!</b>${nomeGrupo ? `\nGrupo encontrado: ${nomeGrupo}` : ""}\n` +
        "A partir do próximo ciclo, o bot passa a postar no grupo (começando devagar).");
      sock.end(undefined);
      process.exit(0);
    }
    if (u.connection === "close" && !pronto) {
      const motivo = u.lastDisconnect?.error?.output?.statusCode;
      if (motivo === DisconnectReason.loggedOut) {
        await avisar("⚠️ O WhatsApp recusou a conexão. Rode o “Conectar WhatsApp” de novo.");
        process.exit(1);
      }
      // Depois de digitar o código o WhatsApp pede para reconectar (normal)
      if (Date.now() < LIMITE) setTimeout(conectar, 2000);
    }
  });
}

conectar();
while (!pronto && Date.now() < LIMITE) await dormir(1000);
if (!pronto) {
  await avisar("⌛ O código do WhatsApp expirou sem ser usado. Rode o “Conectar WhatsApp” de novo quando estiver com o celular em mãos.");
  process.exit(1);
}
