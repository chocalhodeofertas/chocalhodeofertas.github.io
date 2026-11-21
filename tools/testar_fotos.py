"""Calibra a comparação pela foto (bot/foto.py) com os posts reais dos últimos dias. Só leitura.

Pega os posts de cada dia no histórico do git (posts_dia de data/estado.json), baixa as fotos (endereços de
imagem da loja, não links de afiliado), calcula a impressão digital e lista os pares com foto igual ou parecida,
junto com o que a comparação de títulos diz. Uso (workflow inspecao): script=testar_fotos, args="dias" (padrão 6).
"""
import itertools
import json
import subprocess
import sys
from datetime import datetime, timedelta

from bot import foto
from bot.ofertas import _medidas_brigam, comparar_titulos, reposicao

dias = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].strip().isdigit() else 6
desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
subprocess.run(["git", "fetch", "-q", f"--shallow-since={desde}", "origin", "main"], check=False)
commits = subprocess.run(["git", "log", "origin/main", f"--since={desde}", "--format=%H", "--", "data/estado.json"],
                         capture_output=True, text=True).stdout.split()
itens = {}
for c in commits[::6]:  # um a cada ~2 h basta: posts_dia acumula o dia
    try:
        e = json.loads(subprocess.run(["git", "show", f"{c}:data/estado.json"], capture_output=True, text=True).stdout)
    except ValueError:
        continue
    for x in (e.get("posts_dia") or {}).get("itens") or []:
        if x.get("imagem") and x.get("id") and not str(x["imagem"]).startswith(("https://meli.la", "https://s.shopee")):
            itens.setdefault(x["id"], x)
print(f"{len(commits)} versões, {len(itens)} produtos postados com foto desde {desde}")

hashes = {}
for pid, x in itens.items():
    h = foto.baixar(x["imagem"])
    if h:
        hashes[pid] = h
print(f"{len(hashes)} fotos baixadas")

pares = []
for a, b in itertools.combinations(hashes, 2):
    d = foto.distancia(hashes[a], hashes[b])
    if d <= 14:
        ta, tb = itens[a]["titulo"], itens[b]["titulo"]
        ct = comparar_titulos(ta, tb)
        pares.append((d, a, b, ta, tb, ct["igual"], ct["nota"], _medidas_brigam(ta, tb), bool(reposicao(ta) or reposicao(tb))))
pares.sort()
for d, a, b, ta, tb, igual, nota, briga, rep in pares:
    print(f"{d:2d} | título igual={igual} nota={nota} medida_diferente={briga} reposição={rep}\n   {a} {ta[:75]}\n   {b} {tb[:75]}")
dist = sorted(foto.distancia(hashes[a], hashes[b]) for a, b in itertools.combinations(hashes, 2))
if dist:
    print("Distribuição das distâncias:", {k: sum(1 for d in dist if d <= k) for k in (3, 5, 8, 10, 12, 16, 20)},
          f"de {len(dist)} pares")
