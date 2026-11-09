"""Textos das postagens do Chocalho de Ofertas."""
import html
import random
from urllib.parse import quote

NOME_CANAL = "Chocalho de Ofertas"

ABERTURAS = [
    "🪇 O chocalho tocou: preço caiu!",
    "🪇 Chacoalhou o preço!",
    "👶 Achadinho pro pequeno",
    "🧸 Oferta boa pra família",
    "💛 Pra economizar sem chorar",
]
# Chamadas por categoria: só clima, nunca fatos sobre o produto (cláusula 5.4)
CHAMADAS = {
    "fralda": ["🧷 Hora de abastecer o estoque de fraldas!", "🧷 Fralda com preço bom", "🧷 Pra quem troca fralda o dia todo"],
    "higiene": ["🛁 Pra hora do banho", "🫧 Cuidado com o bebê, economia pra família", "🛁 Pro kit de higiene do pequeno"],
    "roupa": ["👕 Look novo pro pequeno", "👗 Pra renovar o guarda-roupa dos pequenos", "🧦 Eles crescem rápido, né?"],
    "brinquedo": ["🧸 Pra brincar muito", "🎁 Ideia de presente", "🪀 Diversão pros pequenos"],
    "jogo": ["🎲 Pra brincar em família", "🧩 Pra animar a brincadeira", "🎁 Ideia de presente"],
    "quarto": ["🛏️ Pro cantinho do bebê", "🌙 Pro quarto do pequeno", "🧸 Pra deixar o quarto do bebê pronto"],
    "passeio": ["🚼 Pros passeios com o pequeno", "🚗 Pros passeios em família", "🌳 Bora passear?"],
    "alimentacao": ["🥣 Pra hora da papinha", "🍽️ Pra hora de comer", "🥄 Pra introdução alimentar"],
    "gestante": ["🤰 Pra mamãe que tá esperando", "💕 Pra gestação mais confortável", "🤰 Pro enxoval que tá chegando"],
    "game": ["🎮 Pra jogar em família", "🎮 Diversão garantida", "🎁 Ideia de presente"],
    "livro": ["📚 Hora da leitura", "📖 Pra ler juntinhos", "📚 Pra estante dos pequenos"],
    "escola": ["✏️ Pro material escolar", "🎒 Pra volta às aulas", "🖍️ Pra desenhar e criar"],
    "esporte": ["⚽ Pra gastar energia", "🏊 Pra brincar ao ar livre", "🚲 Bora se mexer?"],
    "casa": ["🏠 Pro cantinho dos pequenos", "🌙 Pro quarto das crianças", "🧺 Pra organizar a casa"],
    "festa": ["🎉 Pra festa ficar linda", "🎈 Pro aniversário", "🎁 Pra comemorar"],
}

# Cláusula 5.4 dos termos: só informações que estão no anúncio. Por isso não
# afirmamos "menor preço" nem "% abaixo do habitual" (são cálculos nossos).

EMOJI_CATEGORIA = {
    "fralda": "🧷",
    "higiene": "🛁",
    "roupa": "👕",
    "brinquedo": "🧸",
    "jogo": "🎲",
    "quarto": "🛏️",
    "passeio": "🚼",
    "alimentacao": "🥣",
    "gestante": "🤰",
    "game": "🎮",
    "livro": "📚",
    "escola": "✏️",
    "esporte": "⚽",
    "casa": "🏠",
    "festa": "🎉",
}


def brl(valor):
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _titulo_curto(titulo, limite=110):
    titulo = " ".join((titulo or "").split())
    return titulo if len(titulo) <= limite else titulo[: limite - 1].rstrip() + "…"


def _abertura(oferta, rng):
    """70% das vezes uma chamada da categoria, 30% uma chamada geral do canal."""
    proprias = CHAMADAS.get(oferta.categoria)
    if proprias and rng.random() < 0.7:
        return rng.choice(proprias)
    return rng.choice(ABERTURAS)


def _linhas_preco(oferta, negrito, riscado):
    linhas = []
    if oferta.preco_de:
        pct = round(oferta.desconto * 100)
        linhas.append(f"De {riscado(brl(oferta.preco_de))} por {negrito(brl(oferta.preco))} (-{pct}%)")
    else:
        linhas.append(f"Por {negrito(brl(oferta.preco))}")
    return linhas


def montar_telegram(oferta, rng=random):
    """Legenda em HTML para o canal do Telegram (limite de 1024 caracteres)."""
    emoji = EMOJI_CATEGORIA.get(oferta.categoria, "✨")
    partes = [
        f"<b>{html.escape(_abertura(oferta, rng))}</b>",
        "",
        f"{emoji} {html.escape(_titulo_curto(oferta.titulo))}",
        "",
        *_linhas_preco(oferta, lambda t: f"<b>{t}</b>", lambda t: f"<s>{t}</s>"),
        "",
        f'👉 <a href="{html.escape(oferta.link, quote=True)}">Ver oferta no Mercado Livre</a>',
        "",
        "<i>Preço e estoque podem mudar a qualquer momento. #publi · link de afiliado</i>",
    ]
    return "\n".join(partes)[:1024]


def montar_whatsapp(oferta, rng=random):
    """Mesmo conteúdo, no formato do WhatsApp (para copiar e colar)."""
    emoji = EMOJI_CATEGORIA.get(oferta.categoria, "✨")
    partes = [
        f"*{_abertura(oferta, rng)}*",
        "",
        f"{emoji} {_titulo_curto(oferta.titulo)}",
        "",
        *_linhas_preco(oferta, lambda t: f"*{t}*", lambda t: f"~{t}~"),
        "",
        f"👉 {oferta.link}",
        "",
        "_Preço e estoque podem mudar a qualquer momento. #publi · link de afiliado_",
    ]
    return "\n".join(partes)


def montar_x(oferta):
    """Versão curta para o X (até 280 caracteres; o link conta como 23)."""
    if oferta.preco_de:
        preco = f"De {brl(oferta.preco_de)} por {brl(oferta.preco)} (-{round(oferta.desconto * 100)}%)"
    else:
        preco = f"Por {brl(oferta.preco)}"
    meio = f"\n{preco} #publi\n👉 "
    # O X conta todo link como 23 caracteres e emojis como 2; sobra folga de 5
    espaco = 280 - 23 - len(meio) - 3 - 2 - 5
    return "🪇 " + _titulo_curto(oferta.titulo, max(espaco, 40)) + meio + oferta.link


def botoes_compartilhar(texto_whatsapp, texto_x):
    """Links que já abrem o WhatsApp e o X com a mensagem pronta."""
    return [
        ("📲 Compartilhar no WhatsApp", "https://api.whatsapp.com/send?text=" + quote(texto_whatsapp)),
        ("✖️ Postar no X", "https://x.com/intent/tweet?text=" + quote(texto_x)),
    ]
