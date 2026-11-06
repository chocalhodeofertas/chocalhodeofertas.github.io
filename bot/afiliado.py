"""Monta o link de afiliado acrescentando os parâmetros de rastreamento.

São os mesmos parâmetros (matt_word e matt_tool) que aparecem no endereço
quando se abre um link gerado pelo painel de afiliados.
"""
from urllib.parse import urlencode, urlparse, urlunparse


def montar(url: str, matt_word: str, matt_tool: str) -> str:
    if not (matt_word and matt_tool):
        raise ValueError("faltam os parâmetros de afiliado (matt_word e matt_tool)")
    u = urlparse(url)
    query = urlencode({"matt_word": matt_word, "matt_tool": matt_tool})
    return urlunparse((u.scheme or "https", u.netloc, u.path, "", query, ""))
