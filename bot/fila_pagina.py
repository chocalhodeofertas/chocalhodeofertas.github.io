"""Página escondida da fila (docs/fila-4e7a91c3.html): o que saiu hoje, o que espera e o que ficou de fora.

No Telegram não existe fila: oferta aprovada sai na hora. Quem tem fila é o grupo do WhatsApp (limite de posts
por dia e intervalo entre eles) e o Mercado Livre (produto aprovado que ainda espera o link oficial do lote).
A página junta as três coisas e é reescrita a cada rodada; sem links clicáveis, para ninguém abrir link de afiliado por ela.
"""
import html
import re
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "docs" / "fila-4e7a91c3.html"
ENDERECO = "https://chocalhodeofertas.github.io/fila-4e7a91c3.html"
VALIDADE_H = 3          # igual ao wa/servico.mjs: oferta parada há mais de 3 h não sai
HORA_INICIO, HORA_FIM = 7, 23
PONTOS_AVISO = 9.0
MOTIVOS = {"venceu": "esperou mais de 3 h", "limite": "limite de posts do dia", "pausa": "grupo em pausa de segurança",
           "erro": "o WhatsApp recusou"}


def _brl(v):
    return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _quando(iso, agora):
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(agora.tzinfo) if d.tzinfo else d.replace(tzinfo=agora.tzinfo)


def _ha(minutos):
    return f"{minutos} min" if minutos < 60 else f"{minutos // 60} h" + (f" {minutos % 60:02d}" if minutos % 60 else "")


def _link(texto):
    m = re.search(r"https?://\S+", texto or "")
    return m.group(0) if m else None


def ordem_de_saida(itens, ultima_loja="ml"):
    """Mesma regra do wa/comum.mjs (ordenarFila), repetida até a fila acabar: mais pontos primeiro,
    aviso (cupom, resumo) na frente de tudo, e as lojas alternando."""
    resto = sorted(itens, key=lambda i: (-(i.get("pontos") or 0), i.get("arquivo") or ""))
    ordem = []
    while resto:
        prox = resto[0]
        if (prox.get("pontos") or 0) < PONTOS_AVISO:
            prox = next((i for i in resto if (i.get("loja") or "ml") != ultima_loja), prox)
        resto.remove(prox)
        ordem.append(prox)
        ultima_loja = prox.get("loja") or "ml"
    return ordem


def prever(itens, wa, agora):
    """Para cada item esperando no grupo: a hora prevista de saída, ou por que não deve sair."""
    hoje = agora.date().isoformat()
    intervalo = timedelta(minutes=float(wa.get("intervalo_min") or 25))
    limite = wa.get("max_dia")
    enviados = wa.get("enviados", 0) if wa.get("dia") == hoje else 0
    pausado = bool(wa.get("pausado_ate") and wa["pausado_ate"] > agora.isoformat())
    ultimo = _quando(wa.get("ultimo"), agora)
    t = max(agora, ultimo + intervalo) if ultimo else agora
    saida = []
    for item in ordem_de_saida(itens, wa.get("ultima_loja") or "ml"):
        criado = _quando(item.get("criado"), agora) or agora
        vence = criado + timedelta(hours=VALIDADE_H)
        if t.hour < HORA_INICIO:
            t = t.replace(hour=HORA_INICIO, minute=0)
        if pausado:
            previsao = ("fora", "não sai: grupo em pausa de segurança")
        elif limite and enviados >= limite:
            previsao = ("fora", "não deve sair: limite de hoje já foi atingido")
        elif t > vence or t.hour >= HORA_FIM or t.date() != agora.date():
            previsao = ("fora", f"não deve sair: vence às {vence:%H:%M}, antes da vez dela")
        else:
            previsao = ("espera", f"previsão {t:%H:%M}")
            enviados += 1
            t = t + intervalo
        saida.append({**item, "previsao": previsao, "ha_min": max(0, int((agora - criado).total_seconds() // 60))})
    return saida


def _status_no_grupo(post, por_link, na_fila, agora):
    chaves = [post.get("link_wa"), post.get("link")]
    for k in chaves:
        if k and k in na_fila:
            return "espera", "Na fila do grupo"
    for k in chaves:
        h = por_link.get(k) if k else None
        if h:
            if h.get("r") == "enviado":
                q = _quando(h.get("h"), agora)
                return "ok", "No grupo" + (f" às {q:%H:%M}" if q else "")
            return "fora", "Não foi ao grupo: " + MOTIVOS.get(h.get("r"), "ficou de fora")
    return "mudo", "Sem registro no grupo"


def _loja(l):
    return "Shopee" if l == "shopee" else "Mercado Livre"


def _linha(hora, loja, titulo, extra, pill):
    return (f'<li><div class="topo"><span class="hora">{html.escape(hora or "–")}</span>'
            f'<span class="loja">{html.escape(loja)}</span>'
            f'<span class="pill {pill[0]}">{html.escape(pill[1])}</span></div>'
            f'<div class="nome">{html.escape(titulo)}</div>'
            + (f'<div class="extra">{extra}</div>' if extra else "") + "</li>")


def gerar_html(estado, wa, itens_fila, agora):
    hoje = agora.date().isoformat()
    reg = estado.get("posts_dia") or {}
    posts = list(reg.get("itens") or []) if reg.get("dia") == hoje else []
    hist = wa.get("historico") or {}
    historico = list(hist.get("itens") or []) if hist.get("dia") == hoje else []
    por_link = {h["k"]: h for h in historico if h.get("k")}  # o último registro de cada link vale
    pendentes = prever(itens_fila, wa, agora)
    na_fila = {i["link"] for i in itens_fila if i.get("link")}
    enviados = wa.get("enviados", 0) if wa.get("dia") == hoje else 0
    limite = wa.get("max_dia")
    fila_link = estado.get("fila_link") or {}
    esperando_link = fila_link.get("total", estado.get("aguardando_link") or 0)

    # ---- avisos de estado do grupo
    avisos = []
    if wa.get("pausado_ate") and wa["pausado_ate"] > agora.isoformat():
        avisos.append("O grupo do WhatsApp está em pausa de segurança: nada sai por lá até a pausa acabar.")
    elif wa.get("conectado") is False:
        avisos.append("O WhatsApp do Chocalho está desconectado: as ofertas continuam saindo só no Telegram.")
    elif limite and enviados >= limite:
        avisos.append(f"O grupo do WhatsApp já recebeu os {limite} posts de hoje. O que estiver na fila não sai mais hoje.")
    aviso_html = "".join(f'<p class="aviso">{html.escape(a)}</p>' for a in avisos)

    def tile(rotulo, valor, extra=""):
        return f'<div class="tile"><span class="rot">{rotulo}</span><b>{valor}</b><span class="extra">{extra}</span></div>'

    foram = sum(1 for h in historico if h.get("r") == "enviado")
    fora = sum(1 for h in historico if h.get("r") != "enviado")
    tiles = "".join([
        tile("Saíram no Telegram hoje", len(posts), "o Telegram não tem fila: aprovou, saiu"),
        tile("Saíram no grupo hoje", f"{enviados}" + (f" de {limite}" if limite else ""),
             f"1 a cada {wa['intervalo_min']:g} min" if wa.get("intervalo_min") else "WhatsApp"),
        tile("Esperando no grupo", len(pendentes), f"{fora} ficaram de fora hoje" if fora else "fila do WhatsApp"),
        tile("Esperando link oficial", esperando_link, "Mercado Livre: depende do lote"),
    ])

    # ---- esperando no grupo
    linhas_fila = "".join(
        _linha(f"{n}º", _loja(i.get("loja")), i.get("nome") or "(sem texto)",
               f'na fila há {_ha(i["ha_min"])}' + (" · aviso/cupom: passa na frente" if (i.get("pontos") or 0) >= PONTOS_AVISO else ""),
               i["previsao"])
        for n, i in enumerate(pendentes, 1)
    ) or '<li class="vazio">Nada esperando agora.</li>'

    # ---- o que saiu hoje no canal (mais recente primeiro)
    def extra_post(p):
        partes = [f'<b>{_brl(p["preco"])}</b>' if p.get("preco") else ""]
        if p.get("fonte"):
            partes.append("🔁 copiada de @" + html.escape(str(p["fonte"])))
        if p.get("selo"):
            partes.append(f'📉 menor preço em {p["selo"]} dias')
        if p.get("cupom"):
            partes.append("🎟️ com cupom")
        return " · ".join(x for x in partes if x)

    linhas_posts = "".join(
        _linha(p.get("hora"), _loja(p.get("loja")), p.get("titulo") or "", extra_post(p),
               _status_no_grupo(p, por_link, na_fila, agora))
        for p in reversed(posts)
    ) or '<li class="vazio">Nenhuma oferta saiu hoje ainda.</li>'

    # ---- avisos, cupons e resumos que passaram pelo grupo (não são ofertas do canal)
    links_posts = {k for p in posts for k in (p.get("link"), p.get("link_wa")) if k}
    outros = [h for h in historico if not h.get("k") or h["k"] not in links_posts]

    def linha_outro(h):
        q = _quando(h.get("h"), agora)
        pill = ("ok", "No grupo") if h.get("r") == "enviado" else ("fora", "Não foi: " + MOTIVOS.get(h.get("r"), "ficou de fora"))
        return _linha(f"{q:%H:%M}" if q else "", _loja(h.get("l")), h.get("n") or "", "", pill)

    bloco_outros = ""
    if outros:
        bloco_outros = ('<section class="cartao"><h2>Cupons, avisos e resumos no grupo hoje</h2><ul class="lista">'
                        + "".join(linha_outro(h) for h in reversed(outros)) + "</ul></section>")

    # ---- esperando link oficial (lote do Linkbuilder)
    lote = estado.get("lote") or {}
    if lote.get("dia") == hoje and lote.get("ids"):
        situacao = f'Lote de hoje enviado para você com {len(lote["ids"])} links: esperando a sua resposta.'
    else:
        feitos = (estado.get("lotes_dia") or {}).get(hoje, 0)
        situacao = (f"Lotes respondidos hoje: {feitos}." if feitos else "Nenhum lote pendente agora.")
    linhas_link = "".join(
        _linha(f"{n}º", "Mercado Livre", i.get("titulo") or "",
               " · ".join(x for x in [f'<b>{_brl(i["preco"])}</b>' if i.get("preco") else "",
                                      f'desconto do anúncio {round((i.get("desconto") or 0) * 100)}%' if i.get("desconto") else "",
                                      "🔁 veio de outro canal (vale 48 h)" if i.get("espelho") else ""] if x),
               ("espera", "No lote enviado") if i.get("no_lote") else ("mudo", "Próximos lotes"))
        for n, i in enumerate(fila_link.get("itens") or [], 1)
    ) or '<li class="vazio">Nenhum produto esperando link.</li>'
    mais = esperando_link - len(fila_link.get("itens") or [])
    rodape_link = f'<p class="nota">E mais {mais} na sequência.</p>' if mais > 0 else ""

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta http-equiv="refresh" content="600">
<title>Fila do Chocalho</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fredoka:wght@600&family=Poppins:wght@400;500;600&display=swap">
<style>
:root {{ --bg:#f8f3fb; --surface:#fff; --ink:#2b1030; --soft:#6e5a74; --line:#e6d8ef; --grade:#efe6f5;
  --uva:#3a0a40; --roxo:#8e2bb0; --roxo-bg:#f1e3f8; --ok:#1f8a5b; --ok-bg:#e2f4ea;
  --alerta:#b4401c; --alerta-bg:#fde7df; color-scheme:light; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1a0a1e; --surface:#26112b; --ink:#f6ecfa; --soft:#c2afc9;
  --line:#432449; --grade:#34203a; --uva:#f1e1fb; --roxo:#cf8ce9; --roxo-bg:#3a1f44;
  --ok:#6fd3a3; --ok-bg:#173327; --alerta:#ff9a7a; --alerta-bg:#3d1d14; color-scheme:dark; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 Poppins, system-ui, sans-serif; }}
.wrap {{ max-width:860px; margin:0 auto; padding:24px max(16px, env(safe-area-inset-right)) 48px max(16px, env(safe-area-inset-left)); }}
h1 {{ font:600 28px/1.1 Fredoka, Poppins, sans-serif; color:var(--uva); margin:0; }}
h2 {{ font:600 18px/1.2 Fredoka, Poppins, sans-serif; color:var(--uva); margin:0 0 4px; }}
.sub {{ color:var(--soft); margin:4px 0 20px; font-size:13px; }}
.nota {{ color:var(--soft); font-size:13px; margin:0 0 10px; }}
.aviso {{ background:var(--alerta-bg); color:var(--alerta); border-radius:12px; padding:10px 14px; font-weight:500; margin:0 0 16px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-bottom:20px; }}
.tile {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:14px 16px; display:grid; gap:2px; }}
.tile .rot {{ font-size:12px; color:var(--soft); font-weight:500; }}
.tile b {{ font:600 28px/1.1 Fredoka, Poppins, sans-serif; font-variant-numeric:tabular-nums; }}
.tile .extra {{ font-size:12px; color:var(--soft); }}
.cartao {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:16px; margin-bottom:16px; min-width:0; }}
.lista {{ list-style:none; margin:0; padding:0; }}
.lista li {{ border-top:1px solid var(--line); padding:10px 0; }}
.lista li:first-child {{ border-top:0; }}
.lista li.vazio {{ color:var(--soft); font-size:14px; }}
.topo {{ display:flex; flex-wrap:wrap; align-items:center; gap:6px 10px; font-size:12px; color:var(--soft); }}
.hora {{ font-weight:600; color:var(--ink); font-variant-numeric:tabular-nums; min-width:38px; }}
.nome {{ font-size:14px; overflow-wrap:anywhere; margin-top:2px; }}
.extra {{ font-size:13px; color:var(--soft); }}
.extra b {{ color:var(--ink); font-weight:600; }}
.pill {{ display:inline-block; font-size:12px; font-weight:600; padding:2px 10px; border-radius:999px; margin-left:auto; text-align:right; }}
.pill.ok {{ background:var(--ok-bg); color:var(--ok); }} .pill.fora {{ background:var(--alerta-bg); color:var(--alerta); }}
.pill.espera {{ background:var(--roxo-bg); color:var(--roxo); }} .pill.mudo {{ background:var(--grade); color:var(--soft); }}
</style></head>
<body><div class="wrap">
<h1>Fila do Chocalho</h1>
<p class="sub">Atualizado em {agora:%d/%m às %H:%M} · muda a cada rodada do bot (uns 20 min) · para ver na hora, mande <b>fila</b> ao bot no Telegram</p>
{aviso_html}<div class="tiles">{tiles}</div>
<section class="cartao"><h2>Esperando para sair no grupo do WhatsApp</h2>
<p class="nota">Na ordem em que devem sair. Sai primeiro a oferta mais forte, alternando as lojas. Oferta que espera mais de {VALIDADE_H} h é descartada.</p>
<ul class="lista">{linhas_fila}</ul></section>
<section class="cartao"><h2>O que saiu hoje no canal do Telegram</h2>
<p class="nota">A etiqueta à direita diz o que aconteceu com cada oferta no grupo do WhatsApp. {foram} foram ao grupo hoje.</p>
<ul class="lista">{linhas_posts}</ul></section>
{bloco_outros}
<section class="cartao"><h2>Esperando link oficial do Mercado Livre</h2>
<p class="nota">Já aprovadas pelo bot, mas só saem depois que você gerar o link no Linkbuilder. {html.escape(situacao)}</p>
<ul class="lista">{linhas_link}</ul>{rodape_link}</section>
</div></body></html>
"""


def itens_da_fila():
    """Arquivos da fila do WhatsApp (pasta WA_FILA) em formato enxuto para a página."""
    from .comandos import _itens_fila, _nome_do_item

    return [{"arquivo": arq.name, "nome": _nome_do_item(item)[:80], "loja": item.get("loja") or "ml",
             "pontos": item.get("pontos") or 0, "criado": item.get("criado"), "link": _link(item.get("texto"))}
            for arq, item in _itens_fila()]


def publicar(estado, agora, arquivo=ARQ, arquivo_wa=None, itens=None, log=print):
    """Reescreve a página a cada rodada."""
    from . import numeros

    wa = numeros._ler_wa(arquivo_wa or numeros.ARQ_WA)
    try:
        Path(arquivo).parent.mkdir(parents=True, exist_ok=True)
        Path(arquivo).write_text(gerar_html(estado, wa, itens_da_fila() if itens is None else itens, agora),
                                 encoding="utf-8")
    except Exception as e:  # noqa: BLE001 - a página nunca derruba a rodada
        log(f"Aviso: não consegui atualizar a página da fila: {type(e).__name__}: {e}")
        return False
    return True
