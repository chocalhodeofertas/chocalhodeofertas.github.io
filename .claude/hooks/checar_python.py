#!/usr/bin/env python3
"""Conferência rápida (PostToolUse) depois de editar um arquivo Python do repositório.

Roda o pyflakes no arquivo editado: pega na hora nome usado sem importar, variável não definida, import sobrando.
Sem pyflakes instalado, só confere se o arquivo compila. Achou problema: saída 2, e o aviso volta para o Claude.
(Instalar: pip install pyflakes --break-system-packages)
"""
import json
import subprocess
import sys


def main():
    try:
        dados = json.load(sys.stdin)
    except ValueError:
        return
    caminho = (dados.get("tool_input") or {}).get("file_path") or ""
    if not caminho.endswith(".py"):
        return
    r = subprocess.run([sys.executable, "-m", "pyflakes", caminho], capture_output=True, text=True)
    if "No module named pyflakes" in (r.stderr or ""):
        r = subprocess.run([sys.executable, "-m", "py_compile", caminho], capture_output=True, text=True)
    saida = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0 and saida:
        print(f"Conferência do Python achou problema em {caminho}:\n{saida[:2000]}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
