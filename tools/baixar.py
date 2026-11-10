"""Baixa arquivos (cenas exportadas do Canva, fotos de produto) para saida/,
que o workflow de inspeção publica como artefato. Uso: nome=url nome=url ..."""
import sys
from pathlib import Path

import requests

saida = Path("saida")
saida.mkdir(exist_ok=True)
for par in " ".join(sys.argv[1:]).split():
    nome, _, url = par.partition("=")
    r = requests.get(url, timeout=60)
    print(nome, r.status_code, len(r.content), r.headers.get("content-type"))
    if r.ok:
        (saida / nome).write_bytes(r.content)
