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
    r"\b(infantil|infantis|crianca|criancas|kids|kid|bebe|baby|juvenil|menino|menina|junior|escolar|"
    r"aro (12|14|16|20)|tamanho (2|4|6|8|10|12|14)\b|pokemon|nintendo|lego|disney|patrulha canina|turma da monica)\b"
)
_GAMES_OK = re.compile(
    r"\b(nintendo|switch|pokemon|mario|minecraft|lego|sonic|kirby|zelda|game ?boy|roblox|just dance|"
    r"album|figurinhas?|panini|yu.?gi.?oh|beyblade|"
    r"fifa|ea sports fc|playstation|ps5|ps4|xbox|controle|joystick|headset|infantil|kids)\b"
)


def fora_da_faixa(titulo, categoria, exige_infantil=False):
    """Motivo para pular produtos das áreas novas que não são do universo infantil (ou None)."""
    t = normalizar(titulo)
    if categoria == "game" and not _GAMES_OK.search(t):
        return "game fora da lista infantil"
    if exige_infantil and not _INFANTIL.search(t):
        return "não parece infantil"
    return None
