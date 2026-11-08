"""Pacote do dia para o Instagram (e depois TikTok): chega no seu privado do Telegram.

Todo dia, a partir de PACOTE_HORA (padrão 10h), o bot monta com as ofertas atuais:
- 1 carrossel temático (capa com foto + produtos + chamada para o grupo) com legenda
- 1 Reel com os mesmos produtos (sem música: escolha no app ao postar)
- posts únicos de produto (com "Link na bio") com legenda
- stories (um por produto) com o link para colar no adesivo

Você também pode pedir na hora mandando "pacote" para o bot.
"""
import random
from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace

from . import arte
from .mensagens import _abertura, _titulo_curto, brl
from .telegram import TelegramErro

FORA = {"jogo"}  # itens adultos (taco de sinuca etc.) caem aqui; não entram no Instagram
RODAPE_LEGENDA = "⏳ Promoção temporária.\nContém links de afiliado. #publi"


@dataclass
class Tema:
    nome: str
    categorias: set | None  # None = qualquer uma
    titulos: list
    fotos: list  # pastas de assets/capas, em ordem de preferência
    gancho: list
    preco_max: float | None = None
    destaque: str | None = None


TEMAS = [
    Tema("enxoval", {"quarto", "passeio", "alimentacao", "gestante", "higiene", "fralda", "roupa", "outros"},
         ["Achei promoções pro enxoval", "Coisas de bebê que baixaram de preço hoje",
          "O que eu compraria hoje se estivesse montando o enxoval"],
         ["quarto", "enxoval", "gestante", "familia"],
         ["Montando o enxoval sem estourar o orçamento?", "Pra quem está preparando a chegada do bebê:",
          "Enxoval não precisa custar uma fortuna."]),
    Tema("brinquedos", {"brinquedo"},
         ["Brinquedos que baixaram de preço hoje", "Ideias de presente em promoção",
          "Presentes que estão mais baratos hoje"],
         ["brinquedos", "crianca"],
         ["Aniversário, Natal ou só aquele mimo?", "Pra quem procura presente sem gastar muito:",
          "Diversão pros pequenos com preço bom."]),
    Tema("ate50", None,
         ["Achados até R$ 50 pra família", "Coisas úteis até R$ 50 em promoção hoje"],
         ["familia", "crianca", "enxoval"],
         ["Economizar também é cuidar.", "Pequenos preços, grandes ajudas no dia a dia:"],
         preco_max=50),
    Tema("passeio", {"passeio"},
         ["Pra passear com os pequenos: promoções de hoje", "Itens de passeio que baixaram de preço"],
         ["passeio"],
         ["Sair de casa com criança fica mais fácil com as coisas certas."]),
]


def _itens(estado):
    return [i for i in (estado.get("vitrine") or {}).get("itens", []) if i.get("categoria") not in FORA]


def _oferta(i):
    return SimpleNamespace(titulo=i["titulo"], preco=i["preco"], preco_de=i.get("de"),
                           desconto=i.get("desconto") or 0, imagem=i.get("imagem"),
                           categoria=i.get("categoria", ""), link=i.get("link"), id=i.get("id"))


def _candidatos(tema, itens, usados):
    r = [i for i in itens if i["id"] not in usados
         and (tema.categorias is None or i["categoria"] in tema.categorias)
         and (tema.preco_max is None or i["preco"] <= tema.preco_max)]
    return sorted(r, key=lambda i: -(i.get("desconto") or 0))


def _usados(estado, agora):
    limite = (agora - timedelta(days=3)).date().isoformat()
    return {k for k, v in (estado.get("pacote_usados") or {}).items() if v >= limite}


def escolher_varios(estado, agora, n_carrosseis=1, n_posts=3, n=4):
    """Escolhe temas diferentes (em rodízio) para os carrosséis e os produtos dos posts únicos,
    sem repetir produto entre eles."""
    itens = _itens(estado)
    usados = set(_usados(estado, agora))
    dia = agora.toordinal()
    escolhidos = []
    for k in range(len(TEMAS)):
        if len(escolhidos) == n_carrosseis:
            break
        tema = TEMAS[(dia * n_carrosseis + k) % len(TEMAS)]
        cand = _candidatos(tema, itens, usados)
        if len(cand) >= 3:
            carr = cand[:n]
            usados |= {i["id"] for i in carr}
            escolhidos.append((tema, carr))
    resto = [i for i in sorted(itens, key=lambda i: -(i.get("desconto") or 0)) if i["id"] not in usados][:n_posts]
    return escolhidos, resto


def escolher(estado, agora, rng=random, n=4):
    """Compatível com o uso antigo: 1 tema + 3 posts."""
    esc, resto = escolher_varios(estado, agora, 1, 3, n)
    if not esc:
        return None, [], []
    return esc[0][0], esc[0][1], resto


# Lançamento do perfil: 9 primeiros posts em 3 dias, 3 por dia.
# Cada item: (tipo, horário sugerido). Tipos: "fixado:<nome>", "carrossel", "post".
LANCAMENTO_INICIO = date(2026, 11, 8)
LANCAMENTO = [
    [("fixado:como_funciona", "12h"), ("carrossel", "18h"), ("post", "20h30")],
    [("carrossel", "12h"), ("post", "18h"), ("carrossel", "20h30")],
    [("carrossel", "12h"), ("post", "18h"), ("fixado:o_que_e", "20h30")],
]
LEGENDAS_FIXADOS = {
    "como_funciona": "\n".join([
        "Como funciona o Chocalho de Ofertas 🧸",
        "",
        "1. A gente garimpa promoções de produtos para bebês e crianças todos os dias.",
        "2. Você recebe no nosso grupo gratuito, com foto, preço e link.",
        "3. Compra direto na página oficial da loja, pelo mesmo preço.",
        "",
        "Usamos links de afiliado: a loja nos paga uma pequena comissão, sem custo extra para você. "
        "É assim que o canal se mantém gratuito 💜",
        "",
        "🔗 Link do grupo na bio.",
        "#publi"]),
    "o_que_e": "\n".join([
        "Prazer, Chocalho de Ofertas! 🧸",
        "",
        "Um canal de ofertas pra famílias que amam economizar: do enxoval aos brinquedos, "
        "a gente encontra as promoções e você escolhe o que faz sentido pra sua casa.",
        "",
        "✨ Promoções do dia com desconto de verdade",
        "🎟️ Cupons das lojas assim que saem",
        "⏰ Aviso quando uma promoção acaba",
        "",
        "🔗 Entre no grupo gratuito pelo link da bio (WhatsApp ou Telegram).",
        "#publi"]),
}


def plano_do_dia(agora):
    """Roteiro de posts do feed para hoje. Fora do lançamento: rotina normal."""
    k = (agora.date() - LANCAMENTO_INICIO).days
    if 0 <= k < len(LANCAMENTO):
        return k + 1, LANCAMENTO[k]
    return None, [("carrossel", "12h"), ("post", "18h"), ("post", "20h30")]


def _curto(titulo, limite=55):
    titulo = " ".join((titulo or "").split())
    if len(titulo) <= limite:
        return titulo
    return titulo[:limite].rsplit(" ", 1)[0].rstrip(" -,") + "…"


def legenda_carrossel(tema, ofertas, rng=random):
    linhas = [rng.choice(tema.gancho), "", f"Separei {len(ofertas)} achados que estão com desconto hoje:"]
    for k, o in enumerate(ofertas, 1):
        de = f"de {brl(o.preco_de)} " if o.preco_de else ""
        linhas.append(f"{k}. {_curto(o.titulo)} — {de}por {brl(o.preco)}")
    linhas += ["", "💬 Comenta GRUPO que eu te mando o link do nosso grupo gratuito de ofertas.", "", RODAPE_LEGENDA]
    return "\n".join(linhas)


def legenda_reel(tema, rng=random):
    return "\n".join([rng.choice(tema.gancho), "",
                      "💬 Comenta GRUPO que eu te mando o link do nosso grupo gratuito de ofertas.", "",
                      RODAPE_LEGENDA])


def legenda_post(o, rng=random):
    de = f"De {brl(o.preco_de)} por " if o.preco_de else "Por "
    return "\n".join([_abertura(o, rng), "", _titulo_curto(o.titulo), f"{de}{brl(o.preco)}", "",
                      "🔗 Link do grupo na bio — lá a gente posta as ofertas o dia todo.", "", RODAPE_LEGENDA])


def _registrar_usados(estado, agora, itens):
    hoje = agora.date().isoformat()
    usados = {k: v for k, v in (estado.get("pacote_usados") or {}).items()
              if v >= (agora - timedelta(days=7)).date().isoformat()}
    for i in itens:
        usados[i["id"]] = hoje
    estado["pacote_usados"] = usados


def montar_e_enviar(tg, chat, estado, agora, rng=random, log=print, session=None):
    dia_lanc, plano = plano_do_dia(agora)
    n_carr = sum(1 for t, _ in plano if t == "carrossel")
    n_posts = sum(1 for t, _ in plano if t == "post")
    escolhidos, resto = escolher_varios(estado, agora, n_carr, max(n_posts, 3 if not dia_lanc else n_posts))
    if n_carr and not escolhidos:
        tg.enviar_texto(chat, "📦 Ainda não tenho ofertas suficientes para o pacote de hoje. Tento de novo mais tarde.")
        return False
    if any(arte.foto_de_capa(t.fotos, rng) is None for t, _ in escolhidos):
        tg.enviar_texto(chat, "📦 O pacote está pausado: faltam fotos de capa.", html=True)
        return False

    # Roteiro do dia
    linhas = [f"🗓️ <b>Lançamento do perfil — dia {dia_lanc} de {len(LANCAMENTO)}</b>" if dia_lanc
              else "📦 <b>Pacote do dia</b>", "", "<b>Feed — poste nesta ordem:</b>"]
    fila_c, fila_p = list(escolhidos), list(resto)
    roteiro = []
    for k, (tipo, hora) in enumerate(plano, 1):
        if tipo.startswith("fixado:"):
            nome = tipo.split(":", 1)[1]
            roteiro.append((k, hora, "fixado", nome))
            linhas.append(f"{k}. {hora} — post fixado <b>{arte.INSTITUCIONAIS[nome]['capa'][0]}</b> "
                          "(depois de postar: ··· → Fixar no perfil)")
        elif tipo == "carrossel" and fila_c:
            tema, carr = fila_c.pop(0)
            roteiro.append((k, hora, "carrossel", (tema, carr)))
            linhas.append(f"{k}. {hora} — carrossel <b>{tema.nome}</b>")
        elif tipo == "post" and fila_p:
            i = fila_p.pop(0)
            roteiro.append((k, hora, "post", i))
            linhas.append(f"{k}. {hora} — post do produto <b>{_curto(i['titulo'], 40)}</b>")
    linhas += ["", "📱 Stories: 4 a 6 ao longo do dia (vêm no fim)."]
    if not dia_lanc and agora.weekday() in (0, 2, 4, 6):
        linhas.append("🎬 Hoje tem Reel (vem logo depois do carrossel).")
    linhas += ["", "Os preços valem para agora. Para os posts da noite, confira o preço antes de postar."]
    tg.enviar_texto(chat, "\n".join(linhas), html=True)

    estilo_base = agora.toordinal() % 2
    stories, usados = [], []
    for n_c, (k, hora, tipo, dado) in enumerate(roteiro):
        if tipo == "fixado":
            slides = arte.institucional(dado, rng)
            tg.enviar_album(chat, [arte.png(s) for s in slides], f"📌 {k}. {hora} — post fixado (na ordem)")
            tg.enviar_texto(chat, LEGENDAS_FIXADOS[dado])
        elif tipo == "carrossel":
            tema, carr = dado
            ofs = [_oferta(i) for i in carr]
            fotos = [arte.baixar_foto(o.imagem, session) for o in ofs]
            titulo = rng.choice(tema.titulos)
            estilo = "grande" if (estilo_base + n_c) % 2 == 0 else "faixas"
            capa_foto = arte.foto_de_capa(tema.fotos, rng)
            slides = arte.carrossel(ofs, fotos, titulo, capa_foto, tema.destaque, estilo)
            tg.enviar_album(chat, [arte.png(s) for s in slides], f"🎠 {k}. {hora} — carrossel (na ordem)")
            tg.enviar_texto(chat, legenda_carrossel(tema, ofs, rng))
            if not dia_lanc and agora.weekday() in (0, 2, 4, 6) and not any(t == "reel" for t in usados):
                try:
                    mp4 = arte.reel(ofs, fotos, titulo, capa_foto, tema.destaque, estilo)
                    if mp4:
                        tg.enviar_video(chat, mp4, "🎬 Reel — escolha a música no Instagram ao postar")
                        tg.enviar_texto(chat, legenda_reel(tema, rng))
                        usados.append("reel")
                except TelegramErro as e:
                    log(f"Aviso: não consegui mandar o Reel: {e}")
            stories += list(zip(ofs, fotos))
            _registrar_usados(estado, agora, carr)
        elif tipo == "post":
            o = _oferta(dado)
            tg.enviar_foto(chat, arte.gerar(o, session=session, cta="Link na bio"), f"🖼️ {k}. {hora} — post do produto")
            tg.enviar_texto(chat, legenda_post(o, rng))
            stories.append((o, None))
            _registrar_usados(estado, agora, [dado])

    for o, f in stories[:6]:
        tg.enviar_foto(chat, arte.png(arte.story(o, f, session=session)), f"📱 Story — link para o adesivo:\n{o.link}")
    log(f"Pacote do dia enviado ({len(roteiro)} posts de feed).")
    return True


def talvez_enviar(tg, cfg, estado, agora, hora=10, log=print):
    """Uma vez por dia, a partir da hora definida."""
    hoje = agora.date().isoformat()
    if not cfg.admin_chat or estado.get("pacote_enviado") == hoje or agora.hour < hora or agora.hour >= cfg.hora_fim:
        return
    estado["pacote_enviado"] = hoje  # marca antes: se der erro no meio, não repete o dia todo
    try:
        montar_e_enviar(tg, cfg.admin_chat, estado, agora, log=log)
    except TelegramErro as e:
        log(f"Aviso: não consegui mandar o pacote do dia: {e}")
