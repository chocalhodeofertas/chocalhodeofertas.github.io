"""Histórico de preços e do que já foi postado (fica em data/estado.json)."""
import json
from pathlib import Path

MAX_HISTORICO = 60


def novo():
    return {"precos": {}, "postados": {}, "contagem_dia": {}}


def carregar(caminho):
    p = Path(caminho)
    if not p.exists() or not p.read_text().strip():
        return novo()
    estado = json.loads(p.read_text())
    for chave, valor in novo().items():
        estado.setdefault(chave, valor)
    return estado


def salvar(caminho, estado):
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(estado, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def registrar_preco(estado, pid, preco, agora):
    """Guarda o preço só quando ele muda, para o arquivo não crescer à toa."""
    reg = estado["precos"].setdefault(pid, {"min": preco, "historico": []})
    hist = reg["historico"]
    if not hist or hist[-1][1] != preco:
        hist.append([agora.date().isoformat(), preco])
        del hist[:-MAX_HISTORICO]
    reg["min"] = min(reg["min"], preco)


def registrar_post(estado, pid, preco, agora):
    estado["postados"][pid] = {"quando": agora.isoformat(timespec="minutes"), "preco": preco}
    dia = agora.date().isoformat()
    # Só guarda a contagem de hoje
    estado["contagem_dia"] = {dia: estado["contagem_dia"].get(dia, 0) + 1}


def posts_hoje(estado, agora):
    return estado["contagem_dia"].get(agora.date().isoformat(), 0)


def posts_ultima_hora(estado, agora):
    """Quantos posts foram feitos nos últimos 60 minutos."""
    from datetime import datetime

    total = 0
    for p in estado["postados"].values():
        try:
            if (agora - datetime.fromisoformat(p["quando"])).total_seconds() < 3600:
                total += 1
        except (KeyError, ValueError, TypeError):
            pass
    return total
