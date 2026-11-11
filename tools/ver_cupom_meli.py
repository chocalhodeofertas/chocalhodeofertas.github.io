"""Teste: abre links meli.la como navegador e mostra o que a página diz de cupom
(bloco 'promotions' do JSON polycards). Uso: url url ..."""
import json
import re
import sys
from pathlib import Path

import requests

from bot.comandos import UA

saida = Path("saida")
saida.mkdir(exist_ok=True)
for n, url in enumerate(" ".join(sys.argv[1:]).split()):
    r = requests.get(url, headers={**UA, "Accept-Language": "pt-BR,pt;q=0.9"}, timeout=30)
    h = r.text or ""
    print(f"\n### {url} -> {r.status_code} {r.url[:90]} ({len(h)} bytes)")
    (saida / f"pagina{n}.html").write_text(h)
    i = h.find('"polycards":')
    if i < 0:
        print("sem polycards")
    else:
        cards, _ = json.JSONDecoder().raw_decode(h[i + 12:])
        for c in cards[:2]:
            comps = {x["type"]: x.get(x["type"]) for x in c.get("components", [])}
            print(c.get("metadata", {}).get("id"), (comps.get("title") or {}).get("text"))
            print("  preço:", json.dumps(comps.get("price"), ensure_ascii=False)[:300])
            print("  promoções:", json.dumps(comps.get("promotions"), ensure_ascii=False)[:800])
    for m in list(re.finditer(r".{60}[Cc]upom.{100}", h))[:6]:
        print("  >>", m.group(0))
