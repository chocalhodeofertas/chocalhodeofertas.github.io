"""Decide se o preço de um produto é uma oferta que vale postar."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import re


@dataclass
class Oferta:
    id: str
    titulo: str
    preco: float
    preco_de: Optional[float]  # preço "de" informado pelo próprio Mercado Livre
    desconto: float  # 0.30 = 30%
    abaixo_do_habitual: Optional[float]  # % abaixo do preço de referência da planilha
    menor_preco_historico: bool
    link: str
    imagem: Optional[str]
    categoria: str

    @property
    def forca(self):
        """Usado para ordenar: a melhor oferta vai primeiro."""
        return max(self.desconto, self.abaixo_do_habitual or 0) + (0.05 if self.menor_preco_historico else 0)


def avaliar(produto, info, estado, agora: datetime, min_desconto=0.15, repost_dias=3):
    """Retorna uma Oferta, ou None se não for hora de postar esse produto."""
    if not info or not info.disponivel or not info.preco:
        return None
    preco = float(info.preco)

    preco_de = None
    desconto = 0.0
    if info.preco_original and info.preco_original > preco:
        preco_de = float(info.preco_original)
        desconto = 1 - preco / preco_de

    abaixo = None
    if produto.preco_referencia and produto.preco_referencia > preco:
        abaixo = 1 - preco / produto.preco_referencia

    reg = estado["precos"].get(produto.id)
    menor_hist = bool(reg and len(reg["historico"]) >= 3 and preco < reg["min"] * 0.98)

    # Queda de verdade pelo histórico do próprio bot: vale mesmo sem o "de" do anúncio
    from .estado import preco_tipico
    tipico, dias_hist = preco_tipico(estado, produto.id, agora)
    queda_real = bool(tipico and dias_hist >= DIAS_HIST_MIN and preco <= tipico * (1 - QUEDA_REAL_MIN))

    if not (desconto >= min_desconto or (abaixo or 0) >= min_desconto or menor_hist or queda_real):
        return None

    # Repetição: mesmo anúncio ou título parecido só volta depois de repost_dias, ou 10% abaixo do menor preço já postado
    from .estado import checar_repeticao
    repeticao = checar_repeticao(estado, produto.id, info.titulo, preco, agora, repost_dias)
    if repeticao and repeticao["bloqueado"]:
        return None

    o = Oferta(
        id=produto.id,
        titulo=info.titulo,
        preco=preco,
        preco_de=preco_de,
        desconto=desconto,
        abaixo_do_habitual=abaixo,
        menor_preco_historico=menor_hist,
        link=produto.link_afiliado,
        imagem=info.imagem,
        categoria=produto.categoria,
    )
    o.repeticao = repeticao  # None ou o post anterior (voltou porque baixou)
    marcar_queda_real(o, estado, agora)
    return o


# Com pelo menos esta quantidade de dias de histórico, o bot confia no próprio preço "normal"
DIAS_HIST_MIN = 7
# Preço 10% abaixo do normal (mediana de 30 dias) já é oferta, com ou sem "de" no anúncio
QUEDA_REAL_MIN = 0.10


def marcar_queda_real(oferta, estado, agora):
    """Guarda na oferta quanto o preço está abaixo do preço normal visto pelo próprio bot."""
    from .estado import preco_tipico

    tipico, dias = preco_tipico(estado, oferta.id, agora)
    oferta.dias_hist = dias
    oferta.queda_real = (1 - oferta.preco / tipico) if tipico else None
    # Sem "de" no anúncio, mas com queda de verdade: o post mostra o preço que vinha sendo praticado
    oferta.preco_normal = tipico if (tipico and dias >= DIAS_HIST_MIN and not oferta.preco_de
                                     and oferta.preco <= tipico * (1 - QUEDA_REAL_MIN)) else None
    oferta.selo_dias = selo_menor_preco(estado, oferta.id, oferta.preco, agora)
    return oferta


# Selo "menor preço que o Chocalho viu em N dias": só com histórico suficiente para a frase ser verdadeira
SELO_DIAS_MIN = 14
SELO_JANELA = 30
SELO_DIAS_NO_NIVEL = 3  # se o preço já esteve neste nível em mais dias que isso, não é novidade


def selo_menor_preco(estado, pid, preco, agora, dias_min=SELO_DIAS_MIN):
    """Dias (14 a 30) em que este é o menor preço registrado pelo bot, ou None.

    Exige: 14+ dias acompanhando o produto; nenhum dia da janela (nem hoje mais cedo) com preço menor;
    pelo menos um dia com o preço 3% mais alto (preço parado no mesmo valor não ganha selo); e o preço
    de agora visto em no máximo 3 dias da janela. Essa última regra tira o selo de quem vive alternando
    entre dois preços no Mercado Livre: o "menor preço" dele aparece todo dia, não é queda."""
    from datetime import date

    from .estado import serie_diaria

    hist = (estado.get("precos", {}).get(pid) or {}).get("historico") or []
    if not hist or not preco:
        return None
    hoje = agora.date()
    dias_obs = (hoje - date.fromisoformat(hist[0][0])).days
    if dias_obs < dias_min:
        return None
    janela = min(SELO_JANELA, dias_obs)
    antes = [p for _, p in serie_diaria(estado, pid, agora, janela)]
    hoje_cedo = [p for d, p in hist if d == hoje.isoformat()]
    if not antes or preco > min(antes + hoje_cedo) + 0.009 or max(antes) < preco * 1.03:
        return None
    if sum(1 for p in antes if p <= preco * 1.03) > SELO_DIAS_NO_NIVEL:
        return None
    return janela


def peso_queda_real(oferta):
    """Prioriza quem caiu de verdade. Desconto "de fachada" (preço igual ao de sempre) perde força.
    Sem histórico suficiente, não muda nada."""
    queda, dias = getattr(oferta, "queda_real", None), getattr(oferta, "dias_hist", 0)
    if queda is None or dias < DIAS_HIST_MIN:
        return 1.0
    if queda >= 0.10:
        return 1.3
    if queda < 0.03:
        return 0.6
    return 1.0


# Comissão por categoria: roupa paga 16%, a maioria 12%
# Horários de pico (almoço e noite) recebem mais posts
PESO_HORA = {12: 1.6, 13: 1.6, 19: 1.6, 20: 1.6, 21: 1.6}

# Itens de uso diário e de alta procura: têm mais chance de venda
_ESSENCIAIS = re.compile(
    r"\b(fraldas?|lencos? umedecid[oa]s?|toalhas? umedecidas?|sabonete|shampoo|condicionador infantil|"
    r"hidratante infantil|bodys?|macacao|kit (body|banho)|babador|cadeirinha|cadeira (de|para) (carro|auto)|"
    r"bebe conforto|carrinho de bebe|berco|banheira|trocador|mochila maternidade|bolsa maternidade|"
    r"cueiro|manta|cobertor|lencol|protetor de berco|copo de transicao|pratinho|talheres? infantil)\b"
)

# Mesmo tipo de produto não repete no mesmo dia (ex.: duas babás eletrônicas)
_TIPOS = [
    ("mosquiteiro", r"mosquiteiro"),
    ("baba eletronica", r"baba eletronica|baby monitor|monitor (de )?bebe|camera (de )?bebe"),
    ("cadeirinha de carro", r"cadeirinha|cadeira (de|para) (carro|auto)|bebe conforto|assento elevat"),
    ("carrinho de bebe", r"carrinho (de )?(bebe|passeio)|travel system|\btotoka\b|carrinho guarda.chuva"),
    ("aspirador nasal", r"aspirador nasal|sugador (aspirador )?nasal|sugador.*nariz|aspirador.*nariz"),
    ("assento redutor", r"assento redutor|redutor (de )?assento|redutor sanitario"),
    ("trava de seguranca", r"\btravas?\b.*(seguranca|gaveta|geladeira|porta)|protetor de tomada"),
    ("repelente", r"repelente"),
    ("viseira de banho", r"viseira.*banho|viseira.*shampoo"),
    ("grade de cama", r"grade (de )?(protecao|cama)|grade.*cama"),
    ("bolsa maternidade", r"bolsa maternidade|mala maternidade|mochila maternidade"),
    ("cadeira de alimentacao", r"cadeira(s)? de alimentacao|cadeirao"),
    ("berco", r"\bberco|cercadinho|chiqueirinho|cercado"),
    ("banheira", r"banheira|kit banho"),
    ("tapete de atividades", r"tapete (de )?atividades|ginasio"),
    ("fralda", r"\bfraldas?\b"),
    ("lenco umedecido", r"lencos? umedecid|toalhas? umedecid"),
    ("andador", r"\bandador"),
    ("mobile", r"\bmobile\b"),
    ("piscina", r"piscina|\bboia\b"),
    ("pula pula", r"pula pula|cama elastica|trampolim"),
    ("triciclo/bicicleta", r"triciclo|bicicleta|patinete|motoca"),
    ("lego/blocos", r"\blego\b|blocos de montar"),
    ("boneca", r"\bboneca"),
    ("carrinho de brinquedo", r"hot wheels|carrinho (de )?controle|controle remoto|carrinhos?\b.*(miniatura|friccao|1 ?64|metal)|"
                              r"(maleta|kit|caixa|container|garagem|pista).*\bcarrinhos\b|\d+ carrinhos"),
    ("cozinha de brinquedo", r"cozinha (de )?brinquedo|cozinha infantil|comidinha"),
    ("console", r"\bps5\b|\bps4\b|playstation|xbox|nintendo switch|console"),
    ("cartas pokemon", r"pokemon.*(cartas?|booster|box|deck|tcg)|(cartas?|booster).*pokemon"),
    ("mochila", r"\bmochila|lancheira"),
    ("fantasia", r"\bfantasia"),
    ("lapis de cor", r"lapis de cor|canetinha|giz de cera"),
    ("instrumento musical", r"\bpiano|teclado|guitarra|bateria infantil|microfone"),
]
_TIPOS_RE = [(t, re.compile(p)) for t, p in _TIPOS]


# Palavras de embalagem/quantidade: não dizem o que o produto é
_EMBALAGEM = {"kit", "kits", "com", "para", "infantil", "infantis", "bebe", "bebes", "baby", "maleta", "caixa",
              "container", "combo", "pacote", "conjunto", "jogo", "par", "unidades", "pecas", "novo", "nova",
              "original", "super", "mega", "mini", "promocao", "oferta", "brinquedo", "brinquedos"}


def tipo_produto(titulo):
    """Tipo do produto, para não repetir o mesmo tipo no dia (ML e Shopee juntos).
    Sem tipo conhecido: a primeira palavra que diz o que é o produto, no singular."""
    from .filtros import normalizar

    t = normalizar(titulo)
    for nome, padrao in _TIPOS_RE:
        if padrao.search(t):
            return nome
    palavras = [p for p in re.findall(r"[a-z]+", t) if len(p) > 2 and p not in _EMBALAGEM]
    if not palavras:
        return t[:20]
    p = palavras[0]
    return p[:-1] if p.endswith("s") and not p.endswith("ss") else p


def tipos_recentes(estado, agora, horas=48):
    """Tipos postados nas últimas horas (ML + Shopee). Servem para dar a vez a outros tipos."""
    from datetime import datetime, timedelta

    corte = agora - timedelta(hours=horas)
    fontes = list(estado.get("postados", {}).values()) + list(estado.get("shopee", {}).get("titulos", {}).values())
    tipos = set()
    for v in fontes:
        try:
            if v.get("titulo") and datetime.fromisoformat(v["quando"]) > corte:
                tipos.add(tipo_produto(v["titulo"]))
        except (KeyError, ValueError, TypeError):
            pass
    return tipos


def priorizar_tipos_novos(ofertas, estado, agora, titulo=lambda o: o.titulo):
    """Mantém a ordem de pontuação, mas quem é de um tipo que não saiu nos últimos 2 dias vai na frente.
    Os outros só entram se não houver alternativa (o limite de 1 por tipo no dia continua valendo)."""
    recentes = tipos_recentes(estado, agora)
    return sorted(ofertas, key=lambda o: tipo_produto(titulo(o)) in recentes)


# Rodízio de categorias (aprovado pelo Leonardo em 17/11): brinquedo não passa de ~30% do dia e as categorias
# que quase não aparecem ganham a frente da fila até ter COTA_MIN posts no dia. Só muda a ORDEM entre ofertas
# que já passaram em todas as regras; não cria oferta nem baixa o desconto mínimo.
TETO_BRINQUEDO = 0.30
TETO_A_PARTIR_DE = 6  # o teto só vale depois de alguns posts no dia (de manhã 1 de 2 seria 50%)
CATEGORIAS_COTA = ("alimentacao", "passeio", "roupa", "quarto")
COTA_MIN = 2


def categoria_efetiva(categoria, titulo):
    """Categoria da descoberta do ML; quando ela não diz nada ("outros"), a categoria pelo título."""
    if categoria and categoria != "outros":
        return categoria
    from .shopee_ofertas import categoria_do_titulo

    return categoria_do_titulo(titulo or "") or "outros"


def categorias_do_dia(estado, agora):
    """Contagem por categoria do que saiu hoje no canal (ML + Shopee), pelo registro de posts do dia."""
    from collections import Counter

    reg = estado.get("posts_dia")
    if not isinstance(reg, dict) or reg.get("dia") != agora.date().isoformat():
        return Counter()
    return Counter(categoria_efetiva(i.get("categoria"), i.get("titulo")) for i in reg.get("itens") or [])


def equilibrar_categorias(ofertas, estado, agora, titulo=lambda o: o.titulo,
                          categoria=lambda o: getattr(o, "categoria", "")):
    """Reordena (sem tirar ninguém): categoria em falta na frente, brinquedo acima do teto no fim."""
    cont = categorias_do_dia(estado, agora)
    total = sum(cont.values())

    def chave(o):
        c = categoria_efetiva(categoria(o), titulo(o))
        if c == "brinquedo" and total >= TETO_A_PARTIR_DE and (cont[c] + 1) / (total + 1) > TETO_BRINQUEDO:
            return 2
        if c in CATEGORIAS_COTA and cont[c] < COTA_MIN:
            return 0
        return 1

    return sorted(ofertas, key=chave)


def tipos_do_dia(estado, agora):
    """Tipos já postados hoje, somando Mercado Livre e Shopee."""
    hoje = agora.date().isoformat()
    titulos = [v.get("titulo", "") for v in estado.get("postados", {}).values()
               if v.get("quando", "").startswith(hoje)]
    titulos += [v.get("titulo", "") for v in estado.get("shopee", {}).get("titulos", {}).values()
                if v.get("quando", "").startswith(hoje)]
    return {tipo_produto(t) for t in titulos if t} | set(estado.get("shopee", {}).get("tipos", {}).get(hoje, []))


def essencial(titulo):
    from .filtros import normalizar

    return bool(_ESSENCIAIS.search(normalizar(titulo)))


def pontuacao(oferta, posicao=None, agora=None):
    """Desconto x popularidade (posição nos mais vendidos) x item essencial x época do ano. Comissão não conta.
    Com 'agora', produto da época (Natal, volta às aulas, verão...) sobe um pouco: ver bot/sazonal.py."""
    pop = 0.0
    if posicao is not None:
        pop = 0.6 if posicao < 3 else 0.35 if posicao < 8 else 0.15 if posicao < 15 else 0.0
    peso = 1.4 if essencial(oferta.titulo) else 1.0
    if oferta.categoria == "brinquedo":
        peso *= 0.85  # brinquedo é o que mais aparece; equilibra com o resto
    elif oferta.categoria == "game" and re.search(r"ps5|ps4|playstation|xbox", (oferta.titulo or "").lower()):
        peso *= 0.7  # console mais comprado por adultos: entra, mas com menos prioridade
    if agora is not None:
        from . import sazonal
        peso *= sazonal.peso(oferta.titulo, agora, oferta.categoria)
    return oferta.forca * (1 + pop) * peso * peso_queda_real(oferta)


def meta_ate_agora(max_por_dia, hora, inicio=8, fim=22):
    """Quantos posts já 'deveriam' ter saído até o fim desta hora (ritmo do dia)."""
    pesos = {h: PESO_HORA.get(h, 1.0) for h in range(inicio, fim)}
    total = sum(pesos.values()) or 1
    feito = sum(v for h, v in pesos.items() if h <= hora)
    return int(max_por_dia * feito / total + 0.999)


def limite_hora(max_por_hora, hora):
    """No pico, até 2 posts a mais por hora."""
    return max_por_hora + (2 if hora in PESO_HORA else 0)


def vagas_da_rodada(agora, max_rodada, max_hora, max_dia, feitos_hora, feitos_hoje, inicio=8, fim=22):
    """Quantos posts cabem nesta rodada pelo ritmo do dia.
    Na janela da meia-noite (Black Friday, 12.12) vale só o limite por hora, com o reforço de pico:
    é um extra da data, fora da conta do dia."""
    from . import horario

    if horario.meia_noite(agora):
        return max(0, min(max_rodada, max_hora + 2 - feitos_hora))
    return max(0, min(max_rodada, limite_hora(max_hora, agora.hour) - feitos_hora,
                      min(max_dia, meta_ate_agora(max_dia, agora.hour, inicio, fim)) - feitos_hoje))


# Palavras que não ajudam a dizer se dois títulos são o mesmo produto
_VAZIAS = {"kit", "com", "para", "de", "da", "do", "das", "dos", "em", "e", "a", "o", "infantil", "bebe", "bebes",
           "baby", "crianca", "criancas", "menino", "menina", "unissex", "original", "novo", "nova", "promocao",
           "oferta", "envio", "imediato", "pronta", "entrega"}


def assinatura(titulo):
    """Primeiras palavras que importam no título (para achar o mesmo produto com outro anúncio)."""
    from .filtros import normalizar

    return [p for p in re.findall(r"[a-z0-9]+", normalizar(titulo)) if p not in _VAZIAS and len(p) > 1][:8]


def parecido(a, b):
    """True se os dois títulos parecem o mesmo produto (ou um bem parecido)."""
    wa, wb = assinatura(a), assinatura(b)
    if not wa or not wb:
        return False
    sa, sb = set(wa), set(wb)
    comuns = len(sa & sb)
    return (comuns >= 3 and comuns / len(sa | sb) >= 0.5) or (len(wa) >= 3 and wa[:3] == wb[:3])
