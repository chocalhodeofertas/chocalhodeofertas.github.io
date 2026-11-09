"""Gera os posts do Instagram (post, legenda e story) dos links meli.la passados e manda no privado."""
import json
import os
import sys
from types import SimpleNamespace

import requests

from bot import comandos
from bot.mercadolivre import MercadoLivre, token_do_app
from bot.telegram import Telegram

links = sys.argv[1].split()
estado = json.load(open("data/estado.json", encoding="utf-8"))
ml = MercadoLivre(token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"]))
tg = Telegram(os.environ["TELEGRAM_BOT_TOKEN"])
cfg = SimpleNamespace(admin_chat=os.environ.get("TELEGRAM_ADMIN_CHAT_ID") or "787296152")
s = requests.Session()
tg.enviar_texto(cfg.admin_chat, f"📦 Posts de produto para o Instagram ({len(links)} produtos):")
for l in links:
    erro = comandos.postar_insta(l, tg, ml, estado, cfg, s)
    print(l, erro or "ok")
    if erro:
        tg.enviar_texto(cfg.admin_chat, erro, html=True)
