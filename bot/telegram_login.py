"""Login da sua conta do Telegram para ler o canal de cupons (roda no GitHub).

Etapa 1: pede ao Telegram o código de login (chega no seu app do Telegram).
Etapa 2: confirma com o código e guarda a sessão criptografada.

A sessão fica em data/tg_sessao.enc, criptografada com o TG_API_HASH
(que só existe nos secrets do GitHub).
"""
import asyncio
import os
import sys

from .cupons_ml import ARQ_LOGIN, ARQ_SESSAO, _resolver, guardar_seguro, ler_seguro


async def etapa1(api_id, api_hash, telefone):
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()
    try:
        enviado = await client.send_code_request(telefone)
        guardar_seguro({"sessao": client.session.save(), "hash": enviado.phone_code_hash}, api_hash, ARQ_LOGIN)
    finally:
        await client.disconnect()
    print("✅ Código enviado para o seu Telegram (confira o app, na conversa 'Telegram').")
    print("Agora rode de novo este workflow escolhendo a etapa 2 e digitando o código.")
    return 0


async def etapa2(api_id, api_hash, telefone, codigo, senha, convite):
    from telethon import TelegramClient
    from telethon.errors import PhoneCodeExpiredError, PhoneCodeInvalidError, SessionPasswordNeededError
    from telethon.sessions import StringSession

    dados = ler_seguro(api_hash, ARQ_LOGIN)
    if not dados:
        print("Rode primeiro a etapa 1.")
        return 1
    client = TelegramClient(StringSession(dados["sessao"]), int(api_id), api_hash)
    await client.connect()
    try:
        try:
            await client.sign_in(telefone, code=codigo.strip(), phone_code_hash=dados["hash"])
        except SessionPasswordNeededError:
            if not senha:
                print("Sua conta tem verificação em duas etapas. Crie o secret TG_SENHA_2FA com a senha "
                      "e rode a etapa 1 de novo.")
                return 1
            await client.sign_in(password=senha)
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            print("Código inválido ou expirado. Rode a etapa 1 de novo e use o código novo em seguida.")
            return 1
        guardar_seguro({"sessao": client.session.save()}, api_hash, ARQ_SESSAO)
        ARQ_LOGIN.unlink(missing_ok=True)
        print("✅ Login feito e salvo.")
        if convite:
            try:
                chat = await _resolver(client, convite)
                print(f"✅ Canal de cupons encontrado: {getattr(chat, 'title', 'ok')}")
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ Login ok, mas não achei o canal de cupons: {e}")
        return 0
    finally:
        await client.disconnect()


def main():
    e = os.environ.get
    api_id, api_hash, telefone = e("TG_API_ID"), e("TG_API_HASH"), e("TG_TELEFONE")
    faltando = [n for n, v in (("TG_API_ID", api_id), ("TG_API_HASH", api_hash), ("TG_TELEFONE", telefone)) if not v]
    if faltando:
        print("Faltam os secrets: " + ", ".join(faltando))
        return 1
    if e("ETAPA", "").startswith("1"):
        return asyncio.run(etapa1(api_id, api_hash, telefone))
    codigo = e("CODIGO", "").strip()
    if not codigo:
        print("Digite o código que chegou no Telegram.")
        return 1
    return asyncio.run(etapa2(api_id, api_hash, telefone, codigo, e("TG_SENHA_2FA"), e("TG_CANAL_CUPONS")))


if __name__ == "__main__":
    sys.exit(main())
