"""Página de números do Chocalho (subpágina do site, sem link em lugar nenhum
e marcada para não aparecer em buscadores). O bot reescreve a cada rodada.

Fontes: data/estado.json (Telegram, posts, cupons) e data/wa_estado.json
(escrito pelo wa/servico.mjs: membros do grupo, posts no grupo, links apagados).
"""
import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path

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
            f'<polygon points="{area}" class="area"/><polyline points="{linha}" class="linha"/>'
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


def gerar_html(estado, wa, agora):
    hoje = agora.date().isoformat()
    tg_hist = {d: v for d, v in (estado.get("membros_hist") or {}).items() if isinstance(v, int)}
    wa_hist = {d: v for d, v in (wa.get("membros") or {}).items() if isinstance(v, int)}
    hist = estado.get("hist_dia") or {}
    h = hist.get(hoje, {})
    posts_tg = (estado.get("contagem_dia") or {}).get(hoje, h.get("posts", 0))
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

    def tile(rotulo, valor, extra=""):
        return f'<div class="tile"><span class="rot">{rotulo}</span><b>{valor}</b><span class="extra">{extra}</span></div>'

    tg_atual = tg_hist[max(tg_hist)] if tg_hist else "–"
    wa_atual = wa_hist[max(wa_hist)] if wa_hist else "–"
    tiles = "".join([
        tile("Membros no Telegram", tg_atual, _fmt_delta(_delta(tg_hist, 1), "desde ontem") + " · "
             + _fmt_delta(_delta(tg_hist, 7), "em 7 dias")),
        tile("Membros no WhatsApp", wa_atual, _fmt_delta(_delta(wa_hist, 1), "desde ontem") + " · "
             + _fmt_delta(_delta(wa_hist, 7), "em 7 dias")),
        tile("Ofertas hoje", posts_tg, f'{h.get("shopee", 0)} da Shopee · {posts_wa} no WhatsApp · {h.get("com_cupom", 0)} com cupom'),
        tile("Cupons", len(ativos), f'ativos agora · {h.get("cupons", 0)} postados hoje'),
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

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta http-equiv="refresh" content="600">
<title>Números do Chocalho</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fredoka:wght@600&family=Poppins:wght@400;500;600&display=swap">
<style>
:root {{ --bg:#f8f3fb; --surface:#fff; --ink:#2b1030; --soft:#6e5a74; --line:#e6d8ef; --grade:#efe6f5;
  --uva:#3a0a40; --roxo:#8e2bb0; --roxo-area:rgba(142,43,176,.10); --ok:#1f8a5b; --ok-bg:#e2f4ea;
  --alerta:#b4401c; --alerta-bg:#fde7df; color-scheme:light; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1a0a1e; --surface:#26112b; --ink:#f6ecfa; --soft:#c2afc9;
  --line:#432449; --grade:#34203a; --uva:#f1e1fb; --roxo:#cf8ce9; --roxo-area:rgba(207,140,233,.14);
  --ok:#6fd3a3; --ok-bg:#173327; --alerta:#ff9a7a; --alerta-bg:#3d1d14; color-scheme:dark; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 Poppins, system-ui, sans-serif; }}
.wrap {{ max-width:1000px; margin:0 auto; padding:24px max(16px, env(safe-area-inset-right)) 48px max(16px, env(safe-area-inset-left)); }}
h1 {{ font:600 28px/1.1 Fredoka, Poppins, sans-serif; color:var(--uva); margin:0; }}
h2 {{ font:600 18px/1.2 Fredoka, Poppins, sans-serif; color:var(--uva); margin:0 0 10px; }}
.sub {{ color:var(--soft); margin:4px 0 20px; font-size:13px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-bottom:24px; }}
.tile {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:14px 16px; display:grid; gap:2px; }}
.tile .rot {{ font-size:12px; color:var(--soft); font-weight:500; }}
.tile b {{ font:600 30px/1.1 Fredoka, Poppins, sans-serif; color:var(--ink); font-variant-numeric:tabular-nums; }}
.tile .extra {{ font-size:12px; color:var(--soft); }}
.sobe {{ color:var(--ok); }} .desce {{ color:var(--alerta); }} .mudo {{ color:var(--soft); }}
.cartao {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:16px; margin-bottom:16px; min-width:0; }}
.grid2 {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:0 16px; }}
svg {{ width:100%; height:auto; display:block; }}
.grade {{ stroke:var(--grade); stroke-width:1; }} .base {{ stroke:var(--line); stroke-width:1; }}
.eixo {{ fill:var(--soft); font-size:11px; font-family:Poppins, sans-serif; }}
.rotulo {{ fill:var(--ink); font-size:12px; font-weight:600; font-family:Poppins, sans-serif; }}
.linha {{ fill:none; stroke:var(--roxo); stroke-width:2; stroke-linejoin:round; }}
.area {{ fill:var(--roxo-area); stroke:none; }} .ponto {{ fill:var(--roxo); stroke:var(--surface); stroke-width:2; }}
.barra {{ fill:var(--roxo); }} .alvo {{ fill:transparent; }}
.vazio {{ color:var(--soft); font-size:13px; margin:8px 0; }}
.pill {{ display:inline-block; font-size:12px; font-weight:600; padding:3px 10px; border-radius:999px; }}
.pill.ok {{ background:var(--ok-bg); color:var(--ok); }} .pill.alerta {{ background:var(--alerta-bg); color:var(--alerta); }}
.pill.mudo {{ background:var(--grade); color:var(--soft); }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
td {{ padding:8px 4px; border-top:1px solid var(--line); vertical-align:top; overflow-wrap:anywhere; }}
td.num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
.wa {{ display:flex; flex-wrap:wrap; gap:8px 18px; align-items:center; font-size:14px; }}
</style></head>
<body><div class="wrap">
<h1>Números do Chocalho</h1>
<p class="sub">Atualizado em {agora:%d/%m às %H:%M} · a página recarrega sozinha a cada 10 minutos</p>
<div class="tiles">{tiles}</div>
<div class="grid2">
  <section class="cartao"><h2>Membros no Telegram</h2>{_grafico_linha(tg_hist, DIAS_HIST, "membros no Telegram", agora.date())}</section>
  <section class="cartao"><h2>Membros no WhatsApp</h2>{_grafico_linha(wa_hist, DIAS_HIST, "membros no WhatsApp", agora.date())}</section>
</div>
<section class="cartao"><h2>Ofertas postadas por dia</h2>{_grafico_barras(posts14, rot14, "ofertas por dia, últimos 14 dias")}</section>
<div class="grid2">
  <section class="cartao"><h2>WhatsApp hoje</h2><div class="wa"><span class="pill {wa_status[0]}">{wa_status[1]}</span>
    <span>{posts_wa} posts no grupo</span><span>{apagados} links de outras pessoas apagados</span></div></section>
  <section class="cartao"><h2>Maiores descontos de hoje</h2><table>{linhas}</table></section>
</div>
</div></body></html>
"""


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
