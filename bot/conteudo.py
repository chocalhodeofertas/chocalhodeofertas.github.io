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
from datetime import timedelta
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
         ["familia", "enxoval"],
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
         ["crianca", "familia", "brinquedos"],
         ["Economizar também é cuidar.", "Pequenos preços, grandes ajudas no dia a dia:"],
         preco_max=50),
    Tema("passeio", {"passeio"},
         ["Pra passear com os pequenos: promoções de hoje", "Itens de passeio que baixaram de preço"],
         ["passeio", "familia"],
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


def escolher(estado, agora, rng=random, n=4):
    """Escolhe o tema do dia (rodízio) e os produtos do carrossel e dos posts únicos."""
    itens = _itens(estado)
    limite = (agora - timedelta(days=3)).date().isoformat()
    usados = {k for k, v in (estado.get("pacote_usados") or {}).items() if v >= limite}
    dia = agora.toordinal()
    for k in range(len(TEMAS)):
        tema = TEMAS[(dia + k) % len(TEMAS)]
        cand = _candidatos(tema, itens, usados)
        if len(cand) >= 3:
            carr = cand[:n]
            resto = [i for i in sorted(itens, key=lambda i: -(i.get("desconto") or 0))
                     if i not in carr and i["id"] not in usados][:3]
            return tema, carr, resto
    return None, [], []


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


def montar_e_enviar(tg, chat, estado, agora, rng=random, log=print, session=None):
    tema, carr, resto = escolher(estado, agora, rng)
    if not tema:
        tg.enviar_texto(chat, "📦 Ainda não tenho ofertas suficientes para o pacote de hoje. Tento de novo mais tarde.")
        return False
    ofs = [_oferta(i) for i in carr]
    fotos = [arte.baixar_foto(o.imagem, session) for o in ofs]
    titulo = rng.choice(tema.titulos)
    estilo = "grande" if agora.toordinal() % 2 == 0 else "faixas"
    capa_foto = arte.foto_de_capa(tema.fotos, rng)
    destaque = tema.destaque

    tg.enviar_texto(chat, f"📦 <b>Pacote do dia</b> — tema: <b>{titulo}</b>\n"
                          "Carrossel, Reel, posts e stories logo abaixo. Os preços valem para agora; "
                          "se demorar muito para postar, confira antes.", html=True)

    slides = arte.carrossel(ofs, fotos, titulo, capa_foto, destaque, estilo)
    tg.enviar_album(chat, [arte.png(s) for s in slides], "🎠 Carrossel (na ordem)")
    tg.enviar_texto(chat, legenda_carrossel(tema, ofs, rng))

    try:
        mp4 = arte.reel(ofs, fotos, titulo, capa_foto, destaque, estilo)
        if mp4:
            tg.enviar_video(chat, mp4, "🎬 Reel — escolha a música no Instagram ao postar")
            tg.enviar_texto(chat, legenda_reel(tema, rng))
    except TelegramErro as e:
        log(f"Aviso: não consegui mandar o Reel: {e}")

    for i in resto:
        o = _oferta(i)
        tg.enviar_foto(chat, arte.gerar(o, session=session, cta="Link na bio"), "🖼️ Post único")
        tg.enviar_texto(chat, legenda_post(o, rng))

    for o, f in list(zip(ofs, fotos)) + [(_oferta(i), None) for i in resto]:
        tg.enviar_foto(chat, arte.png(arte.story(o, f, session=session)), f"📱 Story — link para o adesivo:\n{o.link}")

    hoje = agora.date().isoformat()
    usados = {k: v for k, v in (estado.get("pacote_usados") or {}).items()
              if v >= (agora - timedelta(days=7)).date().isoformat()}
    for i in carr + resto:
        usados[i["id"]] = hoje
    estado["pacote_usados"] = usados
    log(f"Pacote do dia enviado (tema {tema.nome}).")
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
