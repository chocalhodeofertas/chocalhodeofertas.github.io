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
    compactar_precos(estado)
    if "links_item" not in estado:  # uma vez: qual anúncio cada link antigo abre (tirado dos lotes já respondidos)
        inicial = p.parent / "links_item_inicial.json"
        if inicial.exists():
            estado["links_item"] = {k: v for k, v in json.loads(inicial.read_text()).items() if k in estado["links"]}
    if "posts_hist" not in estado:  # uma vez: todos os posts desde 06/11, refeitos a partir do histórico do git
        inicial = p.parent / "posts_hist_inicial.json"
        estado["posts_hist"] = json.loads(inicial.read_text()) if inicial.exists() else []
    refazer_lote_17_11(estado)
    return estado


def refazer_lote_17_11(estado):
    """Uma vez (pedido do Leonardo, 17/11): o lote de 17/11 tinha vendedor vermelho/laranja e itens fora do nicho.
    Descarta o lote pendente (sem contar como lote do dia); a próxima rodada monta outro já com as regras novas."""
    lote = estado.get("lote") or {}
    if lote.get("dia") == "2026-11-17" and "MLB26414752" in (lote.get("ids") or []):
        estado["lote"] = None
        dias = estado.get("lotes_dia") or {}
        if dias.get("2026-11-17"):
            dias["2026-11-17"] -= 1


def compactar_precos(estado):
    """Em cada dia, guarda cada preço diferente uma vez só (na ordem em que apareceu por último).

    No Mercado Livre, alguns produtos alternam entre dois preços a cada consulta (lojas diferentes
    ganhando a vez). Sem isso, o vai-e-vem enchia o histórico e apagava os dias mais antigos."""
    for reg in (estado.get("precos") or {}).values():
        hist = reg.get("historico") or []
        if len(hist) < 3:
            continue
        novo_hist, vistos = [], set()
        for d, preco in reversed(hist):
            if (d, preco) not in vistos:
                vistos.add((d, preco))
                novo_hist.append([d, preco])
        if len(novo_hist) != len(hist):
            reg["historico"] = novo_hist[::-1]


def salvar(caminho, estado):
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(estado, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def registrar_preco(estado, pid, preco, agora):
    """Guarda o preço só quando ele muda, para o arquivo não crescer à toa.
    No mesmo dia, cada preço fica uma vez só: se ele volta a aparecer, vai para o fim da fila
    (o último registro é sempre o preço em vigor; o menor do dia é o que vale para o histórico)."""
    reg = estado["precos"].setdefault(pid, {"min": preco, "historico": []})
    hist = reg["historico"]
    if not hist or hist[-1][1] != preco:
        dia = agora.date().isoformat()
        for i in range(len(hist) - 1, -1, -1):
            if hist[i][0] != dia:
                break
            if hist[i][1] == preco:
                del hist[i]
                break
        hist.append([dia, preco])
        del hist[:-MAX_HISTORICO]
    reg["min"] = min(reg["min"], preco)


# ---------------------------------------------------------------- repetição
# Um produto (mesmo anúncio OU título parecido, em qualquer loja) só volta ao canal depois de REPOST_DIAS.
# Antes disso, só se o preço estiver REPOST_QUEDA (10%) abaixo do MENOR preço com que ele já saiu nesse período
# (antes era 5% abaixo do último post: produto que alterna entre dois preços, ou variações de cor com preços
# diferentes, voltava a cada poucos dias como se tivesse baixado).
HIST_POSTS_DIAS = 45


def _queda_minima():
    import os
    try:
        return float(os.environ.get("REPOST_QUEDA") or 0.05)
    except ValueError:
        return 0.05


def anotar_post(estado, pid, preco, agora, titulo=None):
    """Guarda cada post (ML e Shopee) para a regra de repetição: [id, quando, preço, título]."""
    from datetime import timedelta

    hist = estado.setdefault("posts_hist", [])
    hist.append([pid, agora.isoformat(timespec="minutes"), preco, (titulo or "")[:80]])
    corte = (agora - timedelta(days=HIST_POSTS_DIAS)).isoformat()
    estado["posts_hist"] = [x for x in hist if x[1] >= corte]


def _posts_conhecidos(estado):
    vistos = {(x[0], x[1]) for x in estado.get("posts_hist") or []}
    saida = [tuple(x) for x in estado.get("posts_hist") or []]
    fontes = [(k, v) for k, v in (estado.get("postados") or {}).items()]
    fontes += [(k, v) for k, v in ((estado.get("shopee") or {}).get("titulos") or {}).items()]
    for pid, v in fontes:  # posts antigos ou gravados por outro caminho
        if isinstance(v, dict) and v.get("quando") and (pid, v["quando"]) not in vistos:
            saida.append((pid, v["quando"], v.get("preco"), v.get("titulo") or ""))
    return saida


def checar_repeticao(estado, pid, titulo, preco, agora, dias=7, mesmos=()):
    """None = nunca saiu no período. Senão, dict com:
    bloqueado (True = não pode sair), quando/preco (último post), menor (menor preço já postado), queda.
    mesmos: ids de outros anúncios já reconhecidos como o mesmo produto (pela foto: bot/foto.py)."""
    from datetime import datetime, timedelta

    from .ofertas import REPOSICAO_DIAS, mesmo_item_reposicao, parecido, reposicao

    # Item de reposição (fralda, lenço...): só o MESMO item (marca + tamanho) conta, e volta em REPOSICAO_DIAS
    eh_reposicao = bool(reposicao(titulo))
    corte = agora - timedelta(days=REPOSICAO_DIAS if eh_reposicao else dias)
    antes = []
    for p_id, quando, p_preco, p_titulo in _posts_conhecidos(estado):
        try:
            t = datetime.fromisoformat(quando)
        except (TypeError, ValueError):
            continue
        if t <= corte or t > agora:
            continue
        if p_id in mesmos:
            igual = True
        elif eh_reposicao:
            igual = p_id == pid or (titulo and p_titulo and mesmo_item_reposicao(titulo, p_titulo))
        else:
            igual = p_id == pid or (titulo and p_titulo and parecido(titulo, p_titulo) and not reposicao(p_titulo))
        if igual:
            antes.append((t, p_preco, p_id))
    if not antes:
        return None
    ultimo = max(antes)
    precos = [p for _, p, _ in antes if p]
    menor = min(precos) if precos else None
    queda = (1 - preco / menor) if (preco and menor) else 0.0
    return {"bloqueado": not (menor and queda >= _queda_minima() - 1e-9), "quando": ultimo[0].isoformat(timespec="minutes"),
            "preco": ultimo[1], "menor": menor, "queda": round(queda, 3), "mesmo_anuncio": ultimo[2] == pid,
            "vezes": len(antes), "pela_foto": bool(mesmos) and ultimo[2] in mesmos}


def registrar_post(estado, pid, preco, agora, titulo=None, desconto=None):
    anotar_post(estado, pid, preco, agora, titulo)
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


def repetido(estado, titulo, agora, dias=3, preco=None, pid=None):
    """True se o produto (ou um bem parecido) já saiu nos últimos dias e o preço não caiu o bastante
    (ver checar_repeticao)."""
    r = checar_repeticao(estado, pid, titulo, preco, agora, dias)
    return bool(r and r["bloqueado"])


def serie_diaria(estado, pid, agora, dias=30, com_hoje=False):
    """Preço do produto dia a dia: [(date, preço)], do começo da janela até ontem (ou hoje, com_hoje=True).

    Em cada dia vale o MENOR preço visto (se num dia o produto apareceu a R$ 30 e a R$ 40, ele esteve
    disponível a R$ 30). Dia sem registro repete o último preço em vigor."""
    from datetime import date, timedelta

    hist = (estado.get("precos", {}).get(pid) or {}).get("historico") or []
    if not hist:
        return []
    hoje = agora.date()
    menor, ultimo = {}, {}
    for d, preco in hist:
        d = date.fromisoformat(d)
        menor[d] = min(menor.get(d, preco), preco)
        ultimo[d] = preco
    dia = max(min(menor), hoje - timedelta(days=dias))
    em_vigor = None
    for d in sorted(ultimo):  # preço em vigor no começo da janela
        if d < dia:
            em_vigor = ultimo[d]
    serie = []
    fim = hoje if com_hoje else hoje - timedelta(days=1)
    while dia <= fim:
        if dia in menor:
            serie.append((dia, menor[dia]))
            em_vigor = ultimo[dia]
        elif em_vigor is not None:
            serie.append((dia, em_vigor))
        dia += timedelta(days=1)
    return serie


def preco_tipico(estado, pid, agora, dias=30):
    """Preço "normal" do produto pelo histórico do próprio bot: mediana dia a dia dos últimos dias
    (em cada dia vale o menor preço visto; hoje fica de fora, é o preço que está sendo avaliado).

    Retorna (preço típico, dias de observação) ou (None, 0). A mediana não se deixa enganar
    por um preço inflado por poucos dias (ex.: vendedor que sobe antes da Black Friday)."""
    from datetime import date

    hist = (estado.get("precos", {}).get(pid) or {}).get("historico") or []
    if not hist:
        return None, 0
    dias_obs = (agora.date() - date.fromisoformat(hist[0][0])).days
    serie = sorted(p for _, p in serie_diaria(estado, pid, agora, dias))
    if not serie:
        return None, dias_obs
    meio = len(serie) // 2
    tipico = serie[meio] if len(serie) % 2 else (serie[meio - 1] + serie[meio]) / 2
    return tipico, dias_obs
