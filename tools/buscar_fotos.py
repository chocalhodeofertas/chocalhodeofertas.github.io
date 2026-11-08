"""Busca fotos livres (CC0 / domínio público) no Openverse para as capas.

Roda no GitHub Actions (lá a internet é liberada). Salva em fotos_candidatas/<tema>/
com um creditos.json; depois a curadoria move as aprovadas para assets/capas/<tema>/.
"""
import io, json, sys, time
from pathlib import Path
import requests
from PIL import Image

TEMAS = {
    "familia": ["baby feet", "baby hands", "mother hands baby", "newborn sleeping", "pregnant belly", "pregnancy",
                "family walking", "father son walking", "mother child walking", "holding hands child", "baby sleeping",
                "mother baby", "father baby", "breastfeeding", "baby carrier"],
    "enxoval": ["nursery", "crib", "baby clothes", "baby room", "baby blanket", "baby shoes", "onesie", "baby shower", "diapers"],
    "brinquedos": ["toys", "wooden toys", "teddy bear", "building blocks", "lego", "toy car", "stuffed animal", "plush toy", "puzzle"],
    "passeio": ["stroller", "pram", "baby stroller park", "car seat"],
    "crianca": ["child playing", "kids playing", "child drawing", "crayons", "school backpack", "kids bicycle", "playground",
                "child running", "kids birthday party", "balloons kids"],
    "banho": ["baby bath", "towel baby", "rubber duck", "bath toys"],
}
POR_BUSCA = 20
SAIDA = Path("fotos_candidatas")
s = requests.Session()
s.headers["User-Agent"] = "chocalho-de-ofertas-bot/1.0"

vistos = set()
for tema, buscas in TEMAS.items():
    pasta = SAIDA / tema
    pasta.mkdir(parents=True, exist_ok=True)
    creditos = []
    n = 0
    for q, pg in [(b, p) for b in buscas for p in (1, 2)]:
        try:
            r = s.get("https://api.openverse.org/v1/images/", params={
                "q": q, "license": "cc0,pdm", "mature": "false",
                "source": "stocksnap,wordpress", "page_size": 20, "page": pg}, timeout=30)
            r.raise_for_status()
            res = r.json().get("results", [])
        except Exception as e:  # noqa: BLE001
            print("falhou busca", q, e, flush=True); time.sleep(20); continue
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
        print(tema, q, pegos, flush=True)
        time.sleep(4)
    (pasta / "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=1), encoding="utf-8")
