"""Mantém o bot rodando em ciclo dentro de uma execução do GitHub Actions.

A cada 20 minutos, dentro do horário de postagem, roda uma rodada normal e
salva o histórico no repositório. Depois de algumas horas, termina; o
workflow dispara a próxima execução, e o ciclo continua.

Uso: python -m bot.ciclo --horas 5.5
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
INTERVALO = timedelta(minutes=20)
RAPIDO_SEG = 120


def log(msg):
    print(f"[{datetime.now(FUSO):%d/%m %H:%M}] {msg}", flush=True)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def sincronizar_antes():
    """Pega edições feitas no repositório (ex.: produtos.csv) antes de cada rodada."""
    r = git("pull", "--rebase", "--autostash", "-q", "origin", os.environ.get("GITHUB_REF_NAME", "main"))
    if r.returncode != 0:
        log(f"Aviso: git pull falhou: {r.stderr.strip()[:200]}")


def salvar_estado():
    git("add", "data/estado.json")
    git("add", "docs")  # separado: se a pasta não existir, não atrapalha o resto
    if git("diff", "--cached", "--quiet").returncode == 0:
        return
    git("commit", "-q", "-m", "Atualiza histórico de preços e página [skip ci]")
    for _ in range(3):
        sincronizar_antes()
        if git("push", "-q").returncode == 0:
            return
        time.sleep(5)
    log("Aviso: não consegui salvar o histórico nesta rodada.")


def proximo_horario(agora, inicio, fim):
    """Daqui a 20 min; se cair fora do horário de postagem, pula para o início do dia seguinte."""
    prox = agora + INTERVALO
    if inicio <= prox.hour < fim:
        return prox
    dia = prox.date() if prox.hour < inicio else prox.date() + timedelta(days=1)
    return datetime(dia.year, dia.month, dia.day, inicio, 2, tzinfo=FUSO)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=float, default=5.5)
    args = ap.parse_args(argv)

    inicio = int(os.environ.get("HORA_INICIO") or 8)
    fim = int(os.environ.get("HORA_FIM") or 22)
    limite = datetime.now(FUSO) + timedelta(hours=args.horas)
    log(f"Ciclo iniciado; vai até {limite:%H:%M}.")

    while True:
        agora = datetime.now(FUSO)
        inicio_rodada = agora
        if inicio <= agora.hour < fim:
            sincronizar_antes()
            r = subprocess.run([sys.executable, "-m", "bot.main", "--modo", "normal"])
            if r.returncode != 0:
                log(f"Rodada terminou com erro (código {r.returncode}); sigo para a próxima.")
            salvar_estado()

        # Conta 20 min a partir do INÍCIO da rodada (os posts espaçados tomam parte desse tempo)
        prox = max(proximo_horario(inicio_rodada, inicio, fim), datetime.now(FUSO))
        if prox >= limite:
            # Espera até o limite (inclusive de madrugada) para não emendar execuções vazias
            espera = (limite - datetime.now(FUSO)).total_seconds()
            if espera > 0:
                log(f"Aguardando até {limite:%H:%M} para passar a vez.")
                time.sleep(espera)
            log("Encerrando esta execução; a próxima continua o ciclo.")
            return 0
        log(f"Próxima rodada às {prox:%H:%M}.")
        # Até lá, a cada 2 min: suas mensagens e o canal de cupons
        while (espera := (prox - datetime.now(FUSO)).total_seconds()) > 0:
            time.sleep(min(RAPIDO_SEG, espera))
            agora = datetime.now(FUSO)
            if inicio <= agora.hour < fim and (prox - agora).total_seconds() > 30:
                sincronizar_antes()
                subprocess.run([sys.executable, "-m", "bot.main", "--modo", "rapido"])
                salvar_estado()


if __name__ == "__main__":
    sys.exit(main())
