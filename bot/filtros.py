"""Filtro de produtos que o canal NÃO divulga.

- NBCAL (Lei 11.265/2006): proíbe promoção comercial de fórmulas infantis,
  mamadeiras, bicos, chupetas e protetores de mamilo. Leites e fórmulas para
  crianças maiores também ficam de fora para simplificar.
- Medicamentos e suplementos: propaganda regulada pela Anvisa.

O filtro olha o título do produto e o endereço dele. Na dúvida, bloqueia.
"""
import re
import unicodedata


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparar com segurança."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().replace("-", " ").replace("_", " ")


# (motivo, padrão) — os padrões são aplicados no texto normalizado
_REGRAS = [
    ("NBCAL: mamadeira", r"\bmamadeiras?\b"),
    ("NBCAL: bico", r"\bbicos?\b"),
    ("NBCAL: chupeta", r"\bchupetas?\b"),
    ("NBCAL: protetor de mamilo", r"\bmamilos?\b"),
    ("NBCAL: fórmula infantil", r"\bformulas?\b"),
    ("NBCAL: leite", r"\bleites?\b|\bcomposto lacteo\b|\blacteo\b"),
    (
        "NBCAL: marca de fórmula/leite",
        r"\b(nan|aptamil|nestogeno|milnutri|enfamil|similac|nutrilon|"
        r"ninho|neocate|pregomin|alfare|fortini|pediasure|sustagen)\b",
    ),
    (
        "Medicamento",
        r"\b(remedios?|medicamentos?|xaropes?|antitermicos?|antibioticos?|"
        r"paracetamol|dipirona|ibuprofeno|simeticona|soro fisiologico)\b",
    ),
    (
        "Suplemento",
        r"\b(suplementos?|vitaminas?|polivitaminicos?|multivitaminicos?|"
        r"omega ?3|probioticos?|colageno|whey)\b",
    ),
]
_REGRAS.append((
    "Fora do nicho (adulto)",
    r"\b(sinuca|bilhar|snooker|taco de (sinuca|bilhar)|poker|truco|cassino|roleta|dardos?|airsoft|"
    r"paintball|narguile|tabacaria|cerveja|vinhos?|whisky|vodka|erotic[oa]s?|sex shop|adult[oa]s? \+?18)\b",
))
_REGRAS.append((
    "Classificação acima de 14 anos",
    r"(\+ ?18|\b18 anos|\b16 anos|\badult[oa]s?\b|\bterror\b|\bhorror\b|\bgta\b|grand theft|call of duty|"
    r"mortal kombat|resident evil|the last of us|god of war|elden ring|battlefield|dead space|dead island|"
    r"silent hill|\bdoom\b|outlast|assassin.?s creed)",
))
_REGRAS.append(("Fora do nicho (sutiã/lingerie)", r"\b(sutias?|sutien|lingeries?)\b"))
_REGRAS.append(("Fora do nicho (geriátrico/incontinência)",
                r"\b(geriatric[oa]s?|incontinencias?|bigfral|tena|plenitud|confort ?master|usefral)\b"))
_REGRAS.append(("Fora do nicho (marca adulta)", r"\bnew era\b"))
_REGRAS.append(("Possível réplica", r"\b(replica|tailandesa|1a linha|primeira linha|1 linha)\b"))
_COMPILADAS = [(motivo, re.compile(p)) for motivo, p in _REGRAS]


# Palavras que o dono do canal bloqueou pelo Telegram ("bloquear baby doll")
_EXTRAS = []


def definir_bloqueios(palavras):
    """Carrega as palavras bloqueadas pelo admin (guardadas em estado["bloqueados"])."""
    _EXTRAS[:] = [(p, re.compile(r"\b" + re.escape(normalizar(p)).replace(r"\ ", r"\s+") + r"s?\b"))
                  for p in (palavras or []) if normalizar(p).strip()]


def motivo_bloqueio(*textos: str):
    """Retorna o motivo do bloqueio, ou None se o produto pode ser divulgado."""
    alvo = " ".join(normalizar(t) for t in textos if t)
    # "bicos" de aspirador nasal não são bicos de mamadeira
    alvo = re.sub(r"(aspirador nasal.*?)\bbicos?\b", r"\1", alvo)
    for motivo, padrao in _COMPILADAS:
        if padrao.search(alvo):
            return motivo
    for palavra, padrao in _EXTRAS:
        if padrao.search(alvo):
            return f"bloqueado por você: {palavra}"
    return None


_INFANTIL = re.compile(
    r"\b(infantil|infantis|infanto|infantojuvenil|crianca|criancas|kids|kid|bebe|bebes|baby|juvenil|"
    r"menino|meninos|menina|meninas|junior|escolar|aro (12|14|16|20)|"
    r"pokemon|patrulha canina|turma da monica|peppa|bluey|frozen|homem aranha|minecraft|"
    r"colorir|livro de atividades|historinhas?|conto de fadas|diario de um banana|"
    r"fraldas?|enxoval|maternidade|berco|lencos? umedecidos?|assaduras?|barbie|hot wheels|lego|bonecas?)\b"
)
# Games: só o que é do universo infantil/familiar (fone, cadeira gamer etc. ficam de fora)
_GAMES_OK = re.compile(
    r"\b(nintendo|switch|pokemon|mario|minecraft|lego|sonic|kirby|zelda|game ?boy|roblox|just dance|"
    r"yu.?gi.?oh|beyblade|fifa|ea sports fc|playstation ?5?|ps5|ps4|xbox series)\b"
)
_GAMES_FORA = re.compile(r"\b(headset|fone|cadeira|microfone|mouse|teclado|monitor|gift ?card|cartao pre)")


# Itens de casa/adulto que às vezes aparecem dentro das categorias de bebê
# (ex.: extensor de torneira em "Higiene", lençol queen em "Quarto").
_CASA_ADULTO = re.compile(
    r"\b(torneira|pia|queen|king|hotel|spa|gelo|passaros|pombos|morcegos|mantimentos?|churrasqueira|"
    r"furadeira|parafusadeira|ferramentas?|pneus?|notebook|smartphone|air ?fryer|cafeteira|"
    r"panela de pressao|aspirador de po|escritorio|igreja|idosos?|marmitex|marmitas?|academia)\b"
)
# "Casal"/"solteiro" só é problema quando o item não é de bebê nem diz que é infantil
# (berço acoplado à cama de casal e jogo de cama solteiro infantil podem)
_CASAL = re.compile(r"\b(casal|solteiro|solteirao|viuva)\b")  # tamanhos de cama de adulto
_ITEM_DE_BEBE = re.compile(r"\b(berco|co ?sleeper|moises|bebe conforto|carrinho|cadeirinha|trocador|fralda)")


# Boné, chapéu e afins: quase sempre adulto. Só passa com sinal claro de criança ("juvenil" não basta)
_ACESSORIO_CABECA = re.compile(r"\b(bones?|chapeus?|viseiras?|bucket|toucas?|gorros?)\b")
_CRIANCA_CLARO = re.compile(r"\b(infantil|infantis|crianca|criancas|kids|kid|bebe|bebes|baby|menino|meninos|menina|meninas)\b")


# "Baby" que não é bebê: peças de roupa adulta com "baby" no nome
_BABY_ADULTO = re.compile(r"\b(baby ?doll|short ?doll|baby ?look)\b")
# Sinais de roupa/item adulto: só passa com sinal claro de criança
_ADULTO = re.compile(r"\b(adultos?|plus size|sem bojo|com bojo|bojo|sensual|sexy|fita up|tapa seios?|"
                    r"(protetor|adesivo)e?s? (de|para) seios? (de )?silicone)\b")


# Cosmético e cabelo de adulto que vazam da categoria de higiene do bebê
_COSMETICO_ADULTO = re.compile(r"\b(men|anticaspa|antiqueda|barba|pos barba|desodorantes?|antitranspirante|tintura|"
                               r"coloracao|progressiva|alisamento|maquiagem|batom|rimel)\b")
_CABELO = re.compile(r"\b(shampoo|xampu|condicionador|leave ?in|creme (de|para) pentear|mascara capilar)\b")
_MARCA_BEBE = re.compile(r"\b(mustela|johnsons?|granado|pom pom|xuxinha|tra la la|galinha pintadinha|huggies|pampers|"
                         r"baruel|weleda|natura mamae|cetaphil baby|dove baby)\b")
# Produto para animais (ex.: "fralda para cachorra"): "para" + bicho, para não barrar pelúcia de cachorro nem Patrulha Canina
_PARA_ANIMAL = re.compile(r"\b(para|pra|p) (cachorr[oa]s?|caes|cao|gatos?|pets?|animais)\b|\b(cio|racao|tapete higienico)\b")
# Material de artesanato (novelo, fio) que aparece entre os brinquedos
_ARTESANATO = re.compile(r"\b(novelos?|barbante|fio (de )?malha|linha (de|para) croche|chenille)\b")


def fora_da_faixa(titulo, categoria, regra=None):
    """Motivo para pular produtos que não são do universo infantil (ou None).

    Vale para tudo (itens de casa/adulto que vazam das categorias de bebê) e,
    nas áreas novas, exige sinal de produto infantil no título."""
    t = _BABY_ADULTO.sub(" ", normalizar(titulo))
    if _ADULTO.search(t) and not _CRIANCA_CLARO.search(t):
        return "roupa/item adulto"
    if _ACESSORIO_CABECA.search(t) and not _CRIANCA_CLARO.search(t):
        return "boné/chapéu sem ser infantil"
    if _PARA_ANIMAL.search(t):
        return "produto para animais"
    if _COSMETICO_ADULTO.search(t) and not _CRIANCA_CLARO.search(t):
        return "cosmético de adulto"
    if not _INFANTIL.search(t):
        if _CASA_ADULTO.search(t) or (_CASAL.search(t) and not _ITEM_DE_BEBE.search(t)):
            return "item de casa/adulto (fora do nicho)"
        if _CABELO.search(t) and not _MARCA_BEBE.search(t):
            return "produto de cabelo sem ser infantil"
        if _ARTESANATO.search(t):
            return "material de artesanato"
    if regra == "game" or categoria == "game":
        if _GAMES_FORA.search(t) or not _GAMES_OK.search(t):
            return "game fora da lista infantil"
    elif regra in ("infantil", True) and not _INFANTIL.search(t):
        return "não parece infantil"
    return None
