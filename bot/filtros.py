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
_COMPILADAS = [(motivo, re.compile(p)) for motivo, p in _REGRAS]


def motivo_bloqueio(*textos: str):
    """Retorna o motivo do bloqueio, ou None se o produto pode ser divulgado."""
    alvo = " ".join(normalizar(t) for t in textos if t)
    for motivo, padrao in _COMPILADAS:
        if padrao.search(alvo):
            return motivo
    return None
