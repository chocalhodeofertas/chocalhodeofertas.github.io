"""Procura canais públicos de ofertas de bebê/criança no Telegram e mede se valem como fonte.

Não entra em nenhum canal: só pesquisa e lê as últimas mensagens públicas.
Uso (workflow inspecao): python -m tools.achar_canais_tg "termo 1; termo 2"
Grava saida/canais_tg.md e manda um resumo no privado do admin.
"""
import asyncio
import os
import sys
from pathlib import Path

from bot.cupons_ml import ARQ_SESSAO, ler_seguro
from bot.espelho import _RE_URL
from bot.filtros import _INFANTIL, normalizar

TERMOS = ["promoções bebê", "ofertas bebê", "promo baby", "baby promo", "ofertas infantis", "achadinhos bebê",
          "promoções mamãe", "descontinho de mamãe", "fraldas promoção", "enxoval bebê ofertas",
          "brinquedos promoção", "ofertas kids", "compare baby", "promoçãozinha baby", "shopee baby"]


async def main(termos):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.contacts import SearchRequest

    api_id, api_hash = os.environ["TG_API_ID"], os.environ["TG_API_HASH"]
    sessao = ler_seguro(api_hash, ARQ_SESSAO)["sessao"]
    client = TelegramClient(StringSession(sessao), int(api_id), api_hash)
    await client.connect()
    achados = {}
    try:
        for termo in termos:
            try:
                r = await client(SearchRequest(q=termo, limit=20))
            except Exception as e:  # noqa: BLE001
                print(f"busca '{termo}': {e}")
                continue
            for ch in r.chats:
                if getattr(ch, "broadcast", False) or getattr(ch, "megagroup", False):
                    if ch.username and ch.id not in achados:
                        achados[ch.id] = ch
        linhas = []
        for ch in achados.values():
            ml = shp = infantil = total = 0
            ultima = None
            try:
                async for m in client.iter_messages(ch, limit=60):
                    texto = m.message or ""
                    for ent in getattr(m, "entities", None) or []:
                        if getattr(ent, "url", None):
                            texto += " " + ent.url
                    urls = _RE_URL.findall(texto)
                    if not urls:
                        continue
                    total += 1
                    ultima = ultima or m.date
                    if any("meli.la" in u or "mercadolivre" in u or "mercadolibre" in u for u in urls):
                        ml += 1
                    if any("shopee" in u or "shope.ee" in u for u in urls):
                        shp += 1
                    if _INFANTIL.search(normalizar(texto)):
                        infantil += 1
            except Exception as e:  # noqa: BLE001
                print(f"{ch.username}: {e}")
                continue
            membros = getattr(ch, "participants_count", None) or 0
            linhas.append((infantil, ch, membros, total, ml, shp, ultima))
        linhas.sort(key=lambda x: (x[0], x[3]), reverse=True)
        saida = ["| canal | membros | posts c/ link (60 últ.) | infantis | ML | Shopee | último |", "|---|---|---|---|---|---|---|"]
        for infantil, ch, membros, total, ml, shp, ultima in linhas:
            saida.append(f"| @{ch.username} — {ch.title} | {membros} | {total} | {infantil} | {ml} | {shp} | "
                         f"{ultima:%d/%m %H:%M} |" if ultima else f"| @{ch.username} — {ch.title} | {membros} | 0 | 0 | 0 | 0 | — |")
        Path("saida").mkdir(exist_ok=True)
        Path("saida/canais_tg.md").write_text("\n".join(saida) + "\n", encoding="utf-8")
        print("\n".join(saida))
    finally:
        await client.disconnect()


if __name__ == "__main__":
    extra = [t.strip() for t in (sys.argv[1] if len(sys.argv) > 1 else "").split(";") if t.strip()]
    asyncio.run(main(extra or TERMOS))
