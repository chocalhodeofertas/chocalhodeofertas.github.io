"""Textos das postagens do Chocalho de Ofertas."""
import html
import random
from urllib.parse import quote

NOME_CANAL = "Chocalho de Ofertas"

# Frases da marca (o chocalho). As que falam de preço caindo só entram quando
# o anúncio mostra o preço "de" (cláusula 5.4: nada além do que o anúncio diz).
ABERTURAS_PRECO = [
    "🪇 O chocalho tocou: preço caiu!",
    "🪇 Chacoalhou o preço!",
    "🪇 Chocalhou, baixou!",
    "🪇 Tchic-tchic: o preço caiu!",
    "🪇 Esse preço fez barulho!",
    "🪇 Balançou o chocalho e o preço desceu",
    "🪇 Ouviu esse barulhinho? É desconto",
    "🪇 Preço chacoalhado, bolso feliz",
    "🪇 Sacudimos o preço pra você",
    "🪇 Chocalhada de desconto!",
]
ABERTURAS = ABERTURAS_PRECO + [
    "👶 Achadinho pro pequeno",
    "🧸 Oferta boa pra família",
    "💛 Pra economizar sem chorar",
    "🪇 Olha o que o chocalho achou",
    "🪇 Chocalho de olho nessa",
]
# Com o produto no meio: "{alvo}" vira "da fralda", "do berço"...
MODELOS_ALVO = [
    "🪇 Chacoalhou o preço {alvo}!",
    "🪇 O preço {alvo} fez barulho!",
    "🪇 Balançou o chocalho e o preço {alvo} caiu",
    "🪇 Tchic-tchic: caiu o preço {alvo}!",
]

# Frases que combinam com O PRODUTO (pelo título). Só clima e uso, nunca
# características técnicas ou promessas (cláusula 5.4). Primeiro que casar vale.
FRASES_PRODUTO = [
    # Acessórios primeiro (o título costuma citar o item "grande" onde eles vão)
    (r"trocador", "do trocador", ["🧷 Pra trocar fralda em qualquer lugar", "🧷 Troca de fralda sem perrengue"]),
    (r"organizador|cesto|porta fralda|porta treco", None, ["🧺 Pra deixar tudo organizado", "🧺 Cada coisa no seu lugar"]),
    (r"mosquiteiro|tela mosquiteira", "do mosquiteiro", ["🦟 Pra deixar os mosquitos longe", "🌙 Soninho sem pernilongo"]),
    (r"bolsa maternidade|mochila maternidade", "da bolsa maternidade",
     ["👜 Pra levar tudo do bebê", "👜 Pra saída da maternidade"]),
    (r"retrovisor", "do retrovisor", ["🚗 Pra ver o bebê no banco de trás", "🚗 Pras voltinhas de carro"]),
    (r"\bmobile\b", "do móbile", ["🌙 Pra olhar lá do berço", "🎵 Pro berço ficar mais divertido"]),
    (r"tapete (de )?atividades|ginasio", "do tapetinho", ["🧸 Pra hora de brincar no chão", "🧸 Pro tempo de barriguinha",
                                                          "🎵 Brincar e descobrir"]),
    (r"kit berco|protetor de berco|lencol (de |para )?berco|edredom infantil", None,
     ["🛏️ Pro berço ficar lindo", "🛏️ Pro enxoval do quarto", "🌙 Pro soninho mais gostoso"]),
    (r"travesseiro", "do travesseiro", ["😴 Pro soninho mais tranquilo", "🌙 Bons sonhos pro pequeno"]),
    (r"colchao", "do colchão", ["🌙 Pro soninho do bebê", "😴 Pra dormir gostoso"]),
    (r"mordedor", "do mordedor", ["🦷 Pra fase dos dentinhos", "🦷 Pros dentinhos que estão chegando"]),
    (r"chocalho", "do chocalho", ["🪇 Chocalho que chacoalha o preço!", "🪇 Pra fazer barulhinho"]),
    (r"termometro", "do termômetro", ["🌡️ Pra ter em casa", "🌡️ Pra farmacinha do bebê"]),
    (r"aspirador nasal|lavagem nasal", None, ["👃 Pra cuidar do narizinho", "👃 Pra farmacinha do bebê"]),
    (r"pomada|assadura", "da pomada", ["🧴 Pro bumbum do bebê", "🧴 Pra deixar no trocador"]),
    (r"shampoo|sabonete|condicionador|hidratante|colonia|locao", None,
     ["🫧 Pra aquele cheirinho de bebê", "🛁 Pra hora do banho", "🫧 Banho gostoso, cheirinho bom"]),
    (r"toalha (de )?banho|roupao", None, ["🛁 Pro pós-banho quentinho", "🧸 Quentinho depois do banho"]),
    (r"lencos? umedecid|toalhas? umedecid", "do lencinho", ["🧻 Lencinho nunca sobra", "🧻 Pra bolsa, pro carro, pro trocador",
                                                          "🧻 Pra ter sempre à mão"]),
    (r"\bfraldas?\b", "da fralda", ["🧷 Estoque de fralda garantido", "🧷 Fralda nunca é demais",
                                     "🧷 Pra quem troca fralda o dia todo", "🧷 Hora de abastecer o estoque"]),
    (r"banheira|kit banho", "da banheira", ["🛁 Pra hora do banho ficar mais fácil", "🛁 Banho gostoso pro pequeno",
                                            "🛁 Pro banho de todo dia"]),
    (r"baba eletronica|baby monitor|camera (de )?bebe", "da babá eletrônica",
     ["👀 Pra ficar de olho no soninho", "🌙 Pra dormir mais tranquila", "👀 Pro olho no bebê, de qualquer cômodo"]),
    (r"cadeirinha de descanso|cadeira de descanso|descanso|balanco|bouncer", "da cadeirinha de descanso",
     ["😴 Pra hora de descansar", "🎵 Balancinho pro bebê relaxar", "😴 Pra ter as mãos livres um pouquinho"]),
    (r"cadeira(s)? de alimentacao|cadeirao", "da cadeira de alimentação",
     ["🥣 Pra hora da papinha", "🥄 Pra introdução alimentar", "🍽️ Pra comer junto com a família"]),
    (r"cadeirinha|bebe conforto|assento elevat|booster|cadeira (de|para) (carro|auto)", "da cadeirinha",
     ["🚗 Pra passear de carro com o pequeno", "🚗 Pras viagens em família", "🚗 Pro banco de trás"]),
    (r"carrinho de bebe|travel system", "do carrinho", ["🚼 Pros passeios com o pequeno", "🌳 Bora passear?",
                                                        "🚼 Pra sair de casa com mais facilidade"]),
    (r"cercadinho|chiqueirinho|cercado", "do cercadinho", ["🧸 Um cantinho só pra brincar", "🧸 Pra brincar no seu cantinho"]),
    (r"\bberco|moises|co sleeper", "do berço", ["🌙 Pro soninho do bebê", "🛏️ Pro cantinho de dormir",
                                                "🌙 Bons sonhos pro pequeno"]),
    (r"\bandador|empurrador|primeiros passos", "do andador", ["👣 Pros primeiros passinhos", "👣 Um passinho de cada vez"]),
    (r"prato|pratinho|talher|colher|babador|copo (de )?transicao", None,
     ["🥣 Pra hora da papinha", "🥄 Pra introdução alimentar", "🍽️ Pra hora de comer"]),
    (r"trava|protetor de tomada|protetor de quina|portao de seguranca", None,
     ["🏠 Pra casa ficar pronta pro pequeno explorar", "🏠 Pra deixar a casa à prova de curiosos"]),
    (r"fantasia", "da fantasia", ["🎭 Pra soltar a imaginação", "🎉 Pra festa à fantasia", "🦸 Pra brincar de ser herói"]),
    (r"piscina|\bboia\b", "da piscina", ["🏊 Pros dias de calor", "☀️ Pra refrescar o verão"]),
    (r"pula pula|cama elastica|trampolim", "do pula-pula", ["🤸 Pra gastar energia", "🤸 Pula, pula, pula!"]),
    (r"triciclo|bicicleta|patinete|motoca|velotrol", None, ["🚲 Pra pedalar por aí", "🚲 Bora dar uma volta?",
                                                          "🛴 Pra gastar energia ao ar livre"]),
    (r"\blego\b|blocos de montar|bloco de montar", "do LEGO", ["🧱 Pra montar e criar", "🧱 Peça por peça, horas de diversão"]),
    (r"\bboneca|\bbebe reborn", "da boneca", ["🎀 Pra brincar de faz de conta", "🎀 Pra cuidar da bonequinha"]),
    (r"cozinha (de )?brinquedo|cozinha infantil|comidinha|panelinha", "da cozinha", ["🍳 Pro chef mirim",
                                                                                     "🍳 Hoje o almoço é por conta deles"]),
    (r"hot wheels|carrinho (de )?controle|controle remoto|pista", None, ["🏎️ Pra acelerar a brincadeira", "🏁 Pra corrida em casa"]),
    (r"dinossauro|\bdino\b", "do dino", ["🦖 Pros fãs de dinossauro", "🦖 Rawr! Pra brincar de aventura"]),
    (r"pelucia|ursinho", "da pelúcia", ["🧸 Pra abraçar na hora de dormir", "🧸 Companheiro de soninho"]),
    (r"quebra cabeca|jogo da memoria|tabuleiro|jogo de cartas|\buno\b|\bstop\b", None,
     ["🎲 Pra brincar em família", "🧩 Pra noite de jogos", "🎲 Bora uma partida?"]),
    (r"montessori|didatico|educativo", None, ["🧠 Brincar e aprender", "🧩 Pra aprender brincando"]),
    (r"massinha|slime|kit pintura|lapis de cor|canetinha|giz de cera", None, ["🖍️ Pra colorir à vontade", "🎨 Pra criar sem parar"]),
    (r"\bps5\b|\bps4\b|playstation|xbox|nintendo|switch|console", None, ["🎮 Pra jogatina em família", "🎮 Diversão garantida"]),
    (r"pokemon", None, ["⚡ Pros colecionadores de Pokémon", "⚡ Temos que pegar!"]),
    (r"figurinha|album", None, ["⚽ Pra completar o álbum", "⭐ Bora trocar figurinha?"]),
    (r"\bmochila|lancheira|estojo|garrafinha", None, ["🎒 Pra volta às aulas", "🎒 Pro material escolar"]),
    (r"\blivro|colorir", None, ["📚 Hora da história", "📖 Pra ler juntinhos"]),
    (r"\bpiano|teclado infantil|guitarra|bateria (infantil|musical)|microfone|xilofone", None,
     ["🎶 Pro pequeno músico", "🎶 Pra fazer um som"]),
    (r"luminaria|luz noturna|abajur", None, ["🌙 Luzinha pro soninho", "🌙 Pro quarto ficar aconchegante"]),
    (r"lixeira", None, ["🧺 Pro trocador ficar organizado", "🏠 Pra deixar a casa em ordem"]),
    (r"\bbody|macacao|macaquinho|pijama|conjunto|vestido|camiseta|short|calca", None,
     ["👶 Look novo pro pequeno", "🧦 Eles crescem rápido, né?", "👕 Pra renovar o guarda-roupa"]),
    (r"tenis|sapato|sandalia|chinelo|pantufa|\bmeias?\b", None, ["👟 Pros pezinhos", "👣 Pros pezinhos que não param"]),
    (r"manta|cobertor", None, ["🧸 Quentinho pro pequeno", "🌙 Pra aconchegar na hora de dormir"]),
]
_FRASES_RE = None


def _frases_do_produto(titulo):
    import re
    from .filtros import normalizar

    global _FRASES_RE
    if _FRASES_RE is None:
        _FRASES_RE = [(re.compile(p), alvo, frases) for p, alvo, frases in FRASES_PRODUTO]
    t = normalizar(titulo)
    # O produto principal costuma vir primeiro no título ("Berço ... com
    # mosquiteiro"): vale o padrão que aparece mais cedo; empate, a ordem da lista.
    melhor = None
    for ordem, (padrao, alvo, frases) in enumerate(_FRASES_RE):
        m = padrao.search(t)
        if m and (melhor is None or (m.start(), ordem) < melhor[0]):
            melhor = ((m.start(), ordem), alvo, frases)
    return (melhor[1], melhor[2]) if melhor else (None, None)


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
    """Frase de abertura que combina com o produto.

    Com produto reconhecido: 55% frase do produto, 30% frase da marca com o
    produto ("Chacoalhou o preço da fralda!"), 15% frase geral da marca.
    Sem produto reconhecido: 60% chamada da categoria, 40% frase da marca.
    Frases de "preço caiu" só quando o anúncio mostra o preço "de".
    """
    tem_de = bool(oferta.preco_de)
    marca = ABERTURAS if tem_de else [a for a in ABERTURAS if a not in ABERTURAS_PRECO]
    alvo, frases = _frases_do_produto(oferta.titulo)
    sorte = rng.random()
    if frases:
        if sorte < 0.55:
            return rng.choice(frases)
        if sorte < 0.85 and alvo and tem_de:
            return rng.choice(MODELOS_ALVO).format(alvo=alvo)
        return rng.choice(marca)
    proprias = CHAMADAS.get(oferta.categoria)
    if proprias and sorte < 0.6:
        return rng.choice(proprias)
    return rng.choice(marca)


def _linhas_preco(oferta, negrito, riscado, codigo=lambda t: t):
    linhas = []
    if oferta.preco_de:
        pct = round(oferta.desconto * 100)
        linhas.append(f"De {riscado(brl(oferta.preco_de))} por {negrito(brl(oferta.preco))} (-{pct}%)")
    elif getattr(oferta, "a_partir", False):
        linhas.append(f"A partir de {negrito(brl(oferta.preco))}")
    else:
        linhas.append(f"Por {negrito(brl(oferta.preco))}")
    if getattr(oferta, "loja", "") == "shopee" and getattr(oferta, "vendas", 0):
        linhas.append(f"⭐ {str(round(oferta.nota, 1)).replace('.', ',')} · {_vendidos(oferta.vendas)}")
    cp = getattr(oferta, "cupom", None)
    if cp and cp.get("origem") == "pagina":
        if cp.get("preco"):
            linhas.append(f"🎟️ Com cupom do anúncio: {negrito(brl(cp['preco']))}*")
        else:
            linhas.append(f"🎟️ Tem cupom de {negrito(cp['desconto'])} no anúncio*")
    elif cp:
        linhas.append(f"🎟️ Com o cupom {codigo(cp['codigo'])}: {negrito(brl(cp['preco']))}*")
    return linhas


def _nota_cupom(oferta):
    if (getattr(oferta, "cupom", None) or {}).get("origem") == "pagina":
        return "*Ative o cupom na página do produto antes de comprar."
    return "*Se o produto for elegível ao cupom. Confira no carrinho antes de pagar."


def _vendidos(n):
    if n >= 1000:
        mil = n // 1000
        return f"+{mil} mil vendidos"
    return f"+{(n // 100) * 100} vendidos"


def _nome_loja(oferta):
    return "na Shopee" if getattr(oferta, "loja", "") == "shopee" else "no Mercado Livre"


def montar_telegram(oferta, rng=random):
    """Legenda em HTML para o canal do Telegram (limite de 1024 caracteres)."""
    emoji = EMOJI_CATEGORIA.get(oferta.categoria, "✨")
    partes = [
        f"<b>{html.escape(_abertura(oferta, rng))}</b>",
        "",
        f"{emoji} {html.escape(_titulo_curto(oferta.titulo))}",
        "",
        *_linhas_preco(oferta, lambda t: f"<b>{t}</b>", lambda t: f"<s>{t}</s>", lambda t: f"<code>{t}</code>"),
        "",
        f'👉 <a href="{html.escape(oferta.link, quote=True)}">Ver oferta {_nome_loja(oferta)}</a>',
        "",
        *([f"<i>{_nota_cupom(oferta)}</i>"] if getattr(oferta, "cupom", None) else []),
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
        f"👉 {getattr(oferta, 'link_wa', None) or oferta.link}",
        "",
        *([f"_{_nota_cupom(oferta)}_"] if getattr(oferta, "cupom", None) else []),
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
