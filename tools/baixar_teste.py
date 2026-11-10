"""Testa se dá para baixar a imagem do Canva em tamanho cheio a partir da URL de miniatura."""
import sys
import requests

url = sys.argv[1]
grande = url.replace("height:200", "height:1408").replace("width:161", "width:1136")
for nome, u in [("mini", url), ("grande", grande)]:
    r = requests.get(u, timeout=30)
    print(nome, r.status_code, len(r.content), r.headers.get("content-type"))
