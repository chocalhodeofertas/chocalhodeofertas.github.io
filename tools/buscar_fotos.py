"""Busca fotos para as capas no Pixabay (ou no Pexels, se houver chave).

Licenças de ambos: uso comercial liberado, sem crédito obrigatório.
Roda no GitHub Actions com o segredo PIXABAY_API_KEY (ou PEXELS_API_KEY). Salva candidatas em
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
PIXABAY = os.environ.get("PIXABAY_API_KEY")
PEXELS = os.environ.get("PEXELS_API_KEY")
s = requests.Session()
if PEXELS:
    s.headers["Authorization"] = PEXELS


def buscar(q):
    """Lista de (id, url_da_imagem, pagina, autor, descricao)."""
    if PIXABAY:
        r = s.get("https://pixabay.com/api/", params={
            "key": PIXABAY, "q": q, "lang": "pt", "image_type": "photo", "orientation": "vertical",
            "safesearch": "true", "per_page": 60, "min_width": 900}, timeout=30)
        r.raise_for_status()
        return [(h["id"], h["largeImageURL"], h["pageURL"], h["user"], h.get("tags")) for h in r.json().get("hits", [])]
    r = s.get("https://api.pexels.com/v1/search", params={
        "query": q, "orientation": "portrait", "size": "large", "locale": "pt-BR", "per_page": 40}, timeout=30)
    r.raise_for_status()
    return [(f["id"], f["src"]["original"] + "?auto=compress&cs=tinysrgb&w=1400", f["url"], f["photographer"],
             f.get("alt")) for f in r.json().get("photos", [])]

vistos = set()
for tema, buscas in TEMAS.items():
    pasta = SAIDA / tema
    pasta.mkdir(parents=True, exist_ok=True)
    creditos, n = [], 0
    for q in buscas:
        try:
            fotos = buscar(q)
        except Exception as e:  # noqa: BLE001
            print("falhou", q, e, flush=True); continue
        pegos = 0
        for fid, url, pagina, autor, descricao in fotos:
            if pegos >= POR_BUSCA or fid in vistos:
                continue
            try:
                im = requests.get(url, timeout=40)
                img = Image.open(io.BytesIO(im.content)).convert("RGB")
            except Exception:  # noqa: BLE001
                continue
            if ImageStat.Stat(img.convert("L")).mean[0] < 115:  # só fotos claras
                continue
            n += 1; pegos += 1; vistos.add(fid)
            nome = f"{tema}_{n:03d}.jpg"
            img.save(pasta / nome, quality=86)
            creditos.append({"arquivo": nome, "busca": q, "id": fid, "pagina": pagina, "autor": autor,
                             "descricao": descricao, "licenca": "Pixabay Content License" if PIXABAY else "Pexels License"})
        print(tema, q, pegos, flush=True)
        time.sleep(1)
    (pasta / "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=1), encoding="utf-8")
