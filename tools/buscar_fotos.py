"""Busca fotos no Pexels para as capas (licença Pexels: uso comercial liberado, sem crédito obrigatório).

Roda no GitHub Actions com o segredo PEXELS_API_KEY. Salva candidatas em
fotos_candidatas/<tema>/ com creditos.json; a curadoria escolhe as que vão para assets/capas/.
"""
import io, json, os, time
from pathlib import Path
import requests
from PIL import Image, ImageStat

TEMAS = {
    "familia": ["família brasileira com bebê", "mãe brasileira com bebê", "pai segurando bebê", "mãe e filho brincando",
                "família feliz em casa", "pai e filha", "mãe amamentando", "grávida sorrindo", "brazilian family baby",
                "brazilian mother child"],
    "quarto": ["quarto de bebê", "berço de bebê", "quarto infantil decorado", "nursery bright", "baby crib white"],
    "enxoval": ["enxoval de bebê", "roupas de bebê", "chá de bebê", "fraldas bebê", "body de bebê", "baby clothes pastel"],
    "brinquedos": ["brinquedos coloridos", "brinquedos de madeira", "criança brincando com brinquedos", "bebê brincando",
                   "quarto de brinquedos", "pelúcia", "toys bright background"],
    "crianca": ["criança brincando", "criança desenhando", "criança feliz", "aniversário infantil", "volta às aulas criança",
                "criança de bicicleta", "brazilian kid"],
    "passeio": ["carrinho de bebê", "mãe passeando com carrinho de bebê", "cadeirinha de carro bebê", "baby stroller park"],
    "alimentacao": ["bebê comendo", "cadeira de alimentação bebê", "papinha bebê"],
    "banho": ["banho de bebê", "bebê na banheira", "toalha de bebê"],
}
POR_BUSCA = 15
SAIDA = Path("fotos_candidatas")
CHAVE = os.environ["PEXELS_API_KEY"]
s = requests.Session()
s.headers["Authorization"] = CHAVE

vistos = set()
for tema, buscas in TEMAS.items():
    pasta = SAIDA / tema
    pasta.mkdir(parents=True, exist_ok=True)
    creditos, n = [], 0
    for q in buscas:
        try:
            r = s.get("https://api.pexels.com/v1/search", params={
                "query": q, "orientation": "portrait", "size": "large", "locale": "pt-BR", "per_page": 40}, timeout=30)
            r.raise_for_status()
            fotos = r.json().get("photos", [])
        except Exception as e:  # noqa: BLE001
            print("falhou", q, e, flush=True); continue
        pegos = 0
        for f in fotos:
            if pegos >= POR_BUSCA or f["id"] in vistos:
                continue
            try:
                im = requests.get(f["src"]["original"] + "?auto=compress&cs=tinysrgb&w=1400", timeout=40)
                img = Image.open(io.BytesIO(im.content)).convert("RGB")
            except Exception:  # noqa: BLE001
                continue
            if ImageStat.Stat(img.convert("L")).mean[0] < 115:  # só fotos claras
                continue
            n += 1; pegos += 1; vistos.add(f["id"])
            nome = f"{tema}_{n:03d}.jpg"
            img.save(pasta / nome, quality=86)
            creditos.append({"arquivo": nome, "busca": q, "pexels_id": f["id"], "pagina": f["url"],
                             "fotografo": f["photographer"], "descricao": f.get("alt"), "licenca": "Pexels License"})
        print(tema, q, pegos, flush=True)
        time.sleep(1)
    (pasta / "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=1), encoding="utf-8")
