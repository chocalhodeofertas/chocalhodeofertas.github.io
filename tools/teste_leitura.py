import asyncio, os
from datetime import datetime
from zoneinfo import ZoneInfo
from bot import cupons_ml
h = os.environ["TG_API_HASH"]
s = cupons_ml.ler_seguro(h, cupons_ml.ARQ_SESSAO)["sessao"]
async def main():
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    c = TelegramClient(StringSession(s), int(os.environ["TG_API_ID"]), h)
    await c.connect()
    chat = await cupons_ml._resolver(c, os.environ["TG_CANAL_CUPONS"])
    msgs = [m async for m in c.iter_messages(chat, limit=15)]
    await c.disconnect()
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    total = rel = 0
    for m in msgs:
        cs = cupons_ml.parse(m.message or "", agora)
        total += len(cs); rel += sum(1 for x in cs if cupons_ml.relevante(x))
    print(f"LEITURA OK: {len(msgs)} mensagens recentes, {total} cupons reconhecidos, {rel} do nosso nicho/gerais")
asyncio.run(main())
