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
    # item de reposição (fralda, lenço...) não vai para o fim da fila por já ter saído: ele pode repetir no dia
    return sorted(ofertas, key=lambda o: not reposicao(titulo(o)) and tipo_produto(titulo(o)) in recentes)


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


# ---------------------------------------------------------------- itens de reposição (aprovado pelo Leonardo, 17/11)
# Coisas que a família compra sempre, em muitas marcas e tamanhos: podem sair várias vezes no dia (fralda até 8,
# os outros até 5 de cada tipo); marca ou tamanho diferente é OUTRO produto; o mesmo (marca + tamanho) volta em 3 dias.
# Papinha e cereal infantil ficam de fora (a NBCAL restringe a propaganda); protetor de mamilo também.
REPOSICAO = [
    ("fralda", r"\bfraldas?\b(?!.*\b(pano|ecologica|natacao|piscina|reutiliza))", 8),
    ("lenco umedecido", r"lencos? umedecid|toalhas? umedecid|lencinhos? umedecid", 5),
    ("pomada de assadura", r"assadura|pomada (infantil|bebe)|creme (preventivo|barreira)|hipoglos|bepantol baby|dermodex", 5),
    ("shampoo e sabonete", r"\bshampoo|\bsabonete|condicionador infantil|condicionador.*(bebe|kids|infantil)|"
                           r"(sabonete|shampoo).*(cabeca aos pes)|banho.*(liquido|glicerina)", 5),
    ("hidratante e oleo", r"hidratante (infantil|bebe|kids)|locao hidratante.*(bebe|infantil)|oleo (de amendoas )?(infantil|bebe|baby)|"
                          r"colonia (infantil|bebe|baby)", 5),
    ("algodao e cotonete", r"\balgodao (em )?(bola|disco|quadrado|rolo)|\bcotonete|hastes? flexive", 5),
    ("protetor solar", r"protetor solar|filtro solar|fps ?\d", 5),
    ("repelente", r"repelente", 5),
    ("higiene bucal", r"creme dental|pasta de dente|gel dental|escova (de )?dente|escova dental", 5),
    ("roupa de bebe (lavar)", r"(sabao|lava.roupas?|amaciante).*(bebe|infantil|baby)|(bebe|infantil|baby).*(sabao|lava.roupas?|amaciante)", 5),
    ("absorvente de seio", r"absorventes? (de|para) seios?|absorventes? (para )?amamentacao|discos? de amamentacao", 5),
]
_REPOSICAO_RE = [(nome, re.compile(p), lim) for nome, p, lim in REPOSICAO]
REPOSICAO_DIAS = 3  # o mesmo item de reposição (mesma marca e tamanho) volta depois disso
MARCAS_REPOSICAO = (
    "pampers, huggies, mamypoko, personal, babysec, turma da monica, pom pom, pompom, cremer, johnsons, johnson, "
    "granado, mustela, natura, cetaphil, dove, nivea, sundown, episol, neutrogena, banana boat, isdin, exposis, repelex, "
    "avon, boticario, baby soft, babysoft, hipoglos, bepantol, dermodex, desitin, colgate, sorriso, malvatrikids, curaprox, "
    "dentalclean, tandy, omo, ype, comfort, downy, dreft, brilhante, topz, cottonbaby, apolo, bioderma, la roche posay, "
    "eucerin, baruel, needs, muriel, giovanna baby, tra la la, plim plim, chicco, lillo, kuka, buba, huggies supreme"
).split(", ")


def _norm(titulo):
    from .filtros import normalizar
    return normalizar(titulo or "")


# Acessórios que citam o item de reposição no título, mas não são ele (20/11: trocador "de fralda",
# lixeira "para fraldas", "bolha de sabão" infantil, viseira "anti shampoo", mordedor "escova de dentes")
_NAO_E_REPOSICAO = {
    "fralda": re.compile(r"\b(trocador|porta|lixeira|lixo|cesto|organizador|bolsa|mochila|pano|boca|ombro|toalha|"
                         r"saida maternidade|saquinhos?|capa|cueiro|tecido|reutilizave\w*|aquecedor|dispenser|"
                         r"bordad\w*|boneca|brinquedo)\b"),
    "shampoo e sabonete": re.compile(r"\b(esponja|viseira|chapeu|protetor|dispenser|saboneteira|porta (shampoo|sabonete)|"
                                     r"brinquedo|banheira)\b"),
    "roupa de bebe (lavar)": re.compile(r"\b(bolhas?|bolinhas?|lanca|brinquedo|pistola|maquina de bolha)\b"),
    "higiene bucal": re.compile(r"\b(mordedor|brinquedo)\b"),
}


def _reposicao(titulo):
    t = _norm(titulo)
    for nome, padrao, lim in _REPOSICAO_RE:
        if padrao.search(t):
            nao = _NAO_E_REPOSICAO.get(nome)
            if nao and nao.search(t):
                continue
            return nome, lim
    return None, 1


def reposicao(titulo):
    """Tipo de item de reposição (fralda, lenço umedecido...) ou None."""
    return _reposicao(titulo)[0]


def limite_por_dia(titulo):
    return _reposicao(titulo)[1]


def tipo_chave(titulo):
    """Chave do limite por dia: o tipo de reposição, ou o tipo do produto (1 por dia)."""
    return reposicao(titulo) or tipo_produto(titulo)


def marca(titulo):
    t = " " + re.sub(r"[^a-z0-9 ]+", "", _norm(titulo).replace("'s ", "s ")) + " "
    for m in sorted({_norm(x) for x in MARCAS_REPOSICAO}, key=len, reverse=True):
        if f" {m} " in t:
            return m
    return None


_TAMANHO = re.compile(r"\b(rn|pp|p|m|g|xg|xxg|xxxg|eg|exg|g/xg|p/m|m/g|xg/xxg)\b")
_QUANT = re.compile(r"(\d+[.,]?\d*)\s?(ml|l|g|kg|un|und|unid|unidades|fraldas|tiras|pecas|pares|pacotes?)\b")


def tamanho(titulo):
    """Tamanho e quantidade do item ('g', '92un'...), para marca/tamanho diferente contar como outro produto."""
    t = _norm(titulo)
    letras = sorted(set(m.group(1) for m in _TAMANHO.finditer(t)))
    quant = sorted(set(f"{m.group(1).replace(',', '.')}{m.group(2)[:2]}" for m in _QUANT.finditer(t)))
    return tuple(letras + quant)


def mesmo_item_reposicao(a, b):
    """Dois títulos de reposição são o MESMO produto só com o mesmo tipo, a mesma marca e o mesmo tamanho."""
    ra, rb = reposicao(a), reposicao(b)
    if not ra or ra != rb:
        return False
    ma, mb = marca(a), marca(b)
    if ma != mb:
        return False
    if ma is None and not parecido(a, b):
        return False
    return tamanho(a) == tamanho(b)


def contar_tipos_do_dia(estado, agora):
    """Quantos de cada tipo já saíram hoje (ML + Shopee), pela chave de tipo_chave."""
    from collections import Counter

    hoje = agora.date().isoformat()
    vistos, titulos = set(), []
    for pid, quando, _, titulo in estado.get("posts_hist") or []:
        if str(quando).startswith(hoje) and titulo:
            vistos.add((pid, quando)); titulos.append(titulo)
    fontes = list(estado.get("postados", {}).items()) + list(estado.get("shopee", {}).get("titulos", {}).items())
    for pid, v in fontes:
        if isinstance(v, dict) and str(v.get("quando", "")).startswith(hoje) and v.get("titulo") and (pid, v["quando"]) not in vistos:
            titulos.append(v["titulo"])
    return Counter(tipo_chave(t) for t in titulos)


def cabe_no_dia(contagem, titulo):
    return contagem.get(tipo_chave(titulo), 0) < limite_por_dia(titulo)


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
    """True se os dois títulos parecem o mesmo produto (ou um bem parecido). Ver `comparar_titulos`."""
    return comparar_titulos(a, b)["igual"]


# Palavras comuns em títulos de produto infantil: contam pouco (peso 0,3) na comparação
_COMUNS = {"brinquedo", "brinquedos", "educativo", "educativa", "musical", "interativo", "interativa", "som", "sons",
           "luz", "luzes", "presente", "sensorial", "montessori", "colorido", "colorida", "coloridos", "conjunto",
           "cor", "cores", "tamanho", "unico", "grande", "pequeno", "pequena", "mini", "super", "premium", "macio",
           "macia", "fofo", "fofa", "divertido", "divertida", "kids", "pecas", "peca", "pcs", "unidades", "un", "und",
           "silicone", "plastico", "tecido", "algodao", "pelucia", "jogo", "boneco", "boneca", "anos", "meses", "ano",
           "mes", "idade", "crianca", "infantis", "bebes", "recem", "nascido", "rn", "menino", "menina", "meninos",
           "meninas", "unissex", "qualidade", "alta", "lindo", "linda", "novo", "nova", "top", "melhor", "promocao",
           "atividades", "atividade", "movimento", "desenvolvimento", "coordenacao", "motora", "aprendizado"}
_CORES = {"preto", "preta", "branco", "branca", "rosa", "azul", "verde", "amarelo", "amarela", "vermelho", "vermelha",
          "cinza", "lilas", "roxo", "roxa", "bege", "marrom", "laranja", "dourado", "prata", "nude", "off", "white",
          "pink", "blue", "claro", "clara", "escuro", "escura", "bebe"}
# Medida/quantidade: "100cm", "aro 12", "kit 30", "30 caixas"... valores diferentes = produtos diferentes
_MEDIDA = re.compile(r"(\d+(?:[.,]\d+)?)\s?(cm|mm|m|ml|l|kg|g|polegadas|pol)\b")
_CONTAGEM = re.compile(r"\b(?:kit|aro|com|c)\s?(\d+)\b|\b(\d+)\s?(pecas|pcs|unidades|un|und|caixas|pares|potes|"
                       r"bolas|bonecos|carrinhos|livros|cartas|blocos|fraldas|lencos|folhas|cores|em 1|em1|velocidades)\b")


def _raiz(p):
    """Singular simples: "mordedores" e "mordedor", "bolas" e "bola" contam como a mesma palavra."""
    if len(p) > 5 and p.endswith("es") and p[-3] in "rsz":
        return p[:-2]
    if len(p) > 3 and p.endswith("s") and not p.endswith("ss") and not p.isdigit():
        return p[:-1]
    return p


_CORES_R = {_raiz(p) for p in _CORES}
_COMUNS_R = {_raiz(p) for p in _COMUNS}


def _palavras_titulo(titulo):
    from .filtros import normalizar

    return [_raiz(p) for p in re.findall(r"[a-z0-9]+", normalizar(titulo or "")) if len(p) > 1 or p.isdigit()]


def _medidas(titulo):
    from .filtros import normalizar

    t = normalizar(titulo or "")
    med = {}
    for v, u in _MEDIDA.findall(t):
        u = {"mm": "cm", "m": "cm", "l": "ml", "kg": "g", "pol": "polegadas"}.get(u, u)
        valor = float(v.replace(",", "."))
        valor = valor / 10 if u == "cm" and re.search(rf"{re.escape(v)}\s?mm", t) else valor
        med.setdefault(u, set()).add(valor * (100 if re.search(rf"\b{re.escape(v)}\s?m\b", t) else 1))
    for m in _CONTAGEM.finditer(t):
        if m.group(1):
            chave = "aro" if m.group(0).startswith("aro") else "kit"
            med.setdefault(chave, set()).add(float(m.group(1)))
        else:
            med.setdefault(m.group(3).replace(" ", ""), set()).add(float(m.group(2)))
    return med


def _codigos(titulo):
    """Códigos de modelo/referência ("18056", "vb603", "scf551"): dois códigos diferentes = dois produtos."""
    return {p for p in _palavras_titulo(titulo)
            if len(p) >= 4 and sum(ch.isdigit() for ch in p) >= 3 and not re.fullmatch(r"(19|20)\d\d", p)}


def _medidas_brigam(a, b):
    ma, mb = _medidas(a), _medidas(b)
    if any(ma[u].isdisjoint(mb[u]) for u in ma.keys() & mb.keys()):
        return True
    ca, cb = _codigos(a), _codigos(b)
    return bool(ca and cb and ca.isdisjoint(cb))


def _peso(p):
    if p in _CORES or _raiz(p) in _CORES_R:
        return 0.0
    if p in _COMUNS or _raiz(p) in _COMUNS_R or p.isdigit():
        return 0.3
    return 1.0


def comparar_titulos(a, b):
    """Diz se dois títulos são o mesmo produto, anunciado de jeitos diferentes (21/11).

    - Usa o título inteiro, não só o começo; palavras raras ("caranguejo", "banguela") valem mais que as comuns
      ("brinquedo", "musical"); cor não conta (cor diferente do mesmo produto é o mesmo produto).
    - Medida ou quantidade diferente ("kit 10" x "kit 30", "25cm" x "100cm", "aro 12" x "aro 16") = outro produto.
    - Código de modelo diferente ("1328" x "1342") = outro produto.
    - O "nome" do produto (as duas primeiras palavras raras de um dos títulos) tem de aparecer no outro.
    Devolve {"igual": bool, "nota": 0 a 1, "motivo": str}."""
    wa, wb = [_raiz(p) for p in assinatura(a)], [_raiz(p) for p in assinatura(b)]
    if not wa or not wb:
        return {"igual": False, "nota": 0.0, "motivo": "sem palavras"}
    if _medidas_brigam(a, b):
        return {"igual": False, "nota": 0.0, "motivo": "medida, quantidade ou modelo diferente"}
    vazias = _VAZIAS | {_raiz(p) for p in _VAZIAS}
    pa = {p for p in _palavras_titulo(a) if p not in vazias}
    pb = {p for p in _palavras_titulo(b) if p not in vazias}
    raras_a = [p for p in wa if _peso(p) == 1.0]
    raras_b = [p for p in wb if _peso(p) == 1.0]
    comuns = pa & pb
    peso_comum = sum(_peso(p) for p in comuns)
    peso_a, peso_b = sum(_peso(p) for p in pa), sum(_peso(p) for p in pb)
    nota = peso_comum / min(peso_a, peso_b) if min(peso_a, peso_b) else 0.0
    raras_comuns = sum(1 for p in comuns if _peso(p) == 1.0)
    # O "nome" do produto: as duas primeiras palavras raras de um dos títulos têm de estar no outro
    nome_bate = bool((raras_a and set(raras_a[:2]) <= pb) or (raras_b and set(raras_b[:2]) <= pa))
    # Regra antiga (continua valendo): as 3 primeiras palavras iguais, ou metade das 8 primeiras
    sa, sb = set(wa), set(wb)
    antiga = (len(sa & sb) >= 3 and len(sa & sb) / len(sa | sb) >= 0.5) or (len(wa) >= 3 and wa[:3] == wb[:3])
    if antiga and nome_bate:
        return {"igual": True, "nota": round(max(nota, 0.5), 2), "motivo": "título quase igual"}
    if nome_bate and raras_comuns >= 3 and nota >= 0.6:
        return {"igual": True, "nota": round(nota, 2), "motivo": "mesmas palavras raras"}
    if antiga and raras_comuns >= 2:
        return {"igual": True, "nota": round(max(nota, 0.5), 2), "motivo": "título quase igual"}
    return {"igual": False, "nota": round(nota, 2), "motivo": "títulos diferentes"}
