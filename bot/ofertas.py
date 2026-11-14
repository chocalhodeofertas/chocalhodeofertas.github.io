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

    if not (desconto >= min_desconto or (abaixo or 0) >= min_desconto or menor_hist):
        return None

    postado = estado["postados"].get(produto.id)
    if postado:
        dias = (agora - datetime.fromisoformat(postado["quando"])).total_seconds() / 86400
        # Repete só depois de alguns dias, ou se o preço caiu mais 5%
        if dias < repost_dias and preco > postado["preco"] * 0.95:
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
    marcar_queda_real(o, estado, agora)
    return o


# Com pelo menos esta quantidade de dias de histórico, o bot confia no próprio preço "normal"
DIAS_HIST_MIN = 7


def marcar_queda_real(oferta, estado, agora):
    """Guarda na oferta quanto o preço está abaixo do preço normal visto pelo próprio bot."""
    from .estado import preco_tipico

    tipico, dias = preco_tipico(estado, oferta.id, agora)
    oferta.dias_hist = dias
    oferta.queda_real = (1 - oferta.preco / tipico) if tipico else None
    return oferta


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


def pontuacao(oferta, posicao=None):
    """Desconto x popularidade (posição nos mais vendidos) x item essencial. Comissão não conta."""
    pop = 0.0
    if posicao is not None:
        pop = 0.6 if posicao < 3 else 0.35 if posicao < 8 else 0.15 if posicao < 15 else 0.0
    peso = 1.4 if essencial(oferta.titulo) else 1.0
    if oferta.categoria == "brinquedo":
        peso *= 0.85  # brinquedo é o que mais aparece; equilibra com o resto
    elif oferta.categoria == "game" and re.search(r"ps5|ps4|playstation|xbox", (oferta.titulo or "").lower()):
        peso *= 0.7  # console mais comprado por adultos: entra, mas com menos prioridade
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
