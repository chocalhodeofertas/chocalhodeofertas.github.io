"""Ensaio do espelho: lê os canais de ofertas e mostra o que viraria oferta, sem postar nada.

Usa o token só do app no ML (não mexe no refresh_token do bot) e uma cópia do estado.
Uso: python -m tools.testar_espelho "canal1,canal2"   (vazio = fontes padrão do ciclo.yml)
"""
import copy
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from bot import espelho
from bot import estado as est
from bot.filtros import fora_da_faixa, motivo_bloqueio
from bot.main import ARQ_ESTADO, DESCONTO_MIN_ESPELHO, FUSO, Produto
from bot.mercadolivre import MercadoLivre, link_produto, token_do_app
from bot.ofertas import avaliar


def fontes_padrao():
    yml = Path(".github/workflows/ciclo.yml").read_text(encoding="utf-8")
    m = re.search(r"FONTES_OFERTAS_TG: \$\{\{ vars.FONTES_OFERTAS_TG \|\| '([^']*)'", yml)
    return m.group(1) if m else ""


def main(arg):
    os.environ["FONTES_OFERTAS_TG"] = arg or fontes_padrao()
    agora = datetime.now(FUSO)
    estado = copy.deepcopy(est.carregar(ARQ_ESTADO))
    estado.pop("espelho", None)  # ensaio do zero: olha as últimas mensagens de cada canal
    ml = MercadoLivre(token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"]))
    linhas, amostra = [], []

    def expandir_registrando(url, sess=None):
        final = espelho.expandir(url, sess)
        if len(amostra) < 25 and "amazon" not in final:
            amostra.append(f"- {url[:70]} → {final[:110]}")
        return final

    espelho.coletar(ml, estado, agora, log=lambda m: linhas.append(f"- {m}"), expandir_url=expandir_registrando)
    linhas.append("\n## Amostra de links (original → destino)\n")
    linhas.extend(amostra)
    e = estado["espelho"]
    linhas.append(f"\n## Mercado Livre ({len(e['ml'])} produtos de catálogo achados)\n")
    for pid, d in e["ml"].items():
        try:
            info = ml.catalogo(pid)
        except Exception as erro:  # noqa: BLE001
            linhas.append(f"- {pid}: sem dados ({erro})")
            continue
        motivo = motivo_bloqueio(info.titulo) or fora_da_faixa(info.titulo, "outros", "infantil")
        p = Produto(pid, "catalogo", link_produto("catalogo", pid), "", "outros", None, 0)
        oferta = None if motivo else avaliar(p, info, estado, agora, DESCONTO_MIN_ESPELHO, 7)
        if motivo:
            res = f"❌ {motivo}"
        elif oferta:
            res = f"✅ R$ {oferta.preco:.2f} (-{round(oferta.desconto * 100)}%)"
        else:
            res = f"⏸ sem desconto suficiente / repetido (R$ {info.preco})"
        linhas.append(f"- {res} — {info.titulo[:70]} [{d['fonte']}]")
    linhas.append(f"\n## Shopee ({len(e['shopee'])} produtos achados)\n")
    if os.environ.get("SHOPEE_APP_ID"):
        from bot.shopee import Shopee
        from bot.shopee_ofertas import do_espelho
        shp = Shopee(os.environ["SHOPEE_APP_ID"], os.environ["SHOPEE_SECRET"])
        ok = do_espelho(shp, estado, agora, log=lambda m: None, limite=60)
        for p in ok:
            linhas.append(f"- ✅ R$ {p.preco:.2f} nota {p.nota} vendas {p.vendas} — {p.titulo[:70]}")
        for pid, d in e["shopee"].items():
            if d.get("fora"):
                linhas.append(f"- ❌ {d['fora']} — {pid} [{d.get('fonte')}]")
        for t, d in e["shopee_titulos"].items():
            linhas.append(f"- 🔎 {d.get('fora', 'pendente')} — “{t[:60]}” [{d.get('fonte')}]")
    fontes = {k: v for k, v in e["fontes"].items()}
    linhas.insert(0, f"# Ensaio do espelho {agora:%d/%m %H:%M}\n\nFontes lidas: {json.dumps(fontes, ensure_ascii=False)}\n")
    Path("saida").mkdir(exist_ok=True)
    Path("saida/espelho.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
