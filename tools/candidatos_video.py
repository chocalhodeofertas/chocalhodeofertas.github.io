"""Candidatos para o Shopee Vídeo: produtos bons e pouco explorados (só pela API oficial).

A API não informa quantos afiliados divulgam cada produto. Por isso a lista prioriza
sinais de "bom e ainda pouco disputado": nota alta, vendas na faixa média (os campeões
com dezenas de milhares de vendas já estão em todo vídeo) e comissão acima do mínimo.
A coluna "videos_no_app" vai vazia para o Leonardo preencher olhando o app.

Não posta nada. Uso (workflow "Inspecionar"): script = candidatos_video,
args = termos separados por vírgula (opcional). Saída: saida/candidatos_video.csv
"""
import csv
import math
import os
import sys
from pathlib import Path

from bot import filtros
from bot.shopee import MAIS_VENDIDOS, MAIOR_COMISSAO, Shopee, ShopeeErro
from bot.shopee_ofertas import TERMOS, categoria_do_titulo

# Termos extras de produtos que rendem bem em vídeo sem mostrar criança.
TERMOS_VIDEO = [
    "organizador brinquedos", "luminária infantil", "projetor estrelas infantil", "garrafa infantil",
    "kit pintura infantil", "slime", "brinquedo de banho", "pista carrinho", "kit médico brinquedo",
    "cozinha infantil brinquedo", "jogo de tabuleiro infantil", "lousa mágica", "pop it",
    "fantoche", "cabana infantil", "mesa atividades infantil", "kit maquiagem infantil",
    "estojo escolar", "garrafinha escolar", "porta lanche infantil", "móbile berço",
]
NOTA_MIN, COMISSAO_MIN = 4.7, 0.05
VENDAS_MIN, VENDAS_MAX = 500, 10000
QUANTOS = 25


def pontos(p):
    """Nota e comissão pesam mais; vendas ajudam até ~3 mil e depois passam a contar contra
    (muita venda = muito afiliado já divulgando)."""
    v = max(p.vendas, 1)
    alvo = math.log10(3000)
    vendas = 1 - abs(math.log10(v) - alvo) / 1.5
    return (p.nota - 4.5) * 4 + p.comissao * 20 + vendas * 2


def apto(p):
    if p.nota < NOTA_MIN or p.comissao < COMISSAO_MIN or not p.link:
        return False
    if not (VENDAS_MIN <= p.vendas <= VENDAS_MAX):
        return False
    return not (filtros.motivo_bloqueio(p.titulo) or filtros.fora_da_faixa(p.titulo, "", "infantil"))


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    termos = [t.strip() for t in arg.split(",") if t.strip()] or (TERMOS + TERMOS_VIDEO)
    shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
    vistos, erros = {}, []
    for termo in termos:
        for ordem in (MAIS_VENDIDOS, MAIOR_COMISSAO):
            try:
                for p in shp.buscar(termo, ordem=ordem, limite=50):
                    vistos.setdefault(p.id, p)
            except ShopeeErro as e:
                erros.append(f"{termo}: {e}")
    if not vistos:
        print("A API não respondeu:", "; ".join(erros[:5]))
        return 1
    bons = sorted((p for p in vistos.values() if apto(p)), key=pontos, reverse=True)
    # No máximo 3 por categoria, para a lista não virar só brinquedo.
    por_cat, lista = {}, []
    for p in bons:
        cat = categoria_do_titulo(p.titulo) or "outros"
        if por_cat.get(cat, 0) >= 3:
            continue
        por_cat[cat] = por_cat.get(cat, 0) + 1
        lista.append((cat, p))
        if len(lista) >= QUANTOS:
            break
    Path("saida").mkdir(exist_ok=True)
    with open("saida/candidatos_video.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["produto", "categoria", "preco", "nota", "vendidos", "comissao", "loja",
                    "loja_oficial", "item_id", "link_produto", "videos_no_app"])
        for cat, p in lista:
            w.writerow([p.titulo, cat, f"{p.preco:.2f}", f"{p.nota:.1f}", p.vendas,
                        f"{p.comissao * 100:.1f}%", p.loja, "sim" if p.loja_oficial else "não",
                        p.id.removeprefix("SHP"), p.link_produto or p.link, ""])
    print(f"{len(vistos)} produtos vistos, {len(bons)} aptos, {len(lista)} na lista. Erros: {len(erros)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
