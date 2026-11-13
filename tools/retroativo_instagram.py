"""Busca os números diários da CONTA de dias passados (até 30), gravando em saida/instagram.

Uso (workflow "Inspecionar"): script = retroativo_instagram, args = "AAAA-MM-DD AAAA-MM-DD" (primeiro e último dia).
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from bot import insights_ig
from bot.instagram import Instagram

primeiro, ultimo = (date.fromisoformat(x) for x in sys.argv[1].split())
assert (ultimo - primeiro).days <= 30
ig = Instagram(os.environ["INSTAGRAM_TOKEN"], os.environ["INSTAGRAM_USER_ID"])
agora = datetime.now(insights_ig.FUSO)
pasta = Path("saida/instagram")
pasta.mkdir(parents=True, exist_ok=True)
dia = primeiro
while dia <= ultimo:
    d = insights_ig.coletar_retroativo(ig, dia, agora)
    (pasta / f"{dia.isoformat()}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("DIA", dia, json.dumps(d["conta_no_dia"]["metricas"]), "AUSENTES", list(d["conta_no_dia"]["ausentes"]))
    dia += timedelta(days=1)
