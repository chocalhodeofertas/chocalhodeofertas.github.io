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
ABERTURA_HISTORICO = "📉 Menor preço que a gente já viu!"

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
}


def brl(valor):
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _titulo_curto(titulo, limite=110):
    titulo = " ".join((titulo or "").split())
    return titulo if len(titulo) <= limite else titulo[: limite - 1].rstrip() + "…"


def _abertura(oferta, rng):
    return ABERTURA_HISTORICO if oferta.menor_preco_historico else rng.choice(ABERTURAS)


def _linhas_preco(oferta, negrito, riscado):
    linhas = []
    if oferta.preco_de:
        pct = round(oferta.desconto * 100)
        linhas.append(f"De {riscado(brl(oferta.preco_de))} por {negrito(brl(oferta.preco))} (-{pct}%)")
    else:
        linhas.append(f"Por {negrito(brl(oferta.preco))}")
        if oferta.abaixo_do_habitual:
            linhas.append(f"📉 {round(oferta.abaixo_do_habitual * 100)}% abaixo do preço habitual")
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
        "<i>Preço e estoque podem mudar a qualquer momento.</i>",
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
        "_Preço e estoque podem mudar a qualquer momento._",
    ]
    return "\n".join(partes)


def montar_x(oferta):
    """Versão curta para o X (até 280 caracteres; o link conta como 23)."""
    if oferta.preco_de:
        preco = f"De {brl(oferta.preco_de)} por {brl(oferta.preco)} (-{round(oferta.desconto * 100)}%)"
    else:
        preco = f"Por {brl(oferta.preco)}"
    meio = f"\n{preco}\n👉 "
    # O X conta todo link como 23 caracteres e emojis como 2; sobra folga de 5
    espaco = 280 - 23 - len(meio) - 3 - 2 - 5
    return "🪇 " + _titulo_curto(oferta.titulo, max(espaco, 40)) + meio + oferta.link


def botoes_compartilhar(texto_whatsapp, texto_x):
    """Links que já abrem o WhatsApp e o X com a mensagem pronta."""
    return [
        ("📲 Compartilhar no WhatsApp", "https://api.whatsapp.com/send?text=" + quote(texto_whatsapp)),
        ("✖️ Postar no X", "https://x.com/intent/tweet?text=" + quote(texto_x)),
    ]
