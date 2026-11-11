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
_REGRAS.append(("Fora do nicho (marca adulta)", r"\bnew era\b"))
_REGRAS.append(("Possível réplica", r"\b(replica|tailandesa|1a linha|primeira linha|1 linha)\b"))
_COMPILADAS = [(motivo, re.compile(p)) for motivo, p in _REGRAS]


def motivo_bloqueio(*textos: str):
    """Retorna o motivo do bloqueio, ou None se o produto pode ser divulgado."""
    alvo = " ".join(normalizar(t) for t in textos if t)
    # "bicos" de aspirador nasal não são bicos de mamadeira
    alvo = re.sub(r"(aspirador nasal.*?)\bbicos?\b", r"\1", alvo)
    for motivo, padrao in _COMPILADAS:
        if padrao.search(alvo):
            return motivo
    return None


_INFANTIL = re.compile(
    r"\b(infantil|infantis|infanto|infantojuvenil|crianca|criancas|kids|kid|bebe|bebes|baby|juvenil|"
    r"menino|meninos|menina|meninas|junior|escolar|aro (12|14|16|20)|"
    r"pokemon|patrulha canina|turma da monica|peppa|bluey|frozen|homem aranha|minecraft|"
    r"colorir|livro de atividades|historinhas?|conto de fadas|diario de um banana)\b"
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
    r"panela de pressao|aspirador de po)\b"
)
# "Casal" só é problema quando o item não é de bebê (berço acoplado à cama de casal pode)
_CASAL = re.compile(r"\bcasal\b")
_ITEM_DE_BEBE = re.compile(r"\b(berco|co ?sleeper|moises|bebe conforto|carrinho|cadeirinha|trocador|fralda)")


# Boné, chapéu e afins: quase sempre adulto. Só passa com sinal claro de criança ("juvenil" não basta)
_ACESSORIO_CABECA = re.compile(r"\b(bones?|chapeus?|viseiras?|bucket|toucas?|gorros?)\b")
_CRIANCA_CLARO = re.compile(r"\b(infantil|infantis|crianca|criancas|kids|kid|bebe|bebes|baby|menino|meninos|menina|meninas)\b")


def fora_da_faixa(titulo, categoria, regra=None):
    """Motivo para pular produtos que não são do universo infantil (ou None).

    Vale para tudo (itens de casa/adulto que vazam das categorias de bebê) e,
    nas áreas novas, exige sinal de produto infantil no título."""
    t = normalizar(titulo)
    if _ACESSORIO_CABECA.search(t) and not _CRIANCA_CLARO.search(t):
        return "boné/chapéu sem ser infantil"
    if not _INFANTIL.search(t):
        if _CASA_ADULTO.search(t) or (_CASAL.search(t) and not _ITEM_DE_BEBE.search(t)):
            return "item de casa/adulto (fora do nicho)"
    if regra == "game" or categoria == "game":
        if _GAMES_FORA.search(t) or not _GAMES_OK.search(t):
            return "game fora da lista infantil"
    elif regra in ("infantil", True) and not _INFANTIL.search(t):
        return "não parece infantil"
    return None
