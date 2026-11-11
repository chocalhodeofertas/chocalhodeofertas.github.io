"""Histórico de preços e do que já foi postado (fica em data/estado.json)."""
import json
from pathlib import Path

MAX_HISTORICO = 60


def novo():
    return {"precos": {}, "postados": {}, "contagem_dia": {}, "links": {}, "lote": None}


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


def registrar_post(estado, pid, preco, agora, titulo=None, desconto=None):
    estado["postados"][pid] = {"quando": agora.isoformat(timespec="minutes"), "preco": preco}
    if titulo:
        estado["postados"][pid]["titulo"] = titulo[:80]
    if desconto is not None:
        estado["postados"][pid]["desconto"] = round(desconto, 3)
    dia = agora.date().isoformat()
    # Só guarda a contagem de hoje
    estado["contagem_dia"] = {dia: estado["contagem_dia"].get(dia, 0) + 1}
    contar_dia(estado, agora, "posts")


def contar_dia(estado, agora, chave, n=1, dias=30):
    """Histórico diário para a página de números (posts, cupons, com_cupom)."""
    hist = estado.setdefault("hist_dia", {})
    dia = agora.date().isoformat()
    hist.setdefault(dia, {})
    hist[dia][chave] = hist[dia].get(chave, 0) + n
    for d in sorted(hist)[:-dias]:
        del hist[d]


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


def titulos_recentes(estado, agora, dias=3):
    """Títulos postados (Mercado Livre e Shopee) nos últimos dias."""
    from datetime import datetime, timedelta

    corte = agora - timedelta(days=dias)
    saida = []
    fontes = list(estado.get("postados", {}).values()) + list(estado.get("shopee", {}).get("titulos", {}).values())
    for v in fontes:
        try:
            if v.get("titulo") and datetime.fromisoformat(v["quando"]) > corte:
                saida.append((v["titulo"], v.get("preco")))
        except (KeyError, ValueError, TypeError, AttributeError):
            pass
    return saida


def repetido(estado, titulo, agora, dias=3, preco=None):
    """True se um produto igual ou bem parecido já saiu nos últimos dias.
    Volta antes do prazo só se o preço agora estiver 5% abaixo do que foi postado."""
    from .ofertas import parecido

    for t, p in titulos_recentes(estado, agora, dias):
        if parecido(titulo, t) and not (preco and p and preco <= p * 0.95):
            return True
    return False
