"""Página de números do Chocalho (subpágina do site, sem link em lugar nenhum
e marcada para não aparecer em buscadores). O bot reescreve a cada rodada.

Fontes: data/estado.json (Telegram, posts, cupons) e data/wa_estado.json
(escrito pelo wa/servico.mjs: membros do grupo, posts no grupo, links apagados).
"""
import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import paginas
from .paginas import plural

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "docs" / "numeros-bcfc6fce.html"
ARQ_WA = RAIZ / "data" / "wa_estado.json"
DIAS_HIST = 30


# ---------- coleta ----------

def contar(estado, agora, chave, n=1):
    """Contador diário (posts, cupons, com_cupom), guardando 30 dias."""
    from .estado import contar_dia

    contar_dia(estado, agora, chave, n)


def atualizar_membros(estado, tg, canal, agora):
    """Guarda o total de membros do canal (no máximo 1 consulta por hora)."""
    if not tg or not canal:
        return
    marca = agora.isoformat()[:13]
    if estado.get("membros_lido_em") == marca:
        return
    try:
        total = tg.membros(canal)
    except Exception:  # noqa: BLE001
        return
    hist = estado.setdefault("membros_hist", {})
    hist[agora.date().isoformat()] = total
    for d in sorted(hist)[:-DIAS_HIST]:
        del hist[d]
    estado["membros_lido_em"] = marca


def _ler_wa(arquivo=ARQ_WA):
    try:
        return json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------- desenho ----------

def _brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _delta(serie, dias_atras):
    """Variação entre o último valor e o de N dias antes (ou None)."""
    if not serie:
        return None
    ultimo_dia = max(serie)
    alvo = (date.fromisoformat(ultimo_dia) - timedelta(days=dias_atras)).isoformat()
    return serie[ultimo_dia] - serie[alvo] if alvo in serie else None


def _fmt_delta(d, sufixo):
    if d is None:
        return f'<span class="mudo">sem dado {sufixo}</span>'
    classe = "sobe" if d > 0 else "desce" if d < 0 else "mudo"
    seta = "▲" if d > 0 else "▼" if d < 0 else "•"
    return f'<span class="{classe}">{seta} {d:+d} {sufixo}</span>'


def _grafico_linha(serie, dias, titulo, hoje):
    """Linha de 2px com área suave, um eixo, rótulo só no último ponto."""
    eixo = [(hoje - timedelta(days=dias - 1 - k)).isoformat() for k in range(dias)]
    pts = [(k, serie[d]) for k, d in enumerate(eixo) if d in serie]
    if len(pts) < 2:
        return (f'<p class="vazio">O gráfico de {html.escape(titulo)} aparece a partir do 2º dia de dados.</p>')
    L, A, ml, mr, mt, mb = 640, 180, 36, 56, 14, 26
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.15
    lo, hi = max(0, lo - pad), hi + pad
    x = lambda k: ml + (L - ml - mr) * k / (dias - 1)  # noqa: E731
    y = lambda v: mt + (A - mt - mb) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    linha = " ".join(f"{x(k):.1f},{y(v):.1f}" for k, v in pts)
    area = f"{x(pts[0][0]):.1f},{A - mb} " + linha + f" {x(pts[-1][0]):.1f},{A - mb}"
    grade = "".join(
        f'<line x1="{ml}" x2="{L - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grade"/>'
        f'<text x="{ml - 6}" y="{y(v) + 4:.1f}" class="eixo" text-anchor="end">{round(v)}</text>'
        for v in (lo + (hi - lo) * f for f in (0, 0.5, 1)))
    marcas = "".join(
        f'<circle cx="{x(k):.1f}" cy="{y(v):.1f}" r="9" class="alvo"><title>{eixo[k][8:]}/{eixo[k][5:7]}: {v}</title></circle>'
        for k, v in pts)
    k_fim, v_fim = pts[-1]
    datas = (f'<text x="{ml}" y="{A - 6}" class="eixo">{eixo[0][8:]}/{eixo[0][5:7]}</text>'
             f'<text x="{L - mr}" y="{A - 6}" class="eixo" text-anchor="end">hoje</text>')
    return (f'<svg viewBox="0 0 {L} {A}" role="img" aria-label="{html.escape(titulo)}">{grade}'
            f'<polygon points="{area}" class="area"/><polyline points="{linha}" class="linha-graf"/>'
            f'<circle cx="{x(k_fim):.1f}" cy="{y(v_fim):.1f}" r="5" class="ponto"/>'
            f'<text x="{x(k_fim) + 9:.1f}" y="{y(v_fim) + 4:.1f}" class="rotulo">{v_fim}</text>{datas}{marcas}</svg>')


def _grafico_barras(valores, rotulos, titulo):
    L, A, ml, mr, mt, mb = 640, 180, 36, 12, 14, 26
    hi = max(valores + [1])
    n = len(valores)
    passo = (L - ml - mr) / n
    larg = passo * 0.62
    barras = []
    for k, (v, r) in enumerate(zip(valores, rotulos)):
        h = (A - mt - mb) * v / hi
        x0 = ml + passo * k + (passo - larg) / 2
        y0 = A - mb - h
        if v:
            barras.append(f'<path d="M{x0:.1f},{A - mb} V{y0 + 4:.1f} Q{x0:.1f},{y0:.1f} {x0 + 4:.1f},{y0:.1f} '
                          f'H{x0 + larg - 4:.1f} Q{x0 + larg:.1f},{y0:.1f} {x0 + larg:.1f},{y0 + 4:.1f} V{A - mb} Z" '
                          f'class="barra"/>')
        barras.append(f'<rect x="{ml + passo * k:.1f}" y="{mt}" width="{passo:.1f}" height="{A - mt - mb}" '
                      f'class="alvo"><title>{r}: {v}</title></rect>')
        if k in (0, n - 1) or k == n // 2:
            barras.append(f'<text x="{ml + passo * k + passo / 2:.1f}" y="{A - 6}" class="eixo" '
                          f'text-anchor="middle">{r}</text>')
    topo = (f'<line x1="{ml}" x2="{L - mr}" y1="{mt}" y2="{mt}" class="grade"/>'
            f'<text x="{ml - 6}" y="{mt + 4}" class="eixo" text-anchor="end">{hi}</text>'
            f'<line x1="{ml}" x2="{L - mr}" y1="{A - mb}" y2="{A - mb}" class="base"/>')
    return f'<svg viewBox="0 0 {L} {A}" role="img" aria-label="{html.escape(titulo)}">{topo}{"".join(barras)}</svg>'


def radar_horas(radar, agora, dias=7):
    """Soma das últimas N jornadas: [entradas, saídas, mensagens] por hora (0 a 23)."""
    horas = [[0, 0, 0] for _ in range(24)]
    datas = {(agora.date() - timedelta(days=k)).isoformat() for k in range(dias)}
    for dia, por_hora in (radar or {}).items():
        if dia not in datas:
            continue
        for h, vals in (por_hora or {}).items():
            for i in range(3):
                horas[int(h)][i] += int(vals[i]) if i < len(vals) else 0
    return horas


def _grafico_radar(horas):
    """Entradas para cima (roxo), saídas para baixo (rosa), uma barra por hora do dia."""
    L, A, ml, mr, mt, mb = 640, 200, 28, 8, 12, 24
    meio = mt + (A - mt - mb) / 2
    hi = max([max(e, s) for e, s, _ in horas] + [1])
    passo = (L - ml - mr) / 24
    larg = passo * 0.6
    partes = [f'<line x1="{ml}" x2="{L - mr}" y1="{meio:.1f}" y2="{meio:.1f}" class="base"/>',
              f'<text x="{ml - 6}" y="{mt + 4}" class="eixo" text-anchor="end">{hi}</text>',
              f'<text x="{ml - 6}" y="{A - mb + 2}" class="eixo" text-anchor="end">{hi}</text>']
    alt = (A - mt - mb) / 2
    for h, (e, s, m) in enumerate(horas):
        x0 = ml + passo * h + (passo - larg) / 2
        if e:
            he = alt * e / hi
            partes.append(f'<rect x="{x0:.1f}" y="{meio - he:.1f}" width="{larg:.1f}" height="{he:.1f}" rx="3" class="barra"/>')
        if s:
            hs = alt * s / hi
            partes.append(f'<rect x="{x0:.1f}" y="{meio + 1:.1f}" width="{larg:.1f}" height="{hs:.1f}" rx="3" class="barra sai"/>')
        partes.append(f'<rect x="{ml + passo * h:.1f}" y="{mt}" width="{passo:.1f}" height="{A - mt - mb}" class="alvo">'
                      f'<title>{h}h: {e} entraram, {s} saíram, {m} mensagens</title></rect>')
        if h in (0, 6, 12, 18, 23):
            partes.append(f'<text x="{ml + passo * h + passo / 2:.1f}" y="{A - 4}" class="eixo" text-anchor="middle">{h}h</text>')
    return (f'<svg viewBox="0 0 {L} {A}" role="img" aria-label="Entradas e saídas do grupo por hora">{"".join(partes)}</svg>'
            '<p class="legenda"><span><i style="background:var(--roxo)"></i>Entraram</span>'
            '<span><i style="background:var(--rosa)"></i>Saíram</span></p>')


def _frase_radar(horas, radar):
    entradas = sum(e for e, _, _ in horas)
    saidas = sum(s for _, s, _ in horas)
    msgs = sum(m for _, _, m in horas)
    desde = min(radar) if radar else None
    if not entradas and not saidas:
        return ("Ninguém entrou nem saiu do grupo nos últimos 7 dias" + (f" (contando desde {desde[8:]}/{desde[5:7]})." if desde else "."))
    melhor = max(range(24), key=lambda h: horas[h][0])
    pior = max(range(24), key=lambda h: horas[h][1])
    partes = [f"Nos últimos 7 dias {plural(entradas, 'pessoa entrou', 'pessoas entraram')} e "
              f"{plural(saidas, 'saiu', 'saíram')}" + (f" (contando desde {desde[8:]}/{desde[5:7]})." if desde else ".")]
    if entradas:
        partes.append(f"Quem mais trouxe gente foi a faixa das {melhor}h.")
    if saidas:
        partes.append(f"As saídas se concentraram às {pior}h.")
    if entradas:
        partes.append(f"Para cada 10 que entraram, {round(10 * saidas / entradas)} saíram.")
    partes.append(f"As pessoas mandaram {plural(msgs, 'mensagem', 'mensagens')} no grupo.")
    return " ".join(partes)


def gerar_html(estado, wa, agora):
    hoje = agora.date().isoformat()
    tg_hist = {d: v for d, v in (estado.get("membros_hist") or {}).items() if isinstance(v, int)}
    wa_hist = {d: v for d, v in (wa.get("membros") or {}).items() if isinstance(v, int)}
    hist = estado.get("hist_dia") or {}
    h = hist.get(hoje, {})
    # total do dia (ML + Shopee); contagem_dia conta só o Mercado Livre (é o ritmo do ML)
    posts_tg = h.get("posts") or (estado.get("contagem_dia") or {}).get(hoje, 0)
    posts_wa = wa.get("enviados", 0) if wa.get("dia") == hoje else 0
    ativos = [c for c, v in (estado.get("cupons") or {}).items() if v.get("status") == "ativo" and not c.startswith("#")]
    if wa.get("pausado_ate") and wa["pausado_ate"] > agora.isoformat():
        wa_status = ("alerta", "Em pausa de segurança")
    elif wa.get("conectado") is False:
        wa_status = ("alerta", "Desconectado")
    elif wa:
        wa_status = ("ok", "Conectado")
    else:
        wa_status = ("mudo", "Ainda sem dados")

    tg_atual = tg_hist[max(tg_hist)] if tg_hist else "–"
    wa_atual = wa_hist[max(wa_hist)] if wa_hist else "–"
    fatos = paginas.fatos([
        ("Membros no Telegram", tg_atual, _fmt_delta(_delta(tg_hist, 1), "desde ontem") + "<br>"
         + _fmt_delta(_delta(tg_hist, 7), "em 7 dias")),
        ("Membros no WhatsApp", wa_atual, _fmt_delta(_delta(wa_hist, 1), "desde ontem") + "<br>"
         + _fmt_delta(_delta(wa_hist, 7), "em 7 dias")),
        ("Ofertas hoje", posts_tg, f'{posts_tg - h.get("shopee", 0)} do Mercado Livre, {h.get("shopee", 0)} da Shopee, '
                                   f'{h.get("com_cupom", 0)} com cupom'),
        ("Cupons ativos", len(ativos), f'{h.get("cupons", 0)} postados hoje'),
    ])
    dias14 = [(agora.date() - timedelta(days=13 - k)).isoformat() for k in range(14)]
    posts14 = [(hist.get(d) or {}).get("posts", 0) for d in dias14]
    if not hist.get(hoje):
        posts14[-1] = posts_tg
    rot14 = [f"{d[8:]}/{d[5:7]}" for d in dias14]

    de_hoje = sorted((p for p in (estado.get("postados") or {}).values()
                      if str(p.get("quando", "")).startswith(hoje) and p.get("titulo")),
                     key=lambda p: p.get("desconto") or 0, reverse=True)[:5]
    linhas = "".join(
        f'<tr><td>{html.escape(p["titulo"][:70])}</td><td class="num">-{round((p.get("desconto") or 0) * 100)}%</td>'
        f'<td class="num">{_brl(p.get("preco") or 0)}</td></tr>' for p in de_hoje
    ) or '<tr><td colspan="3" class="mudo">Nenhuma oferta postada hoje ainda.</td></tr>'
    apagados = (wa.get("apagados") or {}).get(hoje, 0)
    radar = wa.get("radar") or {}
    horas = radar_horas(radar, agora)

    manchete = (f"{plural(posts_tg, 'oferta saiu', 'ofertas saíram')} no Telegram hoje e "
                f"{posts_wa} no grupo do WhatsApp.")
    corpo = f"""<h1 class="manchete">{manchete}</h1>
<p class="quando">Atualizado em {agora:%d/%m às %H:%M}. A página recarrega sozinha a cada 10 minutos.</p>
{fatos}
<section><h2>Quem entra e quem sai do grupo</h2>
<p class="nota">{html.escape(_frase_radar(horas, radar))}</p>
{_grafico_radar(horas)}</section>
<div class="duas">
  <section><h2>Membros no Telegram</h2>{_grafico_linha(tg_hist, DIAS_HIST, "membros no Telegram", agora.date())}</section>
  <section><h2>Membros no WhatsApp</h2>{_grafico_linha(wa_hist, DIAS_HIST, "membros no WhatsApp", agora.date())}</section>
</div>
<section><h2>Ofertas por dia</h2><p class="nota">Últimos 14 dias, Telegram.</p>{_grafico_barras(posts14, rot14, "ofertas por dia, últimos 14 dias")}</section>
<section><h2>WhatsApp hoje</h2><p class="nota"><span class="pill {wa_status[0]}">{wa_status[1]}</span>
  {plural(posts_wa, "post", "posts")} no grupo, {plural(apagados, "link de outra pessoa apagado", "links de outras pessoas apagados")}.</p></section>
<section><h2>Maiores descontos de hoje</h2><table>{linhas}</table></section>"""
    return paginas.pagina("Números do Chocalho", "numeros", corpo)


def talvez_publicar(estado, agora, tg=None, canal=None, arquivo=ARQ, arquivo_wa=ARQ_WA, log=print):
    """Reescreve a página (no máximo a cada 10 min)."""
    atualizar_membros(estado, tg, canal, agora)
    ultima = estado.get("numeros_em")
    if ultima and (agora - datetime.fromisoformat(ultima)).total_seconds() < 600 and Path(arquivo).exists():
        return False
    Path(arquivo).parent.mkdir(parents=True, exist_ok=True)
    Path(arquivo).write_text(gerar_html(estado, _ler_wa(arquivo_wa), agora), encoding="utf-8")
    estado["numeros_em"] = agora.isoformat(timespec="minutes")
    return True
