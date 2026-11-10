"""Manda 3 posts de exemplo da Shopee SÓ para o admin (versão Telegram + versão WhatsApp).

Não posta no canal nem no grupo e não grava nada no estado do bot.
"""
import os
import random
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from bot import estado as est
from bot import mensagens, shopee_ofertas
from bot.ofertas import tipo_produto
from bot.shopee import Shopee
from bot.telegram import Telegram

agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
estado = est.carregar("data/estado.json")
termos = [t.strip() for t in (sys.argv[1] if len(sys.argv) > 1 else "").split(",") if t.strip()] or \
    ["brinquedo educativo", "body bebê", "mochila infantil", "banheira bebê", "kit higiene bebê"]
candidatos = shopee_ofertas.buscar_candidatos(shp, estado, agora, termos=termos)
escolhidos, tipos = [], set()
for p in candidatos:
    tp = tipo_produto(p.titulo)
    if tp not in tipos:
        escolhidos.append(p)
        tipos.add(tp)
    if len(escolhidos) == 3:
        break
tg = Telegram(os.environ["TELEGRAM_BOT_TOKEN"])
admin = os.environ["TELEGRAM_ADMIN_CHAT_ID"]
rng = random.Random()
tg.enviar_texto(admin, f"🛍️ <b>3 exemplos de post da Shopee</b> (nada foi postado)\n"
                f"{len(candidatos)} produtos passaram nas regras nesta busca.", html=True)
for p in escolhidos:
    link_tg, link_wa = shopee_ofertas.links(shp, p)
    o = shopee_ofertas.para_oferta(p, estado, agora, link_tg, link_wa)
    print(mensagens.montar_telegram(o, rng), "\n---\n", mensagens.montar_whatsapp(o, rng), "\n=====")
    tg.enviar_oferta(admin, "[EXEMPLO · Telegram]\n\n" + mensagens.montar_telegram(o, rng), o.imagem)
    tg.enviar_texto(admin, "[EXEMPLO · WhatsApp]\n\n" + mensagens.montar_whatsapp(o, rng))
