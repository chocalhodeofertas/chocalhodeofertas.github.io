"""Página escondida da fila (docs/fila-4e7a91c3.html): o que saiu hoje, o que espera e o que ficou de fora.

No Telegram não existe fila: oferta aprovada sai na hora. Quem tem fila é o grupo do WhatsApp (limite de posts
por dia e intervalo entre eles) e o Mercado Livre (produto aprovado que ainda espera o link oficial do lote).
A página junta as três coisas e é reescrita a cada rodada; sem links clicáveis, para ninguém abrir link de afiliado por ela.
"""
import html
import re
from datetime import datetime, timedelta
from pathlib import Path

from . import paginas
from .paginas import plural

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "docs" / "fila-4e7a91c3.html"
ENDERECO = "https://chocalhodeofertas.github.io/fila-4e7a91c3.html"
VALIDADE_H = 3          # igual ao wa/servico.mjs: oferta parada há mais de 3 h não sai
HORA_INICIO, HORA_FIM = 7, 23
PONTOS_AVISO = 9.0
MOTIVOS = {"venceu": "esperou mais de 3 h", "limite": "limite de posts do dia", "pausa": "grupo em pausa de segurança",
           "erro": "o WhatsApp recusou", "subiu": "o preço subiu enquanto esperava", "acabou": "acabou ou o anúncio saiu"}


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


def ordem_de_saida(itens, ultima_loja="ml", ultima_categoria=None):
    """Mesma regra do wa/comum.mjs (ordenarFila), repetida até a fila acabar: mais pontos primeiro,
    aviso (cupom, resumo) na frente de tudo, as lojas alternando e sem repetir a categoria da anterior."""
    resto = sorted(itens, key=lambda i: (-(i.get("pontos") or 0), i.get("arquivo") or ""))
    ordem = []
    while resto:
        prox = resto[0]
        if (prox.get("pontos") or 0) < PONTOS_AVISO:
            base = [i for i in resto if (i.get("loja") or "ml") != ultima_loja] or resto
            prox = next((i for i in base if not ultima_categoria or i.get("categoria") != ultima_categoria), base[0])
        resto.remove(prox)
        ordem.append(prox)
        ultima_loja = prox.get("loja") or "ml"
        ultima_categoria = prox.get("categoria") or ultima_categoria
    return ordem


def cota_ate(maximo, t):
    """Mesma regra do wa/comum.mjs (cotaAteAgora): o limite do dia espalhado das 7h às 23h."""
    passou = min(max(t.hour + t.minute / 60 - HORA_INICIO, 0), HORA_FIM - HORA_INICIO)
    return min(maximo, max(1, -(-maximo * passou // (HORA_FIM - HORA_INICIO))))


def _intervalo_medio(wa):
    if wa.get("intervalo_max"):
        return timedelta(minutes=(float(wa.get("intervalo_min") or 4) + float(wa["intervalo_max"])) / 2)
    return timedelta(minutes=float(wa.get("intervalo_min") or 25))


def prever(itens, wa, agora):
    """Para cada item esperando no grupo: a hora prevista de saída, ou por que não deve sair."""
    hoje = agora.date().isoformat()
    intervalo = _intervalo_medio(wa)
    limite = wa.get("max_dia")
    enviados = wa.get("enviados", 0) if wa.get("dia") == hoje else 0
    pausado = bool(wa.get("pausado_ate") and wa["pausado_ate"] > agora.isoformat())
    proximo = _quando(wa.get("proximo_em"), agora)
    ultimo = _quando(wa.get("ultimo"), agora)
    t = max(agora, proximo) if proximo else (max(agora, ultimo + intervalo) if ultimo else agora)
    saida = []
    for item in ordem_de_saida(itens, wa.get("ultima_loja") or "ml", wa.get("ultima_categoria")):
        criado = _quando(item.get("criado"), agora) or agora
        vence = criado + timedelta(hours=VALIDADE_H)
        if t.hour < HORA_INICIO:
            t = t.replace(hour=HORA_INICIO, minute=0)
        while limite and wa.get("intervalo_max") and enviados >= cota_ate(limite, t) and enviados < limite \
                and t.hour < HORA_FIM:
            t += timedelta(minutes=15)  # espera a cota do dia liberar mais um post
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
    return (f'<li><div class="linha-topo"><span class="hora">{html.escape(hora or "–")}</span>'
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
    conf = estado.get("wa_conferidos") or {}
    conferidos = list(conf.get("itens") or []) if conf.get("dia") == hoje else []
    por_link = {h["k"]: h for h in conferidos + historico if h.get("k")}  # o envio pelo WhatsApp vale por último
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

    foram = sum(1 for h in historico if h.get("r") == "enviado")
    fora = sum(1 for h in historico if h.get("r") != "enviado")
    tiles = paginas.fatos([
        ("Saíram no Telegram hoje", len(posts), "O Telegram não tem fila: aprovou, saiu."),
        ("Saíram no grupo hoje", f"{enviados}" + (f" de {limite}" if limite else ""),
         (f"1 a cada {wa['intervalo_min']:g} a {wa['intervalo_max']:g} min, espalhados pelo dia." if wa.get("intervalo_max")
          else f"1 a cada {wa['intervalo_min']:g} min." if wa.get("intervalo_min") else "")),
        ("Esperando no grupo", len(pendentes), f"{fora} ficaram de fora hoje." if fora else ""),
        ("Esperando link oficial", esperando_link, "Mercado Livre, depende do lote."),
    ])

    # ---- esperando no grupo
    linhas_fila = "".join(
        _linha(f"{n}º", _loja(i.get("loja")), i.get("nome") or "(sem texto)",
               f'na fila há {_ha(i["ha_min"])}' + (", aviso ou cupom: passa na frente" if (i.get("pontos") or 0) >= PONTOS_AVISO else ""),
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
        return ", ".join(x for x in partes if x)

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
               ", ".join(x for x in [f'<b>{_brl(i["preco"])}</b>' if i.get("preco") else "",
                                      f'desconto do anúncio {round((i.get("desconto") or 0) * 100)}%' if i.get("desconto") else "",
                                      "🔁 veio de outro canal (vale 48 h)" if i.get("espelho") else ""] if x),
               ("espera", "No lote enviado") if i.get("no_lote") else ("mudo", "Próximos lotes"))
        for n, i in enumerate(fila_link.get("itens") or [], 1)
    ) or '<li class="vazio">Nenhum produto esperando link.</li>'
    mais = esperando_link - len(fila_link.get("itens") or [])
    rodape_link = f'<p class="nota">E mais {mais} na sequência.</p>' if mais > 0 else ""

    if pendentes and pendentes[0]["previsao"][0] == "espera":
        manchete = (f"{plural(len(pendentes), 'oferta espera', 'ofertas esperam')} o grupo do WhatsApp; "
                    f"a próxima sai por volta das {pendentes[0]['previsao'][1].removeprefix('previsão ')}.")
    elif pendentes:
        manchete = f"{plural(len(pendentes), 'oferta espera', 'ofertas esperam')} o grupo do WhatsApp, mas hoje não devem sair."
    else:
        manchete = f"Nada esperando o grupo agora. {plural(len(posts), 'oferta saiu', 'ofertas saíram')} no Telegram hoje."
    corpo = f"""<h1 class="manchete">{manchete}</h1>
<p class="quando">Atualizado em {agora:%d/%m às %H:%M}. Muda a cada rodada do bot (uns 20 min); para ver na hora, mande <b>fila</b> ao bot no Telegram.</p>
{aviso_html}{tiles}
<section><h2>Esperando para sair no grupo do WhatsApp</h2>
<p class="nota">Na ordem em que devem sair. Sai primeiro a oferta mais forte, alternando as lojas. Oferta que espera mais de {VALIDADE_H} h é descartada.</p>
<ul class="lista">{linhas_fila}</ul></section>
<section><h2>O que saiu hoje no canal do Telegram</h2>
<p class="nota">A etiqueta à direita diz o que aconteceu com cada oferta no grupo do WhatsApp. {foram} foram ao grupo hoje.</p>
<ul class="lista">{linhas_posts}</ul></section>
{bloco_outros}
<section><h2>Esperando link oficial do Mercado Livre</h2>
<p class="nota">Já aprovadas pelo bot, mas só saem depois que você gerar o link no Linkbuilder. {html.escape(situacao)}</p>
<ul class="lista">{linhas_link}</ul>{rodape_link}</section>"""
    return paginas.pagina("Fila do Chocalho", "fila", corpo)


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
