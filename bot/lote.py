"""Links oficiais (meli.la) pelo Linkbuilder do painel de afiliados, em lote.

1. Uma vez por dia, o bot manda no privado um bloco com as URLs das melhores
   ofertas que ainda não têm link oficial.
2. Você cola o bloco no Linkbuilder, clica em Gerar e manda os links de volta.
3. O bot associa os links na mesma ordem e guarda para sempre.
"""
import html
import re

LINKBUILDER = "https://www.mercadolivre.com.br/afiliados/linkbuilder"
RE_MELI = re.compile(r"https?://meli\.la/[A-Za-z0-9]+")
PESO_CATEGORIA = {"roupa": 1.3}  # roupa paga 16% de comissão, a maioria 12%


def url_linkbuilder(item_id):
    """Endereço de anúncio, que é o formato que o Linkbuilder aceita."""
    return f"https://produto.mercadolivre.com.br/MLB-{item_id[3:]}-produto-_JM"


def prioridade(oferta, posicao=None):
    from .ofertas import pontuacao

    return pontuacao(oferta, posicao)


def montar_lote(estado, sem_link, tamanho, agora):
    pos = {pid: d.get("pos") for pid, d in estado.get("descobertos", {}).items()}
    """sem_link: lista de (oferta, item_id). Grava o lote pendente e devolve as URLs."""
    escolhidas, vistos = [], set()
    for o, item in sorted(sem_link, key=lambda x: prioridade(x[0], pos.get(x[0].id)), reverse=True):
        if o.id in vistos or o.id in estado["links"] or not item:
            continue
        vistos.add(o.id)
        escolhidas.append((o.id, url_linkbuilder(item)))
        if len(escolhidas) >= tamanho:
            break
    if not escolhidas:
        return []
    estado["lote"] = {
        "dia": agora.date().isoformat(),
        "ids": [pid for pid, _ in escolhidas],
        "urls": [u for _, u in escolhidas],
    }
    return [u for _, u in escolhidas]


def texto_lote(urls, numero=1, total=1):
    return (
        f"🔗 <b>Lote {numero} de até {total} hoje: {len(urls)} ofertas sem link oficial</b>\n\n"
        f"1. Toque no bloco abaixo para copiar\n"
        f'2. Abra o <a href="{LINKBUILDER}">Linkbuilder</a>, cole e toque em <b>Gerar</b>\n'
        f"3. Copie todos os links gerados e mande aqui, numa mensagem só\n\n"
        f"<pre>{html.escape(chr(10).join(urls))}</pre>"
    )


def aplicar_resposta(estado, texto):
    """Associa os meli.la do texto ao lote pendente. Retorna (ok, mensagem)."""
    links = RE_MELI.findall(texto or "")
    lote = estado.get("lote")
    if not links:
        return False, None
    if not lote:
        return False, "Recebi links, mas não há nenhum lote pendente."
    if len(links) != len(lote["ids"]):
        return False, (
            f"⚠️ Recebi {len(links)} links, mas o lote tem {len(lote['ids'])} produtos. "
            "Para não trocar um produto pelo outro, não salvei nada. "
            "Gere de novo com o bloco inteiro e mande todos os links juntos."
        )
    for pid, link in zip(lote["ids"], links):
        estado["links"][pid] = link
    estado["lote"] = None
    return True, (f"✅ {len(links)} links oficiais salvos ({len(estado['links'])} no total)! "
                  "Começo a postar nas próximas rodadas. Se ainda houver lote hoje, ele chega em até 20 min.")
