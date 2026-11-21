"""Transcreve áudios (narração de Reel) com tempo de cada palavra, usando faster-whisper.

Uso no workflow: script=transcrever, args = "nome=url nome=url ..."
Saída: saida/<nome>.json com segmentos e palavras ({inicio, fim, texto}).
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path


def main(args: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "faster-whisper"], check=True)
    from faster_whisper import WhisperModel

    saida = Path("saida")
    saida.mkdir(exist_ok=True)
    modelo = WhisperModel("small", device="cpu", compute_type="int8")
    for par in args.split():
        nome, url = par.split("=", 1)
        arq = Path("/tmp") / (nome + Path(url).suffix)
        urllib.request.urlretrieve(url, arq)
        segs, _ = modelo.transcribe(str(arq), language="pt", word_timestamps=True)
        res = []
        for s in segs:
            res.append({"inicio": round(s.start, 2), "fim": round(s.end, 2), "texto": s.text.strip(),
                        "palavras": [{"inicio": round(w.start, 2), "fim": round(w.end, 2), "texto": w.word.strip()}
                                     for w in (s.words or [])]})
        (saida / f"{nome}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print(nome, " ".join(r["texto"] for r in res))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
