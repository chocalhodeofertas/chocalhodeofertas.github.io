"""Prévia SÓ para o admin: respostas da busca sob pedido e o post diário dos cupons da Shopee. Não posta nada.

Uso (workflow inspecao): script=previa_busca, args="fralda g; mochila infantil"
"""
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from bot import busca_publica, comandos, resumos
from bot import estado as est
from bot.mercadolivre import MercadoLivre, token_do_app
from bot.telegram import Telegram

agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
estado = est.carregar("data/estado.json")
tg = Telegram(os.environ["TELEGRAM_BOT_TOKEN"])
admin = os.environ.get("TELEGRAM_ADMIN_CHAT_ID") or "787296152"
ml = None
try:
    ml = MercadoLivre(token_do_app(os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")))
except Exception as e:  # noqa: BLE001
    print("ML indisponível:", type(e).__name__)
os.environ["SHOPEE_ATIVO"] = "1"
shp = busca_publica._shopee(print)
termos = [t.strip() for t in (sys.argv[1] if len(sys.argv) > 1 else "").split(";") if t.strip()] or ["fralda g"]
tg.enviar_texto(admin, "🧪 <b>PRÉVIA · busca sob pedido</b> (é assim que a pessoa receberia a resposta)", html=True)
for termo in termos[:5]:
    resposta = busca_publica.procurar(termo, estado, agora, ml, shp, print)
    print("=" * 10, termo)
    print(re.sub(r"<[^>]+>", "", resposta))
    tg.enviar_texto(admin, resposta, html=True)
link = comandos.link_cupons_shopee()
tg.enviar_texto(admin, "🧪 <b>PRÉVIA · cupons da Shopee do dia</b> (nada foi postado)", html=True)
tg.enviar_texto(admin, resumos.montar_cupons_shopee(link, "telegram"), html=True)
tg.enviar_texto(admin, "[versão do WhatsApp]\n\n" + resumos.montar_cupons_shopee(link, "whatsapp"))
