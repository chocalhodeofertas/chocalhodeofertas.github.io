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


# Temas por categoria: no dia, vence a categoria com mais promoções
TEMAS_CATEGORIA = [
    Tema("brinquedos", {"brinquedo"},
         ["Brinquedos que baixaram de preço hoje", "Ideias de presente em promoção",
          "Presentes que estão mais baratos hoje"],
         ["brinquedos", "crianca"],
         ["Aniversário, Natal ou só aquele mimo?", "Pra quem procura presente sem gastar muito:",
          "Diversão pros pequenos com preço bom."]),
    Tema("roupas", {"roupa"},
         ["Roupinhas em promoção hoje", "Roupas de bebê e criança com desconto"],
         ["enxoval"],
         ["Eles crescem rápido, e a gente economiza onde dá:", "Pra renovar o guarda-roupa dos pequenos:"]),
    Tema("higiene", {"higiene", "fralda"},
         ["Higiene e banho do bebê com desconto", "Itens de higiene que baixaram de preço"],
         ["enxoval"],
         ["Item de uso diário em promoção é economia o mês todo.", "Pra hora do banho e da troca:"]),
    Tema("quarto", {"quarto"},
         ["Pro quarto do bebê: promoções de hoje", "Coisas pro quartinho que baixaram de preço"],
         ["quarto"],
         ["Montando ou renovando o quartinho?", "Aconchego pro quarto dos pequenos:"]),
    Tema("passeio", {"passeio"},
         ["Pra passear com os pequenos: promoções de hoje", "Itens de passeio que baixaram de preço"],
         ["passeio"],
         ["Sair de casa com criança fica mais fácil com as coisas certas."]),
    Tema("alimentacao", {"alimentacao"},
         ["Hora da papinha: itens em promoção", "Pra alimentação dos pequenos, com desconto"],
         ["alimentacao"],
         ["Introdução alimentar sem gastar muito:", "Pra hora das refeições:"]),
    Tema("gestante", {"gestante"},
         ["Pra gestante: promoções de hoje", "Itens pra gravidez com desconto"],
         ["gestante"],
         ["Cuidar de você também faz parte.", "Pra quem está esperando um bebê:"]),
]
TEMAS_CATEGORIA += [
    Tema("escola", {"escola"}, ["Material escolar em promoção", "Pra volta às aulas: ofertas de hoje"],
         ["crianca"], ["Lista de material sem susto no bolso:", "Pra mochila ficar completa:"]),
    Tema("livros", {"livro"}, ["Livros infantis em promoção", "Pra estante dos pequenos: livros com desconto"],
         ["crianca", "familia"], ["Ler junto é um dos melhores momentos do dia.", "Pra criar o hábito da leitura:"]),
    Tema("games", {"game"}, ["Games e diversão em promoção", "Pra jogar em família: ofertas de hoje"],
         ["crianca", "brinquedos"], ["Diversão pra tarde de chuva:", "Pra jogar junto:"]),
    Tema("esporte", {"esporte"}, ["Pra brincar ao ar livre: promoções", "Esporte e diversão com desconto"],
         ["crianca"], ["Pra gastar energia:", "Bora se mexer?"]),
    Tema("casa", {"casa"}, ["Pro quarto das crianças: promoções", "Organização e decoração infantil com desconto"],
         ["quarto"], ["Casa organizada, vida mais leve:", "Pro cantinho dos pequenos:"]),
]
# Reserva, quando nenhuma categoria tem promoções suficientes sozinha
TEMAS_GERAIS = [
    Tema("enxoval", {"quarto", "passeio", "alimentacao", "gestante", "higiene", "fralda", "roupa", "outros"},
         ["Achei promoções pro enxoval", "Coisas de bebê que baixaram de preço hoje",
          "O que eu compraria hoje se estivesse montando o enxoval"],
         ["quarto", "enxoval", "gestante", "familia"],
         ["Montando o enxoval sem estourar o orçamento?", "Pra quem está preparando a chegada do bebê:",
          "Enxoval não precisa custar uma fortuna."]),
    Tema("ate50", None,
         ["Achados até R$ 50 pra família", "Coisas úteis até R$ 50 em promoção hoje"],
         ["familia", "crianca", "enxoval"],
         ["Economizar também é cuidar.", "Pequenos preços, grandes ajudas no dia a dia:"],
         preco_max=50),
]
TEMAS = TEMAS_CATEGORIA + TEMAS_GERAIS


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
    """Escolhe os temas do dia: primeiro as categorias com mais promoções hoje, sem repetir
    o tema dos últimos 2 dias; se faltar, usa os temas gerais. Produtos não se repetem."""
    itens = _itens(estado)
    usados = set(_usados(estado, agora))
    limite = (agora - timedelta(days=2)).date().isoformat()
    recentes = {t for t, d in (estado.get("temas_recentes") or {}).items() if d >= limite}
    ranking = sorted(TEMAS_CATEGORIA, key=lambda t: -len(_candidatos(t, itens, usados)))
    ordem = ([t for t in ranking if t.nome not in recentes] + TEMAS_GERAIS
             + [t for t in ranking if t.nome in recentes])
    escolhidos = []
    for tema in ordem:
        if len(escolhidos) == n_carrosseis:
            break
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


# Lançamento do perfil: 9 posts em 3 dias = 3 da marca (fixados), 3 temáticos e 3 de produto.
# O temático é sempre às 18h (coluna do meio da grade); marca e produto alternam nas pontas.
# No dia 2 o temático sai como Reel, para testar o formato.
LANCAMENTO_INICIO = date(2026, 11, 9)
LANCAMENTO = [
    [("fixado:o_que_e", "12h"), ("carrossel", "18h"), ("post", "20h30")],
    [("post", "12h"), ("reel", "18h"), ("fixado:como_funciona", "20h30")],
    [("fixado:perguntas", "12h"), ("carrossel", "18h"), ("post", "20h30")],
]
LEGENDAS_FIXADOS = {
    "como_funciona": "\n".join([
        "Como funciona o Chocalho de Ofertas 🧸",
        "",
        "1. A gente garimpa promoções de produtos para bebês e crianças todos os dias.",
        "2. Você recebe no nosso grupo gratuito, com foto, preço e link.",
        "3. Compra direto na página oficial da loja, pelo mesmo preço.",
        "",
        "🔗 Link do grupo na bio.",
        "Contém links de afiliado. #publi"]),
    "o_que_e": "\n".join([
        "Prazer, Chocalho de Ofertas! 🧸",
        "",
        "Um canal de ofertas pra famílias que amam economizar: do enxoval aos brinquedos, "
        "a gente encontra as promoções e você escolhe o que faz sentido pra sua casa.",
        "",
        "✨ Promoções do dia com desconto de verdade",
        "🎟️ Cupons das lojas assim que saem",
        "",
        "🔗 Entre no grupo gratuito pelo link da bio (WhatsApp ou Telegram).",
        "#publi"]),
    "perguntas": "\n".join([
        "Separamos as dúvidas que mais chegam pra gente 💬",
        "",
        "Ficou com alguma outra? Manda aqui nos comentários!",
        "🔗 Link do grupo na bio.",
        "#publi"]),
}


def plano_do_dia(agora):
    """Roteiro de posts do feed para hoje. Fora do lançamento: rotina normal."""
    k = (agora.date() - LANCAMENTO_INICIO).days
    if 0 <= k < len(LANCAMENTO):
        return k + 1, LANCAMENTO[k]
    return None, [("post", "12h"), ("carrossel", "18h"), ("post", "20h30")]


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


def _registrar_tema(estado, agora, tema):
    hoje = agora.date().isoformat()
    lim = (agora - timedelta(days=7)).date().isoformat()
    rec = {t: d for t, d in (estado.get("temas_recentes") or {}).items() if d >= lim}
    rec[tema.nome] = hoje
    estado["temas_recentes"] = rec


def montar_e_enviar(tg, chat, estado, agora, rng=random, log=print, session=None):
    dia_lanc, plano = plano_do_dia(agora)
    n_carr = sum(1 for t, _ in plano if t in ("carrossel", "reel"))
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
        elif tipo in ("carrossel", "reel") and fila_c:
            tema, carr = fila_c.pop(0)
            roteiro.append((k, hora, tipo, (tema, carr)))
            linhas.append(f"{k}. {hora} — {'Reel' if tipo == 'reel' else 'carrossel'} temático <b>{tema.nome}</b>")
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
        elif tipo == "reel":
            tema, carr = dado
            ofs = [_oferta(i) for i in carr]
            fotos = [arte.baixar_foto(o.imagem, session) for o in ofs]
            titulo = rng.choice(tema.titulos)
            estilo = "grande" if (estilo_base + n_c) % 2 == 0 else "faixas"
            capa_foto = arte.foto_de_capa(tema.fotos, rng)
            arte.registrar_capa(capa_foto)
            mp4 = arte.reel(ofs, fotos, titulo, capa_foto, tema.destaque, estilo)
            if mp4:
                tg.enviar_video(chat, mp4, f"🎬 {k}. {hora} — Reel temático (escolha a música no Instagram)")
                capa_916 = arte.capa(capa_foto, titulo, tema.destaque, estilo, L=1080, A=1920)
                tg.enviar_documento(chat, arte.png(capa_916), "capa_reel.png",
                                    "🖼️ Capa do Reel: em 'Editar capa', escolha 'Adicionar da galeria'", "image/png")
                tg.enviar_texto(chat, legenda_carrossel(tema, ofs, rng))
            else:  # sem ffmpeg: manda como carrossel
                slides = arte.carrossel(ofs, fotos, titulo, capa_foto, tema.destaque, estilo)
                tg.enviar_album(chat, [arte.png(s) for s in slides], f"🎠 {k}. {hora} — carrossel (o Reel falhou)")
                tg.enviar_texto(chat, legenda_carrossel(tema, ofs, rng))
            stories += list(zip(ofs, fotos))
            _registrar_usados(estado, agora, carr)
            _registrar_tema(estado, agora, tema)
        elif tipo == "carrossel":
            tema, carr = dado
            ofs = [_oferta(i) for i in carr]
            fotos = [arte.baixar_foto(o.imagem, session) for o in ofs]
            titulo = rng.choice(tema.titulos)
            estilo = "grande" if (estilo_base + n_c) % 2 == 0 else "faixas"
            capa_foto = arte.foto_de_capa(tema.fotos, rng)
            arte.registrar_capa(capa_foto)
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
            _registrar_tema(estado, agora, tema)
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


# ---------- Peças sob demanda (você escolhe no dia) ----------

NOMES_TEMA = {t.nome: t for t in TEMAS}


def listar_temas(estado, agora):
    """Quantas promoções cada tema tem agora, para você escolher o do dia."""
    itens = _itens(estado)
    linhas = ["🎯 <b>Temas com promoções agora</b>", ""]
    for t in TEMAS:
        cand = _candidatos(t, itens, set())
        if cand:
            top = ", ".join(_curto(i["titulo"], 28) for i in cand[:3])
            linhas.append(f"• <b>{t.nome}</b> — {len(cand)} ofertas (ex.: {top})")
    linhas += ["", "Para gerar: <b>carrossel brinquedos</b> ou <b>reel brinquedos</b> (troque pelo tema).",
               "Para o post de um produto: <b>insta</b> + o link meli.la dele."]
    return "\n".join(linhas)


def enviar_tema(tg, chat, estado, agora, nome, formato="carrossel", rng=random, session=None):
    tema = NOMES_TEMA.get(nome)
    if not tema:
        return f"Não conheço o tema “{nome}”. Opções: {', '.join(NOMES_TEMA)}."
    cand = _candidatos(tema, _itens(estado), set())
    if len(cand) < 3:
        return f"O tema <b>{nome}</b> tem só {len(cand)} oferta(s) agora; preciso de pelo menos 3."
    capa_foto = arte.foto_de_capa(tema.fotos, rng)
    arte.registrar_capa(capa_foto)
    if capa_foto is None:
        return f"Faltam fotos de capa para o tema <b>{nome}</b>."
    carr = cand[:4]
    ofs = [_oferta(i) for i in carr]
    fotos = [arte.baixar_foto(o.imagem, session) for o in ofs]
    titulo = rng.choice(tema.titulos)
    estilo = rng.choice(["grande", "faixas"])
    if formato == "reel":
        mp4 = arte.reel(ofs, fotos, titulo, capa_foto, tema.destaque, estilo)
        if not mp4:
            return "⚠️ Não consegui montar o vídeo agora. Tente o carrossel."
        tg.enviar_video(chat, mp4, "🎬 Reel temático (escolha a música no Instagram)")
        capa_916 = arte.capa(capa_foto, titulo, tema.destaque, estilo, L=1080, A=1920)
        tg.enviar_documento(chat, arte.png(capa_916), "capa_reel.png",
                            "🖼️ Capa do Reel: em 'Editar capa', escolha 'Adicionar da galeria'", "image/png")
    else:
        slides = arte.carrossel(ofs, fotos, titulo, capa_foto, tema.destaque, estilo)
        tg.enviar_album(chat, [arte.png(s) for s in slides], "🎠 Carrossel temático (na ordem)")
    tg.enviar_texto(chat, legenda_carrossel(tema, ofs, rng))
    for o, f in zip(ofs, fotos):
        tg.enviar_foto(chat, arte.png(arte.story(o, f, session=session)), f"📱 Story — link para o adesivo:\n{o.link}")
    _registrar_tema(estado, agora, tema)
    return None


def enviar_post_produto(tg, chat, oferta, rng=random, session=None):
    """Post único do Instagram (com 'Link na bio'), legenda e story de um produto que você escolheu."""
    tg.enviar_foto(chat, arte.gerar(oferta, session=session, cta="Link na bio"), "🖼️ Post do produto")
    tg.enviar_texto(chat, legenda_post(oferta, rng))
    tg.enviar_foto(chat, arte.png(arte.story(oferta, None, session=session)),
                   f"📱 Story — link para o adesivo:\n{oferta.link}")
