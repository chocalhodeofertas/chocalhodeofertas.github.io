"""Busca fotos livres (CC0 / domínio público) no Openverse para as capas.

Roda no GitHub Actions (lá a internet é liberada). Salva em fotos_candidatas/<tema>/
com um creditos.json; depois a curadoria move as aprovadas para assets/capas/<tema>/.
"""
import io, json, sys, time
from pathlib import Path
import requests
from PIL import Image

TEMAS = {
    "familia": ["mother holding baby", "father holding baby", "parent baby hands", "mom and toddler walking",
                "family with baby", "pregnant belly", "dad and child playing"],
    "enxoval": ["nursery room", "baby crib", "baby clothes", "baby room", "baby blanket", "baby shoes"],
    "brinquedos": ["wooden toys", "toys colorful", "teddy bear", "building blocks toys", "toy car", "baby toys"],
    "passeio": ["baby stroller", "stroller park", "car seat baby"],
    "crianca": ["child playing", "kids playing outdoor", "child drawing", "school backpack", "kids bicycle", "playground"],
    "banho": ["baby bath", "baby towel", "rubber duck bath"],
}
POR_BUSCA = 12
SAIDA = Path("fotos_candidatas")
s = requests.Session()
s.headers["User-Agent"] = "chocalho-de-ofertas-bot/1.0"

vistos = set()
for tema, buscas in TEMAS.items():
    pasta = SAIDA / tema
    pasta.mkdir(parents=True, exist_ok=True)
    creditos = []
    n = 0
    for q in buscas:
        try:
            r = s.get("https://api.openverse.org/v1/images/", params={
                "q": q, "license": "cc0,pdm", "category": "photograph", "mature": "false",
                "size": "large", "page_size": 30}, timeout=30)
            r.raise_for_status()
            res = r.json().get("results", [])
        except Exception as e:  # noqa: BLE001
            print("falhou busca", q, e); continue
        pegos = 0
        for it in res:
            if pegos >= POR_BUSCA or it["id"] in vistos:
                continue
            w, h = it.get("width") or 0, it.get("height") or 0
            if w and h and (min(w, h) < 900):
                continue
            try:
                im = s.get(it["url"], timeout=40)
                im.raise_for_status()
                img = Image.open(io.BytesIO(im.content)).convert("RGB")
            except Exception:  # noqa: BLE001
                continue
            if min(img.size) < 900:
                continue
            img.thumbnail((1800, 1800))
            n += 1; pegos += 1; vistos.add(it["id"])
            nome = f"{tema}_{n:03d}.jpg"
            img.save(pasta / nome, quality=88)
            creditos.append({"arquivo": nome, "busca": q, "titulo": it.get("title"), "autor": it.get("creator"),
                             "licenca": f'{it.get("license")} {it.get("license_version") or ""}'.strip(),
                             "fonte": it.get("source"), "pagina": it.get("foreign_landing_url"), "openverse_id": it["id"]})
            time.sleep(0.3)
        print(tema, q, pegos)
    (pasta / "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=1), encoding="utf-8")
