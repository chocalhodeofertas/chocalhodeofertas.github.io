"""Publica no Instagram um carrossel que está em docs/ig-tmp/<pasta>/ (01.jpg, 02.jpg... + legenda.txt).

As imagens precisam estar no ar no GitHub Pages (o Instagram baixa por URL).
Uso (workflow "Inspecionar"): script = publicar_carrossel, args = <pasta>.
Só rodar com a aprovação do Leonardo para aquele post.
"""
import os
import sys
import time
from pathlib import Path

import requests

from bot.instagram import Instagram
from bot.telegram import Telegram

SITE = "https://chocalhodeofertas.github.io"
pasta = sys.argv[1].strip().strip("/")
local = Path("docs/ig-tmp") / pasta
fotos = sorted(p.name for p in local.glob("*.jpg"))
legenda = (local / "legenda.txt").read_text(encoding="utf-8").strip()
urls = [f"{SITE}/ig-tmp/{pasta}/{n}" for n in fotos]
print("IMAGENS", len(urls))
for _ in range(60):  # espera o GitHub Pages publicar as imagens
    if all(requests.head(u, timeout=20).status_code == 200 for u in urls):
        break
    time.sleep(10)
else:
    sys.exit("as imagens não ficaram no ar no GitHub Pages")
ig = Instagram(os.environ.get("INSTAGRAM_TOKEN"), os.environ.get("INSTAGRAM_USER_ID"))
mid, link = ig.publicar_carrossel(urls, legenda)
print("PUBLICADO", mid, link)
if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_ADMIN_CHAT_ID"):
    Telegram(os.environ["TELEGRAM_BOT_TOKEN"]).enviar_texto(
        os.environ["TELEGRAM_ADMIN_CHAT_ID"], f"📸 Carrossel publicado no Instagram: {link}")
