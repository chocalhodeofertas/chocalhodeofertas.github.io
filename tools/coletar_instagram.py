"""Roda a coleta de números do Instagram uma vez, gravando em saida/instagram (não mexe em data/).

Uso (workflow "Inspecionar"): script = coletar_instagram.
"""
import json
import sys
from pathlib import Path

from bot import insights_ig

pasta = Path("saida/instagram")
codigo = insights_ig.rodar(pasta=pasta)
for arq in sorted(pasta.glob("2*.json")):
    d = json.loads(arq.read_text())
    print("CONTA_DIA", json.dumps(d["conta_no_dia"]["metricas"], ensure_ascii=False))
    print("CONTA_AUSENTES", json.dumps(d["conta_no_dia"]["ausentes"], ensure_ascii=False))
    for p in d["posts"]:
        print("POST", p["formato"], p["publicado_em"], json.dumps(p["metricas"]), "AUSENTES", json.dumps(p["ausentes"], ensure_ascii=False))
sys.exit(codigo)
