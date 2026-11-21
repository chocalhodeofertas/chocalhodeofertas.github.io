"""Gera narração com vozes abertas do Piper (pt-BR) e salva em saida/.

Uso no workflow: script=narrar, args = JSON {"vozes": ["faber", ...], "falas": ["...", ...]}
Saída: saida/<voz>_<n>.wav, uma por fala.
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR"
QUALIDADE = {"faber": "medium", "cadu": "medium", "jeff": "medium", "edresson": "low"}


def main(args: str) -> None:
    cfg = json.loads(args)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "piper-tts"], check=True)
    saida = Path("saida")
    saida.mkdir(exist_ok=True)
    modelos = Path("/tmp/piper")
    modelos.mkdir(exist_ok=True)
    for voz in cfg["vozes"]:
        q = QUALIDADE.get(voz, "medium")
        nome = f"pt_BR-{voz}-{q}"
        try:
            for ext in (".onnx", ".onnx.json"):
                destino = modelos / (nome + ext)
                if not destino.exists():
                    urllib.request.urlretrieve(f"{BASE}/{voz}/{q}/{nome}{ext}", destino)
        except Exception as e:  # voz que não existe é só pulada
            print(f"voz {voz}: {e}")
            continue
        for i, fala in enumerate(cfg["falas"], 1):
            subprocess.run(
                [sys.executable, "-m", "piper", "-m", str(modelos / (nome + ".onnx")),
                 "-f", str(saida / f"{voz}_{i}.wav"),
                 "--length-scale", str(cfg.get("ritmo", 0.95))],
                input=fala.encode(), check=True)
        print(f"voz {voz}: ok")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "{}")
