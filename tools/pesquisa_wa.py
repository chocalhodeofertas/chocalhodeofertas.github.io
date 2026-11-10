"""Pesquisa no GitHub sobre bibliotecas de WhatsApp: números dos repositórios,
avisos do README e o que aparece nas issues sobre banimento. Saída em saida/."""
import json
import os
import re
import time
from pathlib import Path

import requests

S = requests.Session()
tok = os.environ.get("GITHUB_TOKEN")
if tok:
    S.headers["Authorization"] = f"Bearer {tok}"
S.headers["Accept"] = "application/vnd.github+json"

REPOS = ["WhiskeySockets/Baileys", "pedroslopez/whatsapp-web.js", "wppconnect-team/wppconnect",
         "EvolutionAPI/evolution-api", "devlikeapro/waha", "orkestral/venom", "tulir/whatsmeow",
         "open-wa/wa-automate-nodejs", "aldinokemal/go-whatsapp-web-multidevice", "mdtsoftware/whatsapp-mcp",
         "lharries/whatsapp-mcp", "asternic/wuzapi"]
PALAVRAS = ["ban", "banned", "banido", "bloqueado", "blocked", "restricted", "restrição"]


def get(url, **kw):
    for _ in range(3):
        r = S.get(url, timeout=30, **kw)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            time.sleep(20)
            continue
        return r
    return r


saida = {"repos": {}, "issues": {}}
for full in REPOS:
    r = get(f"https://api.github.com/repos/{full}")
    if r.status_code != 200:
        saida["repos"][full] = {"erro": r.status_code}
        continue
    j = r.json()
    info = {k: j.get(k) for k in ("stargazers_count", "forks_count", "open_issues_count", "pushed_at", "archived",
                                    "description", "language")}
    info["license"] = (j.get("license") or {}).get("spdx_id")
    rel = get(f"https://api.github.com/repos/{full}/releases?per_page=3")
    if rel.status_code == 200:
        info["releases"] = [(x["tag_name"], x["published_at"][:10]) for x in rel.json()]
    rd = get(f"https://api.github.com/repos/{full}/readme", headers={"Accept": "application/vnd.github.raw"})
    if rd.status_code == 200:
        txt = rd.text
        trechos = []
        for m in re.finditer(r"(?i)(disclaimer|not affiliated|ban|block|spam|bulk|stalkerware|official)", txt):
            a = max(0, m.start() - 200)
            trechos.append(re.sub(r"\s+", " ", txt[a:m.start() + 300]))
        info["readme_avisos"] = trechos[:6]
    saida["repos"][full] = info
    time.sleep(1)

consultas = {
    "baileys_ban": 'repo:WhiskeySockets/Baileys ban in:title,body',
    "wwebjs_ban": 'repo:pedroslopez/whatsapp-web.js ban in:title,body',
    "evolution_ban": 'repo:EvolutionAPI/evolution-api ban in:title,body',
    "waha_ban": 'repo:devlikeapro/waha ban in:title,body',
    "whatsmeow_ban": 'repo:tulir/whatsmeow ban in:title,body',
    "baileys_group": 'repo:WhiskeySockets/Baileys group send in:title',
    "baileys_pairing": 'repo:WhiskeySockets/Baileys pairing code in:title',
}
for nome, q in consultas.items():
    r = get("https://api.github.com/search/issues", params={"q": q, "sort": "comments", "order": "desc", "per_page": 12})
    if r.status_code != 200:
        saida["issues"][nome] = {"erro": r.status_code, "msg": r.text[:200]}
        continue
    itens = []
    for it in r.json().get("items", []):
        itens.append({"titulo": it["title"], "url": it["html_url"], "estado": it["state"],
                      "comentarios": it["comments"], "criado": it["created_at"][:10],
                      "reacoes": (it.get("reactions") or {}).get("total_count"),
                      "trecho": re.sub(r"\s+", " ", (it.get("body") or ""))[:500]})
    saida["issues"][nome] = {"total": r.json().get("total_count"), "itens": itens}
    time.sleep(7)

# Comentários das 4 issues mais comentadas sobre ban no Baileys e no whatsapp-web.js
for nome in ("baileys_ban", "wwebjs_ban", "evolution_ban"):
    for it in (saida["issues"].get(nome, {}).get("itens") or [])[:4]:
        api = it["url"].replace("https://github.com/", "https://api.github.com/repos/").replace("/pull/", "/issues/")
        r = get(api + "/comments", params={"per_page": 40})
        if r.status_code == 200:
            it["comentarios_texto"] = [re.sub(r"\s+", " ", c.get("body") or "")[:400] for c in r.json()][:40]
        time.sleep(1)

Path("saida").mkdir(exist_ok=True)
Path("saida/pesquisa_wa.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok", {k: v.get("stargazers_count") for k, v in saida["repos"].items()})
