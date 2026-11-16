"""Diagnóstico: o que a página de destino de um link oficial do ML mostra (endereço final e preços em destaque).

Só leitura, poucas páginas por vez (uso pontual para investigar diferença de preço). Grava o HTML em saida/.
Uso (workflow inspecao): script=ver_pagina_ml, args="https://meli.la/a https://meli.la/b"
"""
import json
import os
import re
import sys
import time

import requests

NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0 Mobile Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9",
             "Accept": "text/html,application/xhtml+xml"}
os.makedirs("saida", exist_ok=True)
for n, link in enumerate((sys.argv[1] if len(sys.argv) > 1 else "").split()[:6]):
    try:
        r = requests.get(link, headers=NAVEGADOR, timeout=25)
    except requests.RequestException as e:
        print(link, "erro", type(e).__name__)
        continue
    h = r.text
    with open(f"saida/pagina_{n}.html", "w", encoding="utf-8") as f:
        f.write(h)
    print("=" * 30, link, r.status_code, len(h))
    print("final:", r.url[:400])
    print("historico:", [x.headers.get("location", "")[:200] for x in r.history])
    print("titulo:", (re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1][:150])
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            d = json.loads(m.group(1))
            print("ld:", json.dumps(d, ensure_ascii=False)[:500])
        except ValueError:
            pass
    print("pix:", [re.sub(r"<[^>]+>", " ", x)[:120] for x in re.findall(r".{150}no Pix.{60}", h)[:4]])
    print("fractions:", re.findall(r'andes-money-amount__fraction[^>]*>([\d.]+)<', h)[:14])
    print("aria:", re.findall(r'aria-label="((?:Antes: |Agora: )?[\d.]+ reais[^"]{0,40})"', h)[:14])
    print("item ids:", sorted(set(re.findall(r"MLB-?\d{9,}", h)))[:12])
    time.sleep(2)
