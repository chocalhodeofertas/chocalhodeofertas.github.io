"""Manda no privado do admin um pacote pronto de docs/ig-tmp/<pasta>/:
carrossel (álbum + arquivos sem compressão), legenda e stories, cada story com o
link de afiliado para o adesivo. Antes, confere o preço de cada produto na loja:
se mudou, avisa no lugar de mandar.

pacote.json: {"legenda": "...", "carrossel": ["01.jpg", ...],
              "produtos": [{"nome", "loja": "ml"|"shopee", "id", "preco", "story": "story_1.jpg"}]}
Uso (workflow inspecao): enviar_pacote <pasta>
"""
import json
import os
import sys
from pathlib import Path

from bot.mercadolivre import MercadoLivre, token_do_app
from bot.mensagens import brl
from bot.shopee import _CAMPOS, Shopee
from bot.telegram import Telegram

pasta = Path("docs/ig-tmp") / sys.argv[1].strip()
pac = json.loads((pasta / "pacote.json").read_text(encoding="utf-8"))
estado = json.loads(Path("data/estado.json").read_text(encoding="utf-8"))
tg = Telegram(os.environ["TELEGRAM_BOT_TOKEN"])
admin = os.environ["TELEGRAM_ADMIN_CHAT_ID"]
ml = MercadoLivre(token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"]))
shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))

ids_ml = [p["id"] for p in pac["produtos"] if p["loja"] == "ml"]
info_ml = ml.itens(ids_ml) if ids_ml else {}
problemas = []
for p in pac["produtos"]:
    if p["loja"] == "ml":
        i = info_ml.get(p["id"])
        p["agora"] = i.preco if i and i.disponivel else None
        p["link"] = (estado.get("links") or {}).get(p["id"])
    else:
        d = shp._chamar("{productOfferV2(itemId:%d,page:1,limit:1){nodes{%s}}}" % (int(p["id"]), _CAMPOS))
        nos = (d.get("productOfferV2") or {}).get("nodes") or []
        n = nos[0] if nos else {}
        p["agora"] = float(n["priceMin"]) if n.get("priceMin") else None
        origem = n.get("productLink") or n.get("offerLink")
        p["link"] = (shp.link_curto(origem, ["instagram"]) if origem else None) or n.get("offerLink")
    print(p["nome"], p["preco"], "->", p["agora"], p["link"])
    if p["agora"] is None:
        problemas.append(f"• {p['nome']}: saiu do ar ou sem estoque")
    elif abs(p["agora"] - p["preco"]) > 0.009:
        problemas.append(f"• {p['nome']}: era {brl(p['preco'])}, agora {brl(p['agora'])}")
    if not p["link"]:
        problemas.append(f"• {p['nome']}: não consegui o link de afiliado")

if problemas:
    tg.enviar_texto(admin, "⚠️ <b>Pacote não enviado: preço mudou</b>\n" + "\n".join(problemas)
                    + "\n\nPeça para eu atualizar a arte antes de postar.", html=True)
    sys.exit(0)

slides = [(pasta / n).read_bytes() for n in pac["carrossel"]]
tg.enviar_texto(admin, f"🎄 <b>{pac.get('titulo', 'Pacote')}</b>\nPreços conferidos agora. Nada foi postado.", html=True)
tg.enviar_album(admin, slides, "🎠 Carrossel (na ordem)")
for k, (n, b) in enumerate(zip(pac["carrossel"], slides), 1):
    tg.enviar_documento(admin, b, f"carrossel_{k:02d}.jpg", None, "image/jpeg")
tg.enviar_texto(admin, pac["legenda"])
for p in pac["produtos"]:
    tg.enviar_foto(admin, (pasta / p["story"]).read_bytes(), f"📱 Story · {p['nome']}\nLink para o adesivo:\n{p['link']}",
                   nome=p["story"])
print("enviado")
