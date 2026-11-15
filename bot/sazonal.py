"""Calendário do ano: o que as famílias procuram em cada época ganha prioridade.

Não muda o que é oferta (as regras de desconto continuam as mesmas); só a ordem da fila:
produto da época sobe um pouco na pontuação do Mercado Livre e da Shopee, e a busca da Shopee
ganha uma palavra-chave da época por rodada.
"""
import re
from datetime import date, timedelta

from .filtros import normalizar

_BRINQUEDO = (r"\b(brinquedos?|bonecas?|bonecos?|lego|blocos? de montar|pelucia|hot wheels|barbie|quebra cabeca|"
              r"jogos? (de|da) (tabuleiro|memoria|cartas|montar|encaixe)|jogos? (infantil|educativo)|playset|"
              r"dinossauro|massinha|slime|patinete|bicicleta|triciclo|motoca|casinha|"
              r"cozinha infantil|controle remoto|pula pula|kit pintura)")


def pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return date(ano, mes, dia)


def carnaval(ano):
    """Terça-feira de Carnaval: 47 dias antes da Páscoa."""
    return pascoa(ano) - timedelta(days=47)


def _fixo(mes_ini, dia_ini, mes_fim, dia_fim):
    """Período com datas fixas; pode virar o ano (ex.: 26/12 a 20/02)."""
    def dentro(hoje):
        ini, fim, d = (mes_ini, dia_ini), (mes_fim, dia_fim), (hoje.month, hoje.day)
        return ini <= d <= fim if ini <= fim else (d >= ini or d <= fim)
    return dentro


def _ate_carnaval(hoje):
    fim = carnaval(hoje.year)
    return fim - timedelta(days=25) <= hoje <= fim


def _ate_pascoa(hoje):
    fim = pascoa(hoje.year)
    return fim - timedelta(days=21) <= hoje <= fim


# (nome, quando, padrão no título, categorias, peso, palavras-chave para a busca da Shopee)
EPOCAS = [
    ("Natal", _fixo(11, 15, 12, 24), _BRINQUEDO + r"|\b(natal|natalin\w+|papai noel|presente)", {"brinquedo", "jogo"}, 1.2,
     ["presente infantil natal", "pijama natal infantil", "roupa natal bebê"]),
    ("volta às aulas", _fixo(12, 26, 2, 20),
     r"\b(mochilas?|lancheiras?|estojos?|escolar|cadernos?|lapis|canetinhas?|giz de cera|garrafinha|squeeze|uniforme|"
     r"apontador|borracha|tesoura sem ponta|agenda)", {"escola"}, 1.35,
     ["mochila infantil", "lancheira infantil", "kit escolar infantil", "estojo infantil", "garrafinha infantil"]),
    ("verão", _fixo(12, 1, 3, 10),
     r"\b(piscinas?|boias?|protetor solar|maio|sunga|biquini|praia|roupa de banho|oculos de sol|chapeu|"
     r"fralda de piscina|baldinho|guarda sol|ventilador|repelente|camiseta uv|protecao uv)", set(), 1.2,
     ["piscina infantil", "boia infantil", "roupa de banho infantil", "brinquedo de praia"]),
    ("Carnaval", _ate_carnaval, r"\b(fantasias?|carnaval|tiara|tutu|mascara infantil|confete|serpentina)", {"festa"}, 1.3,
     ["fantasia infantil", "fantasia carnaval bebê"]),
    ("Páscoa", _ate_pascoa, r"\b(pascoa|coelh\w+|orelhas? de coelho)", set(), 1.2,
     ["fantasia coelho infantil", "pelúcia coelho"]),
    ("inverno", _fixo(5, 1, 8, 15),
     r"\b(casacos?|jaquetas?|moletom|pijama|mantas?|cobertor|touca|luvas?|meias?|botas?|flanel\w*|soft|plush|"
     r"macacao|saco de dormir|umidificador|cachecol)", set(), 1.2,
     ["pijama infantil inverno", "casaco infantil", "manta bebê", "macacão bebê inverno"]),
    ("festa junina", _fixo(5, 20, 6, 30), r"\b(festa junina|junin\w+|caipira|chapeu de palha|sao joao)", set(), 1.3,
     ["roupa festa junina infantil", "vestido festa junina infantil"]),
    ("Dia das Crianças", _fixo(9, 15, 10, 12), _BRINQUEDO + r"|\b(presente)", {"brinquedo", "jogo"}, 1.3,
     ["brinquedo dia das crianças", "boneca", "carrinho brinquedo", "blocos de montar"]),
    ("Halloween", _fixo(10, 13, 10, 31), r"\b(halloween|fantasias?|bruxa|abobora|vampiro|esqueleto)", {"festa"}, 1.25,
     ["fantasia halloween infantil"]),
]
_COMPILADAS = [(n, q, re.compile(p), cats, peso, termos) for n, q, p, cats, peso, termos in EPOCAS]


def _dia(agora):
    return agora.date() if hasattr(agora, "date") else agora


def epocas(agora):
    """Nomes das épocas em vigor na data."""
    hoje = _dia(agora)
    return [n for n, quando, *_ in _COMPILADAS if quando(hoje)]


def peso(titulo, agora, categoria=""):
    """Multiplicador da pontuação: maior que 1 quando o produto combina com uma época em vigor.
    Se combinar com mais de uma, vale a maior (não acumula)."""
    if agora is None:
        return 1.0
    hoje, t, melhor = _dia(agora), None, 1.0
    for _, quando, padrao, cats, valor, _ in _COMPILADAS:
        if valor <= melhor or not quando(hoje):
            continue
        t = normalizar(titulo) if t is None else t
        if (categoria and categoria in cats) or padrao.search(t):
            melhor = valor
    return melhor


def termos_shopee(agora):
    """Palavras-chave da época para a busca da Shopee (lista vazia fora de época)."""
    hoje, saida = _dia(agora), []
    for _, quando, _, _, _, termos in _COMPILADAS:
        if quando(hoje):
            saida += [t for t in termos if t not in saida]
    return saida
