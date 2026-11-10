"""Teste da API da Shopee: busca produtos infantis e manda uma prévia SÓ para o admin.

Não posta nada no canal nem no grupo. Uso (workflow "Inspecionar"):
script = testar_shopee, args = termos separados por vírgula (opcional).
"""
import html
import json
import os
import sys
from pathlib import Path

from bot import filtros
from bot.shopee import MAIS_VENDIDOS, Shopee, ShopeeErro
from bot.telegram import Telegram

TERMOS = ["bebê", "infantil", "brinquedo educativo", "body bebê", "mochila infantil",
          "fralda", "banheira bebê", "kit higiene bebê"]


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    termos = [t.strip() for t in (sys.argv[1] if len(sys.argv) > 1 else "").split(",") if t.strip()] or TERMOS
    shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
    vistos, bons, fora = {}, [], {}
    for termo in termos:
        try:
            achados = shp.buscar(termo, ordem=MAIS_VENDIDOS, limite=50)
        except ShopeeErro as e:
            print("ERRO", termo, e)
            return str(e)
        print(f"TERMO {termo}: {len(achados)} produtos")
        for p in achados:
            if p.id in vistos:
                continue
            vistos[p.id] = p
            motivo = filtros.motivo_bloqueio(p.titulo) or filtros.fora_da_faixa(p.titulo, "", "infantil")
            if motivo:
                fora[motivo] = fora.get(motivo, 0) + 1
                continue
            bons.append(p)
    bons.sort(key=lambda p: (p.desconto, p.vendas), reverse=True)
    Path("saida").mkdir(exist_ok=True)
    Path("saida/shopee.json").write_text(json.dumps([p.__dict__ for p in bons], ensure_ascii=False, indent=1))
    linhas = [f"🛍️ <b>Teste da API da Shopee</b> (nada foi postado)",
              f"{len(vistos)} produtos encontrados · {len(bons)} passaram nos filtros"]
    for motivo, n in sorted(fora.items(), key=lambda x: -x[1]):
        linhas.append(f"• {n} barrados: {html.escape(motivo)}")
    linhas.append("\n<b>Maiores descontos</b>")
    for p in bons[:12]:
        de = f"de {brl(p.preco_de)} por " if p.preco_de else ""
        linhas.append(f"• {html.escape(p.titulo[:70])}\n  {de}<b>{brl(p.preco)}</b> · comissão {p.comissao * 100:.0f}% · "
                      f"{p.vendas} vendidos · ⭐ {p.nota:.1f}{' · loja oficial' if p.loja_oficial else ''}")
    texto = "\n".join(linhas)
    print(texto)
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_ADMIN_CHAT_ID"):
        Telegram(os.environ["TELEGRAM_BOT_TOKEN"]).enviar_texto(
            os.environ["TELEGRAM_ADMIN_CHAT_ID"], texto[:4000], html=True)
    return None


if __name__ == "__main__":
    erro = main()
    if erro and os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_ADMIN_CHAT_ID"):
        Telegram(os.environ["TELEGRAM_BOT_TOKEN"]).enviar_texto(
            os.environ["TELEGRAM_ADMIN_CHAT_ID"], f"⚠️ Teste da Shopee falhou: {erro}")
    sys.exit(1 if erro else 0)
