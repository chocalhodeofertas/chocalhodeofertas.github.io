"""Prévia do cartão com a marca para a prévia do link no WhatsApp, SÓ para o admin (não posta no grupo nem no canal).

Pega as 3 últimas ofertas do dia com foto (estado.posts_dia), monta o cartão de cada uma e manda um álbum no
privado do admin, com o título que iria na prévia. Também grava os PNGs em saida/.
Uso (workflow inspecao): script=previa_cartao_wa
"""
import os
from pathlib import Path

from bot import arte
from bot import estado as est
from bot.telegram import Telegram

estado = est.carregar("data/estado.json")
itens = [i for i in (estado.get("posts_dia") or {}).get("itens", []) if i.get("imagem")][-3:]
saida = Path("saida")
saida.mkdir(exist_ok=True)
pngs, titulos = [], []
for n, i in enumerate(itens, 1):
    foto = arte.baixar_foto(i["imagem"])
    if foto is None:
        print("sem foto:", i["titulo"][:60])
        continue
    png = arte.cartao_previa(foto)
    (saida / f"cartao{n}.png").write_bytes(png)
    pngs.append(png)
    titulos.append(i["titulo"])
print("\n".join(titulos))
if pngs:
    tg = Telegram(os.environ["TELEGRAM_BOT_TOKEN"])
    admin = os.environ.get("TELEGRAM_ADMIN_CHAT_ID") or "787296152"
    tg.enviar_album(admin, pngs, "👀 Prévia (só você vê): imagem da prévia do link no grupo do WhatsApp.\n"
                    "Títulos que iriam junto:\n" + "\n".join(titulos))
