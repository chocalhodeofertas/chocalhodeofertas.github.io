#!/usr/bin/env python3
"""Trava do Claude Code (PreToolUse) com duas regras do Chocalho:

1. Nunca abrir os links de afiliado do Leonardo (meli.la, s.shopee.com.br, shope.ee): abrir conta como clique e
   o Mercado Livre/Shopee pode entender como clique de robô. Vale para WebFetch, curl/wget/requests e para
   disparar ferramentas no GitHub (workflow inspecao) com esses links.
2. Não editar data/*.json na mão: o ciclo grava data/estado.json a cada rodada e uma edição paralela dá conflito
   ou apaga histórico de preço. Mudança de dados vai por código do bot (bot/estado.py carrega e migra).

Saída 2 = bloqueia e o motivo volta para o Claude.
"""
import json
import re
import sys

LINKS_DO_LEONARDO = re.compile(r"(https?://)?(www\.)?\b(meli\.la|s\.shopee\.com\.br|shope\.ee)/\S*", re.I)
NAVEGADOR = re.compile(r"chrome|browser|computer", re.I)  # Claude in Chrome, navegador do app, computer use
ABRE_REDE = re.compile(r"\b(curl|wget|requests\.(get|post|head)|urlopen|httpx|aiohttp|playwright|chromium|selenium)\b"
                       r"|gh\s+api\b.*dispatches|gh\s+workflow\s+run", re.I | re.S)
DADOS = re.compile(r"(^|/)data/\S+\.json$")
ESCREVE_DADOS = re.compile(
    r"(sed\s+-i[^|;&\n]*|>>?\s*|tee\s+(-a\s+)?|\bcp\s+\S+\s+|\bmv\s+\S+\s+)(\S*/)?data/[^\s'\"]+\.json"
    r"|data/[^\s'\"]+\.json['\"]\s*,\s*['\"][wa]"
)


def bloquear(motivo):
    print(f"Bloqueado pela trava do Chocalho: {motivo}", file=sys.stderr)
    sys.exit(2)


def main():
    try:
        dados = json.load(sys.stdin)
    except ValueError:
        return
    ferramenta = dados.get("tool_name") or ""
    entrada = dados.get("tool_input") or {}

    if ferramenta.startswith("mcp__") and NAVEGADOR.search(ferramenta):
        if LINKS_DO_LEONARDO.search(json.dumps(entrada, ensure_ascii=False)):
            bloquear("o navegador abriria um link de afiliado do Leonardo. Decisão dele (16/11): nunca abrir os links "
                     "de afiliado dele, nem pelo navegador.")
        return

    if ferramenta == "WebFetch":
        if LINKS_DO_LEONARDO.search(entrada.get("url") or ""):
            bloquear("é um link de afiliado do Leonardo. Ele não aceita que o bot ou o Claude abram os links dele "
                     "(conta como clique). Use a API oficial (catálogo do ML / API de afiliados da Shopee).")
        return

    if ferramenta == "Bash":
        cmd = entrada.get("command") or ""
        if LINKS_DO_LEONARDO.search(cmd) and ABRE_REDE.search(cmd):
            bloquear("o comando abriria um link de afiliado do Leonardo (meli.la / s.shopee.com.br / shope.ee). "
                     "Decisão dele (16/11): nunca abrir os links de afiliado. Use a API oficial.")
        if ESCREVE_DADOS.search(cmd):
            bloquear("o comando grava em data/*.json. O ciclo grava esses arquivos sozinho a cada rodada; mude os "
                     "dados pelo código do bot (ex.: migração em bot/estado.py ao carregar), não na mão.")
        return

    if ferramenta in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        caminho = entrada.get("file_path") or entrada.get("notebook_path") or ""
        if DADOS.search(caminho):
            bloquear(f"{caminho} é gravado pelo ciclo do bot. Mude os dados pelo código (bot/estado.py), não na mão.")


if __name__ == "__main__":
    main()
