from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import json
import random

import pytest

from bot import estado as est
from bot import mensagens
from bot.filtros import motivo_bloqueio
from bot.main import Config, Produto, carregar_produtos, rodar
from bot.mercadolivre import AcessoNegado, InfoProduto, MercadoLivre, extrair_id
from bot.ofertas import avaliar

FUSO = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 11, 5, 15, 0, tzinfo=FUSO)


# ---------- links ----------

@pytest.mark.parametrize(
    "link,esperado",
    [
        ("https://produto.mercadolivre.com.br/MLB-1234567890-fralda-pampers-_JM", ("item", "MLB1234567890")),
        ("https://www.mercadolivre.com.br/fralda-huggies/p/MLB19876543", ("catalogo", "MLB19876543")),
        ("https://www.mercadolivre.com.br/x/p/MLB19876543?wid=MLB5555555555&sid=y", ("item", "MLB5555555555")),
        ("MLB1234567890", ("item", "MLB1234567890")),
    ],
)
def test_extrair_id(link, esperado):
    assert extrair_id(link) == esperado


def test_extrair_id_invalido():
    with pytest.raises(ValueError):
        extrair_id("https://meli.la/abc")


# ---------- filtros ----------

@pytest.mark.parametrize(
    "titulo",
    [
        "Kit Mamadeira Avent 260ml",
        "Chupeta Nuk Silicone Tam 2",
        "Bico de Silicone Para Mamadeira",
        "Protetor de Mamilo Medela",
        "Fórmula Infantil Aptamil 800g",
        "Composto Lácteo Ninho Fases",
        "Leite em pó NAN Supreme",
        "Vitamina D Gotas Infantil",
        "Xarope Infantil Tosse",
        "Suplemento Infantil Pediasure",
    ],
)
def test_bloqueia(titulo):
    assert motivo_bloqueio(titulo)


@pytest.mark.parametrize(
    "titulo",
    [
        "Fralda Pampers Confort Sec G 92 unidades",
        "Lenço Umedecido Huggies 4 pacotes",
        "Copo de Transição com Alça 300ml",
        "Carrinho de Bebê Travel System",
        "Bicicleta Infantil Aro 16",
        "Body Bebê Manga Longa Kit 5",
        "Babador Silicone Pega Migalha",
        "Aspirador Nasal Manual Buba Com Estojo 2 Bicos",
    ],
)
def test_libera(titulo):
    assert motivo_bloqueio(titulo) is None


# ---------- planilha ----------

def test_carregar_produtos(tmp_path):
    arq = tmp_path / "produtos.csv"
    arq.write_text(
        "# comentário\n"
        "link_produto,link_afiliado,categoria,preco_referencia\n"
        "https://produto.mercadolivre.com.br/MLB-111111111-fralda-_JM,https://meli.la/a,fralda,\"1.299,90\"\n"
        "https://produto.mercadolivre.com.br/MLB-222222222-chupeta-nuk-_JM,https://meli.la/b,outros,\n"
        "https://produto.mercadolivre.com.br/MLB-333333333-body-_JM,,roupa,\n"
        "https://produto.mercadolivre.com.br/MLB-444444444-body-_JM,https://meli.la/d,Roupa,49.90\n"
        "https://produto.mercadolivre.com.br/MLB-111111111-fralda-_JM,https://meli.la/a,fralda,\n",
        encoding="utf-8",
    )
    produtos, avisos = carregar_produtos(arq)
    assert [p.id for p in produtos] == ["MLB111111111", "MLB333333333", "MLB444444444"]
    assert produtos[0].preco_referencia == 1299.90
    assert produtos[2].preco_referencia == 49.90
    assert produtos[2].categoria == "roupa"
    assert produtos[1].link_afiliado == ""  # será montado automaticamente
    assert len(avisos) == 2  # chupeta, repetido


# ---------- avaliação ----------

def prod(pid="MLB1", ref=None):
    return Produto(pid, "item", "x", "https://meli.la/a", "fralda", ref, 2)


def info(preco, original=None, pid="MLB1"):
    # título diferente por produto (o bot não repete o mesmo tipo de produto no dia)
    nome = "".join(chr(97 + int(c)) for c in pid if c.isdigit()) or "item"
    return InfoProduto(pid, f"{nome.capitalize()}{nome}{nome} produto teste", preco, original, "https://img/x-O.jpg", True)


def test_oferta_por_desconto_do_ml():
    o = avaliar(prod(), info(70, 100), est.novo(), AGORA)
    assert o and round(o.desconto, 2) == 0.30 and o.preco_de == 100


def test_desconto_pequeno_nao_posta():
    assert avaliar(prod(), info(95, 100), est.novo(), AGORA) is None


def test_oferta_por_preco_de_referencia():
    o = avaliar(prod(ref=100), info(80), est.novo(), AGORA)
    assert o and o.preco_de is None and round(o.abaixo_do_habitual, 2) == 0.20


def test_menor_preco_historico():
    e = est.novo()
    for i, p in enumerate([100, 98, 99]):
        est.registrar_preco(e, "MLB1", p, AGORA - timedelta(days=3 - i))
    assert avaliar(prod(), info(90), e, AGORA).menor_preco_historico
    assert avaliar(prod(), info(97), e, AGORA) is None


def test_nao_repete_logo():
    e = est.novo()
    est.registrar_post(e, "MLB1", 70, AGORA - timedelta(days=1))
    assert avaliar(prod(), info(70, 100), e, AGORA) is None
    assert avaliar(prod(), info(60, 100), e, AGORA) is not None  # caiu mais
    assert avaliar(prod(), info(70, 100), e, AGORA + timedelta(days=3)) is not None


def test_indisponivel():
    i = info(50, 100)
    i.disponivel = False
    assert avaliar(prod(), i, est.novo(), AGORA) is None


# ---------- mensagens ----------

def test_brl():
    assert mensagens.brl(1299.9) == "R$ 1.299,90"


def test_mensagem_telegram_e_whatsapp():
    o = avaliar(prod(), info(70, 100), est.novo(), AGORA)
    o.titulo = "Fralda <Premium> & Cia"
    tg = mensagens.montar_telegram(o)
    assert "<s>R$ 100,00</s>" in tg and "<b>R$ 70,00</b>" in tg and "(-30%)" in tg
    assert "&lt;Premium&gt; &amp;" in tg and 'href="https://meli.la/a"' in tg
    wa = mensagens.montar_whatsapp(o)
    assert "~R$ 100,00~" in wa and "*R$ 70,00*" in wa and "https://meli.la/a" in wa


def test_mensagem_x_cabe():
    o = avaliar(prod(), info(70, 100), est.novo(), AGORA)
    o.titulo = "Fralda " * 80
    x = mensagens.montar_x(o)
    peso = len(x) - len(o.link) + 23 + 1  # emoji conta 2
    assert peso <= 280


# ---------- API do ML (simulada) ----------

class Resp:
    def __init__(self, status, dados):
        self.status_code, self._d, self.text, self.content = status, dados, str(dados), b"x"

    def json(self):
        return self._d


class SessaoFalsa:
    def __init__(self, resposta):
        self.resposta, self.chamadas = resposta, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.chamadas.append((url, params, headers))
        return self.resposta


def test_ml_itens():
    s = SessaoFalsa(Resp(200, [
        {"code": 200, "body": {"id": "MLB1", "title": "Fralda", "price": 70, "original_price": 100,
                               "status": "active", "available_quantity": 5,
                               "secure_thumbnail": "https://http2.mlstatic.com/D_123-I.jpg"}},
        {"code": 404, "body": {"message": "not found"}},
    ]))
    r = MercadoLivre("tok", session=s).itens(["MLB1", "MLB2"])
    assert list(r) == ["MLB1"]
    assert r["MLB1"].imagem.endswith("-O.jpg")
    assert s.chamadas[0][2]["Authorization"] == "Bearer tok"


def test_ml_acesso_negado():
    with pytest.raises(AcessoNegado):
        MercadoLivre(session=SessaoFalsa(Resp(403, {"message": "forbidden"}))).itens(["MLB1"])


# ---------- rodada completa (simulada) ----------

class MLFalso:
    def __init__(self, infos):
        self.infos = infos

    def itens(self, ids):
        return {i: self.infos[i] for i in ids if i in self.infos}

    def catalogo(self, pid, titulo=None, imagem=None):
        return self.infos[pid]


class TGFalso:
    def __init__(self):
        self.enviados = []

    def enviar_oferta(self, chat, legenda, imagem=None):
        self.enviados.append(("oferta", chat, legenda))

    def enviar_texto(self, chat, texto, html=False, botoes=None):
        self.enviados.append(("texto", chat, texto))
        self.botoes = botoes


def cenario():
    produtos = [prod("MLB1"), prod("MLB2"), prod("MLB3")]
    infos = {
        "MLB1": info(70, 100, "MLB1"),  # 30%
        "MLB2": info(50, 100, "MLB2"),  # 50% — melhor
        "MLB3": InfoProduto("MLB3", "Chupeta Nuk", 10, 50, None, True),  # bloqueada
    }
    return produtos, MLFalso(infos)


def test_rodada_normal_posta_a_melhor():
    produtos, ml = cenario()
    tg, e = TGFalso(), est.novo()
    cfg = Config(canal="@canal", admin_chat="123", max_por_rodada=1)
    enviadas = rodar("normal", cfg, ml, tg, e, produtos, agora=AGORA)
    assert [o.id for o in enviadas] == ["MLB2"]
    assert tg.enviados[0][:2] == ("oferta", "@canal")
    assert [t[1] for t in tg.enviados[1:]] == ["123"]  # cópia com botões
    assert tg.botoes[0][1].startswith("https://api.whatsapp.com/send?text=")
    assert tg.botoes[1][1].startswith("https://x.com/intent/tweet?text=")
    assert "MLB2" in e["postados"] and "MLB3" not in e["precos"]
    # Na rodada seguinte não repete a MLB2, posta a MLB1
    enviadas = rodar("normal", cfg, ml, TGFalso(), e, produtos, agora=AGORA + timedelta(minutes=20))
    assert [o.id for o in enviadas] == ["MLB1"]


def test_limite_por_hora():
    produtos = [prod(f"MLB{i}") for i in range(1, 6)]
    ml = MLFalso({f"MLB{i}": info(50, 100, f"MLB{i}") for i in range(1, 6)})
    e, cfg = est.novo(), Config(canal="@c", max_por_rodada=1, max_por_hora=2)
    feitos = [len(rodar("normal", cfg, ml, TGFalso(), e, produtos, agora=AGORA + timedelta(minutes=m)))
              for m in (0, 20, 40, 65)]
    assert feitos == [1, 1, 0, 1]


def test_sorteio_pula_rodada():
    import random as _r
    produtos, ml = cenario()
    cfg = Config(canal="@c", chance_postar=0.0)
    assert rodar("normal", cfg, ml, TGFalso(), est.novo(), produtos, agora=AGORA, rng=_r.Random(1)) == []


def test_rodada_fora_do_horario():
    produtos, ml = cenario()
    tg, e = TGFalso(), est.novo()
    madrugada = AGORA.replace(hour=3)
    assert rodar("normal", Config(canal="@c"), ml, tg, e, produtos, agora=madrugada) == []
    assert tg.enviados == [] and e["precos"]  # preços registrados mesmo assim


def test_limite_diario():
    produtos, ml = cenario()
    e = est.novo()
    e["contagem_dia"] = {AGORA.date().isoformat(): 25}
    assert rodar("normal", Config(canal="@c"), ml, TGFalso(), e, produtos, agora=AGORA) == []


def test_modo_teste_manda_so_para_admin():
    produtos, ml = cenario()
    tg, e = TGFalso(), est.novo()
    rodar("teste", Config(canal="@canal", admin_chat="123"), ml, tg, e, produtos, agora=AGORA.replace(hour=3))
    assert tg.enviados and all(chat == "123" for _, chat, _ in tg.enviados)
    assert "[TESTE]" in tg.enviados[0][2]
    assert e["postados"] == {}


def test_modo_teste_sem_oferta_manda_exemplo():
    produtos = [prod("MLB1")]
    ml = MLFalso({"MLB1": info(99, 100, "MLB1")})
    tg = TGFalso()
    rodar("teste", Config(admin_chat="123"), ml, tg, est.novo(), produtos, agora=AGORA)
    assert tg.enviados and "R$ 99,00" in tg.enviados[0][2]


# ---------- cofre do token ----------

def test_cofre(tmp_path):
    from bot import cofre
    arq = tmp_path / "t.enc"
    cofre.guardar("TG-refresh-123", "segredo", arq)
    assert b"TG-refresh" not in arq.read_bytes()
    assert cofre.ler("segredo", arq) == "TG-refresh-123"
    assert cofre.ler("outro", arq) is None
    assert cofre.ler("segredo", tmp_path / "nao-existe") is None


def test_conectar_ml_guarda_token_novo(tmp_path, monkeypatch):
    from bot import cofre, main
    arq = tmp_path / "t.enc"
    monkeypatch.setattr(cofre, "ARQ_TOKEN", arq)
    monkeypatch.setattr(cofre.guardar, "__defaults__", (arq,))
    monkeypatch.setattr(cofre.ler, "__defaults__", (arq,))
    cofre.guardar("velho", "s")
    monkeypatch.setattr(main, "renovar_token", lambda c, s, r: ("acesso", "novo" if r == "velho" else "x"))
    ml, modo = main.conectar_ml(Config(ml_client_id="c", ml_client_secret="s"))
    assert ml.token == "acesso" and modo == "com token"
    assert cofre.ler("s") == "novo"


# ---------- descoberta e link de afiliado ----------

def test_afiliado():
    from bot import afiliado
    url = afiliado.montar("https://www.mercadolivre.com.br/p/MLB123?x=1#y", "chocalho", "999")
    assert url == "https://www.mercadolivre.com.br/p/MLB123?matt_word=chocalho&matt_tool=999"
    with pytest.raises(ValueError):
        afiliado.montar("https://x", "", "")


class SessaoRotas:
    def __init__(self, rotas):
        self.rotas, self.chamadas = rotas, []

    def get(self, url, params=None, headers=None, timeout=None):
        caminho = url.replace("https://api.mercadolibre.com", "")
        self.chamadas.append(caminho)
        status, dados = self.rotas.get(caminho, (404, {"message": "not found"}))
        return Resp(status, dados)


def test_catalogo_menor_preco_e_cache():
    s = SessaoRotas({
        "/products/MLB9": (200, {"name": "Fralda Huggies XG", "pictures": [{"url": "https://i/a-I.jpg"}],
                                 "buy_box_winner": None}),
        "/products/MLB9/items": (200, {"results": [{"price": 194.99, "original_price": 197.75},
                                                   {"price": 180.0, "original_price": 250.0}]}),
    })
    ml = MercadoLivre("t", session=s)
    i = ml.catalogo("MLB9")
    assert (i.titulo, i.preco, i.preco_original, i.disponivel) == ("Fralda Huggies XG", 180.0, 250.0, True)
    assert i.imagem == "https://i/a-O.jpg"
    s.chamadas.clear()
    ml.catalogo("MLB9", "Fralda", "img")
    assert s.chamadas == ["/products/MLB9/items"]  # usou o cache, sem pedir nome/foto
    assert ml.catalogo("MLB8", "X", None).disponivel is False  # ninguém vendendo


def test_descobrir():
    from bot import descoberta
    s = SessaoRotas({
        "/categories/MLB1384": (200, {"children_categories": [
            {"id": "MLB1396", "name": "Roupas"}, {"id": "MLB39965", "name": "Alimentos"}]}),
        "/categories/MLB1132": (200, {"children_categories": [{"id": "MLB1166", "name": "Pelúcias"}]}),
        "/highlights/MLB/category/MLB1384": (200, {"content": [
            {"id": "MLB2", "position": 2, "type": "PRODUCT"}, {"id": "MLB1", "position": 1, "type": "ITEM"},
            {"id": "MLB7", "position": 3, "type": "USER_PRODUCT"}]}),
        "/highlights/MLB/category/MLB1396": (200, {"content": [{"id": "MLB3", "position": 1, "type": "PRODUCT"}]}),
        "/highlights/MLB/category/MLB1166": (403, {"message": "forbidden"}),
    })
    achados = descoberta.descobrir(MercadoLivre("t", session=s), por_categoria=5, log=lambda m: None)
    assert achados == {
        "MLB2": {"tipo": "catalogo", "categoria": "outros", "pos": 0},
        "MLB3": {"tipo": "catalogo", "categoria": "roupa", "pos": 0},
    }
    assert "/highlights/MLB/category/MLB39965" not in s.chamadas  # categoria excluída


def test_montar_lista_e_descoberta_periodica(monkeypatch):
    from bot import main
    cfg = Config(matt_word="w", matt_tool="1")
    e = est.novo()
    chamadas = []
    monkeypatch.setattr(main, "descobrir", lambda ml, n, log: chamadas.append(1) or
                        {"MLB5": {"tipo": "catalogo", "categoria": "brinquedo"}})
    assert main.atualizar_descoberta(cfg, None, e, AGORA)
    assert not main.atualizar_descoberta(cfg, None, e, AGORA + timedelta(hours=5))
    assert main.atualizar_descoberta(cfg, None, e, AGORA + timedelta(hours=21))
    assert len(chamadas) == 2
    planilha = [Produto("MLB9", "item", "x", "", "fralda", None, 2)]
    lista = main.montar_lista(cfg, planilha, e)
    assert [p.id for p in lista] == ["MLB9", "MLB5"]
    assert lista[0].link_afiliado == "https://produto.mercadolivre.com.br/MLB-9?matt_word=w&matt_tool=1"
    assert lista[1].link_afiliado == "https://www.mercadolivre.com.br/p/MLB5?matt_word=w&matt_tool=1"


# ---------- ciclo ----------

def test_proximo_horario():
    from bot.ciclo import proximo_horario
    d = lambda h, m, dia=6: datetime(2026, 11, dia, h, m, tzinfo=FUSO)
    assert proximo_horario(d(10, 0), 8, 22) == d(10, 20)
    assert proximo_horario(d(21, 50), 8, 22) == d(8, 2, 7)  # passou das 22h: amanhã cedo
    assert proximo_horario(d(3, 0), 8, 22) == d(8, 2)  # madrugada: hoje às 8h


# ---------- lote do Linkbuilder ----------

def test_lote_fluxo_completo():
    from bot import lote
    e = est.novo()
    roupa = avaliar(Produto("MLB2", "catalogo", "", "x?matt_word=w", "roupa", None, 0),
                    info(80, 100, "MLB2"), e, AGORA)  # 20%, mas roupa pesa mais
    brinq = avaliar(Produto("MLB1", "catalogo", "", "x?matt_word=w", "brinquedo", None, 0),
                    info(78, 100, "MLB1"), e, AGORA)  # 22%
    urls = lote.montar_lote(e, [(brinq, "MLB111"), (roupa, "MLB222"), (brinq, "MLB111")], 10, AGORA)
    assert urls == [lote.url_linkbuilder("MLB222"), lote.url_linkbuilder("MLB111")]
    assert e["lote"]["ids"] == ["MLB2", "MLB1"]
    ok, msg = lote.aplicar_resposta(e, "https://meli.la/AAA")
    assert not ok and "não salvei" in msg
    ok, msg = lote.aplicar_resposta(e, "aqui:\nhttps://meli.la/AAA\nhttps://meli.la/BBB")
    assert ok and e["links"] == {"MLB2": "https://meli.la/AAA", "MLB1": "https://meli.la/BBB"}
    assert e["lote"] is None


def test_modo_oficial_so_posta_com_link_e_manda_lote():
    from bot import main
    e = est.novo()
    produtos = [Produto("MLB1", "catalogo", "", "https://x/p/MLB1?matt_word=w&matt_tool=1", "fralda", None, 0),
                Produto("MLB2", "catalogo", "", "https://meli.la/ok", "fralda", None, 0)]
    infos = {"MLB1": info(50, 100, "MLB1"), "MLB2": info(70, 100, "MLB2")}
    infos["MLB1"].item_id = "MLB999"
    tg = TGFalso()
    enviadas = main.rodar("normal", Config(canal="@c", admin_chat="123", max_por_rodada=5),
                          MLFalso(infos), tg, e, produtos, agora=AGORA)
    assert [o.id for o in enviadas] == ["MLB2"]  # MLB1 tem desconto maior, mas não tem link oficial
    assert e["lote"]["ids"] == ["MLB1"]
    assert any("Linkbuilder" in t[2] for t in tg.enviados)
    # Com lote pendente, não manda outro
    n = len(tg.enviados)
    main.rodar("normal", Config(canal="@c", admin_chat="123"), MLFalso(infos), tg, e, produtos,
               agora=AGORA + timedelta(minutes=20))
    assert not any("Linkbuilder" in t[2] for t in tg.enviados[n:])
    # Lote antigo maior que 30 (feito antes do limite) é refeito
    e["lote"]["ids"] = ["MLB1"] * 40
    main.rodar("normal", Config(canal="@c", admin_chat="123"), MLFalso(infos), tg, e, produtos,
               agora=AGORA + timedelta(minutes=40))
    assert e["lote"]["ids"] == ["MLB1"] and e["lotes_dia"][AGORA.date().isoformat()] == 2
    # Respondeu: o próximo sai, até o limite do dia
    e["lote"] = None
    e["lotes_dia"] = {AGORA.date().isoformat(): 3}
    n = len(tg.enviados)
    main.rodar("normal", Config(canal="@c", admin_chat="123"), MLFalso(infos), tg, e, produtos,
               agora=AGORA + timedelta(minutes=60))
    assert not any("Linkbuilder" in t[2] for t in tg.enviados[n:])


class TGCmd:
    """Telegram falso para os comandos."""
    def __init__(self, updates=()):
        self.updates, self.textos, self.ofertas = list(updates), [], []

    def atualizacoes(self, offset=None):
        return self.updates

    def enviar_texto(self, chat, t, html=False, botoes=None, responder_a=None):
        self.textos.append((chat, t))
        self.respostas = getattr(self, "respostas", []) + [responder_a]
        return {"message_id": 500 + len(self.textos)}

    def editar_texto(self, chat, message_id, texto, html=True):
        self.editados = getattr(self, "editados", []) + [(chat, message_id, texto)]

    def enviar_oferta(self, chat, legenda, imagem=None):
        self.ofertas.append((chat, legenda))

    def membros(self, chat):
        return 120


class PaginaFalsa:
    def __init__(self, texto):
        self.texto = texto

    def get(self, url, headers=None, timeout=None):
        class R: pass
        r = R(); r.text = self.texto
        return r


HTML_SOCIAL = 'x"item_id":"MLB555"y"product_id":"MLB9"z ... "item_id":"MLB777" "product_id":"MLB8"'


def cfg_cmd():
    return Config(canal="@canal", admin_chat="123")


def test_resolver_meli():
    from bot import comandos
    assert comandos.resolver_meli("https://meli.la/x", PaginaFalsa(HTML_SOCIAL)) == ("catalogo", "MLB9")
    assert comandos.resolver_meli("https://meli.la/x", PaginaFalsa('"item_id":"MLB5"')) == ("item", "MLB5")
    assert comandos.resolver_meli("https://meli.la/x", PaginaFalsa("nada")) is None


def test_comando_link_avulso_posta_e_passa_a_acompanhar():
    from bot import comandos
    e, tg = est.novo(), TGCmd()
    ml = MLFalso({"MLB9": InfoProduto("MLB9", "Body Bebê Kit 3", 50, 80, "img", True)})
    r = comandos.tratar_texto("olha esse https://meli.la/AbC", tg, ml, e, cfg_cmd(), AGORA,
                              session=PaginaFalsa(HTML_SOCIAL))
    assert r.startswith("✅ Postado") and tg.ofertas[0][0] == "@canal"
    assert e["links"]["MLB9"] == "https://meli.la/AbC" and "MLB9" in e["manuais"]
    assert "MLB9" in e["postados"]
    # Entra na lista de acompanhamento do bot
    from bot.main import montar_lista
    assert "MLB9" in [p.id for p in montar_lista(Config(matt_word="w", matt_tool="1"), [], e)]


def test_comando_link_bloqueado_nbcal():
    from bot import comandos
    e, tg = est.novo(), TGCmd()
    ml = MLFalso({"MLB9": InfoProduto("MLB9", "Mamadeira Anticólica 260ml", 30, 60, None, True)})
    r = comandos.tratar_texto("https://meli.la/AbC", tg, ml, e, cfg_cmd(), AGORA, session=PaginaFalsa(HTML_SOCIAL))
    assert r.startswith("🚫") and not tg.ofertas


def test_comando_lote_tem_prioridade():
    from bot import comandos
    e, tg = est.novo(), TGCmd()
    e["lote"] = {"dia": "x", "ids": ["MLB1", "MLB2"], "urls": ["u", "v"]}
    r = comandos.tratar_texto("https://meli.la/A https://meli.la/B", tg, MLFalso({}), e, cfg_cmd(), AGORA)
    assert "salvos" in r and e["links"] == {"MLB1": "https://meli.la/A", "MLB2": "https://meli.la/B"}
    assert not tg.ofertas


def test_comando_cupom_e_ajuda():
    from bot import comandos
    e, tg = est.novo(), TGCmd()
    r = comandos.tratar_texto("Cupom: 20% OFF em brinquedos, código BRINCA20", tg, None, e, cfg_cmd(), AGORA)
    assert r.startswith("✅") and tg.textos[0][0] == "@canal" and "BRINCA20" in tg.textos[0][1]
    assert "#publi" not in tg.textos[0][1]
    assert "Compartilhar" in comandos.tratar_texto("https://www.mercadolivre.com.br/x/p/MLB1", tg, None, e,
                                                   cfg_cmd(), AGORA)
    assert "O que você pode me mandar" in comandos.tratar_texto("oi", tg, None, e, cfg_cmd(), AGORA)


def test_processar_membros_e_resumo():
    from bot import comandos
    e = est.novo()
    e["membros_hist"] = {"2026-11-04": 100}
    entra = {"old_chat_member": {"status": "left"}, "new_chat_member": {"status": "member"}}
    sai = {"old_chat_member": {"status": "member"}, "new_chat_member": {"status": "left"}}
    tg = TGCmd([{"update_id": 7, "chat_member": entra}, {"update_id": 8, "chat_member": entra},
                {"update_id": 9, "chat_member": sai},
                {"update_id": 10, "message": {"chat": {"id": 999}, "text": "oi"}},
                {"update_id": 11, "message": {"chat": {"id": 123}, "text": "resumo"}}])
    est.registrar_post(e, "MLB1", 50, AGORA, "Fralda Pampers G", 0.4)
    comandos.processar(tg, None, e, cfg_cmd(), AGORA, log=lambda m: None)
    assert e["tg_offset"] == 12 and e["membros_dia"][AGORA.date().isoformat()] == {"entrou": 2, "saiu": 1}
    resumo = tg.textos[-1][1]
    assert tg.textos[-1][0] == "123" and "120" in resumo and "2 entraram" in resumo and "-40% Fralda" in resumo
    # Resumo automático: só na última hora, uma vez por dia
    tg2 = TGCmd()
    comandos.talvez_resumo_diario(tg2, e, cfg_cmd(), AGORA.replace(hour=15), log=lambda m: None)
    assert not tg2.textos
    comandos.talvez_resumo_diario(tg2, e, cfg_cmd(), AGORA.replace(hour=21), log=lambda m: None)
    comandos.talvez_resumo_diario(tg2, e, cfg_cmd(), AGORA.replace(hour=21, minute=40), log=lambda m: None)
    assert len(tg2.textos) == 1


# ---------- ranking, ritmo e chamadas ----------

def test_pontuacao_e_ritmo():
    from bot.ofertas import limite_hora, meta_ate_agora, pontuacao
    e = est.novo()
    roupa = avaliar(Produto("A", "catalogo", "", "l", "roupa", None, 0), info(80, 100, "A"), e, AGORA)
    brinq = avaliar(Produto("B", "catalogo", "", "l", "brinquedo", None, 0), info(76, 100, "B"), e, AGORA)
    assert pontuacao(roupa) < pontuacao(brinq)  # comissão não pesa mais: 24% de desconto ganha de 20%
    assert pontuacao(brinq, 0) > pontuacao(brinq, 10)  # top 3 dos mais vendidos ganha bônus
    assert meta_ate_agora(50, 21) == 50 and meta_ate_agora(50, 8) < meta_ate_agora(50, 12)
    # O almoço "pesa" mais que uma hora comum
    assert meta_ate_agora(50, 12) - meta_ate_agora(50, 11) > meta_ate_agora(50, 10) - meta_ate_agora(50, 9)
    assert limite_hora(4, 20) == 6 and limite_hora(4, 10) == 4


def test_ritmo_guarda_posts_para_a_noite():
    produtos = [prod(f"MLB{i}") for i in range(1, 30)]
    ml = MLFalso({f"MLB{i}": info(50, 100, f"MLB{i}") for i in range(1, 30)})
    e = est.novo()
    cfg = Config(canal="@c", max_por_rodada=5, max_por_hora=10, max_por_dia=20)
    cedo = rodar("normal", cfg, ml, TGFalso(), e, produtos, agora=AGORA.replace(hour=8, minute=5))
    assert 0 < len(cedo) <= 2  # 8h: só a "cota" da primeira hora


def test_chamada_por_categoria():
    import random as _r
    o = avaliar(prod(), info(70, 100), est.novo(), AGORA)
    o.categoria = "fralda"
    o.titulo = "Produto generico qualquer"
    textos = {mensagens._abertura(o, _r.Random(i)) for i in range(40)}
    assert any(t in mensagens.CHAMADAS["fralda"] for t in textos)
    assert any(t in mensagens.ABERTURAS for t in textos)


def test_abertura_combina_com_o_produto():
    import random as _r
    o = avaliar(prod(), info(70, 100), est.novo(), AGORA)
    o.titulo, o.categoria = "Banheira Bebê Dobrável Com Suporte", "higiene"
    textos = {mensagens._abertura(o, _r.Random(i)) for i in range(80)}
    _, frases = mensagens._frases_do_produto(o.titulo)
    assert any(t in frases for t in textos)
    assert "🪇 Chacoalhou o preço da banheira!" in textos or any("da banheira" in t for t in textos)
    assert not any("fralda" in t.lower() for t in textos)  # nada de frase de outro produto
    # Sem preço "de": nenhuma frase dizendo que o preço caiu
    o.preco_de = None
    sem_de = {mensagens._abertura(o, _r.Random(i)) for i in range(80)}
    assert not any(t in mensagens.ABERTURAS_PRECO or "preço" in t for t in sem_de)
    assert mensagens._frases_do_produto("Fralda Turma da Mônica M 50 un")[0] == "da fralda"
    assert mensagens._frases_do_produto("Kit Berço Protetor Trança")[1][0].startswith("🛏️")
    # Produto principal vem primeiro no título: berço com mosquiteiro é berço
    assert mensagens._frases_do_produto("Berço Co-sleeper Com Mosquiteiro")[0] == "do berço"
    assert mensagens._frases_do_produto("Cadeirinha De Descanso Musical")[0] == "da cadeirinha de descanso"
    assert mensagens._frases_do_produto("Trocador De Fraldas Portátil")[0] == "do trocador"


# ---------- página (vitrine) ----------

def test_vitrine(tmp_path):
    from bot import vitrine
    e = est.novo()
    o = avaliar(Produto("MLB1", "catalogo", "", "https://meli.la/A", "roupa", None, 0), info(60, 100, "MLB1"), e, AGORA)
    o.titulo = "Body <bebê> & cia"
    vitrine.guardar(e, [o], AGORA)
    arq = tmp_path / "index.html"
    assert vitrine.talvez_publicar(e, "@chocalho", AGORA, arq, log=lambda m: None)
    h = arq.read_text()
    assert "https://t.me/chocalho" in h and "Body &lt;bebê&gt; &amp; cia" in h and "%" not in h.split("<body>")[1].split("<script>")[0]
    assert "https://meli.la/A" in h and "#publi" in h and 'data-f="roupa"' in h and "R$ 100,00" in h
    assert "[[" not in h  # todos os campos do modelo foram preenchidos
    # Mesma hora: não reescreve; hora seguinte sem mudança: também não
    assert not vitrine.talvez_publicar(e, "@chocalho", AGORA, arq, log=lambda m: None)
    assert not vitrine.talvez_publicar(e, "@chocalho", AGORA + timedelta(hours=1), arq, log=lambda m: None)
    o.preco = 55
    vitrine.guardar(e, [o], AGORA)
    assert vitrine.talvez_publicar(e, "@chocalho", AGORA + timedelta(hours=1), arq, log=lambda m: None)


def test_vitrine_selos_e_shopee():
    from types import SimpleNamespace
    from bot import vitrine
    e = est.novo()
    # 10 dias a R$ 100, hoje a R$ 80: baixou de verdade (preço normal R$ 100)
    for d in range(10, 0, -1):
        est.registrar_preco(e, "MLB9", 100.0, AGORA - timedelta(days=d))
    est.registrar_preco(e, "MLB9", 80.0, AGORA)
    item = {"id": "MLB9", "preco": 80.0}
    assert vitrine.selo(e, item, AGORA) == ("baixou", 100.0)
    # preço sempre igual: sem selo, mesmo com "de" alto no anúncio
    for d in range(10, -1, -1):
        est.registrar_preco(e, "MLB8", 50.0, AGORA - timedelta(days=d))
    assert vitrine.selo(e, {"id": "MLB8", "preco": 50.0}, AGORA) == (None, None)
    # pouco histórico: sem selo
    est.registrar_preco(e, "MLB7", 30.0, AGORA)
    assert vitrine.selo(e, {"id": "MLB7", "preco": 30.0}, AGORA) == (None, None)
    o = SimpleNamespace(id="SHP1", titulo="Kit massinha", preco=19.9, preco_de=None, a_partir=True,
                        imagem="https://x/y.jpg", categoria="brinquedo")
    vitrine.guardar_shopee(e, o, "https://s.shopee.com.br/site", AGORA)
    vitrine.guardar_shopee(e, o, "https://s.shopee.com.br/site", AGORA)
    assert len(e["vitrine_shopee"]) == 1
    h = vitrine.gerar_html(e, "@chocalho", "https://chat.whatsapp.com/ABC", AGORA)
    assert "Shopee" in h and "a partir de" in h and "https://s.shopee.com.br/site" in h and "chat.whatsapp.com" in h
    # some depois de 36 h
    vitrine.guardar_shopee(e, SimpleNamespace(**{**o.__dict__, "id": "SHP2"}), "l", AGORA + timedelta(hours=40))
    assert [i["id"] for i in e["vitrine_shopee"]] == ["SHP2"]


def test_intervalo_aleatorio_entre_posts(monkeypatch):
    import random as _r
    from bot import main
    esperas = []
    monkeypatch.setattr(main, "dormir", lambda seg: esperas.append(seg))
    produtos = [prod(f"MLB{i}") for i in range(1, 6)]
    ml = MLFalso({f"MLB{i}": info(50, 100, f"MLB{i}") for i in range(1, 6)})
    cfg = Config(canal="@c", max_por_rodada=3, max_por_hora=10, max_por_dia=50,
                 intervalo_min=4, intervalo_max=8, atraso_max=3)
    enviadas = main.rodar("normal", cfg, ml, TGFalso(), est.novo(), produtos, agora=AGORA, rng=_r.Random(3))
    assert len(enviadas) == 3 and len(esperas) == 3  # atraso inicial + 2 intervalos
    assert 0 <= esperas[0] <= 180 and all(240 <= x <= 480 for x in esperas[1:])
    assert esperas[1] != esperas[2]


# ---------- cupons: esgotado e validade ----------

def test_extrair_codigo_e_validade():
    from bot import comandos
    assert comandos.extrair_codigo("15% OFF em fraldas, código fralda15") == "FRALDA15"
    assert comandos.extrair_codigo("R$ 20 OFF acima de R$ 99 com BEBE20 no app") == "BEBE20"
    assert comandos.extrair_codigo("10% OFF em tudo") is None
    v = comandos.extrair_validade
    assert v("válido até 10/11", AGORA) == AGORA.replace(day=10, hour=23, minute=59, second=0)
    assert v("até 10/11 às 18h", AGORA) == AGORA.replace(day=10, hour=18, minute=0, second=0)
    assert v("só hoje!", AGORA) == AGORA.replace(hour=23, minute=59, second=0)
    assert v("até 15h30", AGORA) == AGORA.replace(hour=15, minute=30, second=0)
    assert v("até 05/01", AGORA.replace(month=12)).year == AGORA.year + 1
    assert v("sem data", AGORA) is None


def test_cupom_esgotou_e_vence():
    from bot import comandos
    e, tg = est.novo(), TGCmd()
    r = comandos.tratar_texto("cupom 20% OFF em brinquedos, código BRINCA20, até 10/11", tg, None, e,
                              cfg_cmd(), AGORA)
    assert "esgotou BRINCA20" in r and "10/11" in r
    c = e["cupons"]["BRINCA20"]
    assert c["status"] == "ativo" and c["post"] == 501 and c["validade"].startswith("2026-11-10T23:59")
    comandos.tratar_texto("cupom 10% OFF em roupas, código ROUPA10", tg, None, e, cfg_cmd(), AGORA)
    assert "Me diga qual" in comandos.tratar_texto("esgotou", tg, None, e, cfg_cmd(), AGORA)
    r = comandos.tratar_texto("Esgotou brinca20", tg, None, e, cfg_cmd(), AGORA)
    assert r.startswith("✅") and e["cupons"]["BRINCA20"]["status"] == "esgotado"
    assert tg.editados[-1][1] == 501 and "ESGOTADO" in tg.editados[-1][2]
    assert tg.respostas[-1] == 501 and "esgotou" in tg.textos[-1][1]
    # Validade: ROUPA10 não tem data; um cupom "só hoje" vence às 23h59
    comandos.tratar_texto("cupom R$ 15 OFF em fraldas, código FRALDA15, só hoje", tg, None, e, cfg_cmd(), AGORA)
    comandos.verificar_cupons(tg, cfg_cmd(), e, AGORA.replace(hour=22), log=lambda m: None)
    assert e["cupons"]["FRALDA15"]["status"] == "ativo"
    comandos.verificar_cupons(tg, cfg_cmd(), e, AGORA + timedelta(days=1), log=lambda m: None)
    assert e["cupons"]["FRALDA15"]["status"] == "encerrado" and "ENCERRADO" in tg.editados[-1][2]
    assert e["cupons"]["ROUPA10"]["status"] == "ativo"
    comandos.verificar_cupons(tg, cfg_cmd(), e, AGORA + timedelta(days=11), log=lambda m: None)
    assert e["cupons"] == {} and e["posts_cupom"] == {}  # antigos são esquecidos


# ---------- canal de cupons do Mercado Livre (posts reais) ----------

POST_ML_1 = """Meio-dia: entrada, prato principal e sobremesa servidos juntos!

🎟️ SEMPREOFF 👉 R$300 OFF
Tecnologia | Compra mínima: R$2.199
Válido somente em 06.11, em até 90% da categoria.
🔗 https://bit.ly/4A8Qi2M

🎟️ MOMENTOPROMO 👉 30% OFF
Compra mín: R$1 | Desconto máx: R$500
Válido até 31.12, ou enquanto durarem os estoques, em produtos elegíveis.
🔗 https://bit.ly/4jVaBMn

🎟️ GANHOUOFF 👉 30% OFF
Compra mín: R$1 | Desconto máx: R$500
Válido até 28.12, ou enquanto durarem os estoques, em produtos elegíveis.
🔗 https://bit.ly/4fh8yyT

Buchinho cheio, agora é só dar aquela arrasada!"""

POST_ML_LOTE = """🚚📦 Descarregando o segundo lote:

🎟️ OFFPRACONSTRU 👉 20% OFF
Indústria e Comércio
Compra mín: R$79 | Desconto máx: R$80

🎟️ MODAKIDS 👉 15% OFF
Moda Infantil
Compra mín: R$99 | Desconto máx: R$50

🎟️ SAUDEMELI 👉 10% OFF
Saúde
Compra mín: R$79 | Desconto máx: R$40

Compartilhe!
🔗 https://bit.ly/4BHIUNj"""

POST_ML_UPDATE = """Confirmado: cupons aumentaram o percentual de desconto:

🎟️ CLIENTESTOP: 10% → 15% OFF
📱 Tecnologia

🎟️ MOMENTOPROMO: 30% → 35% OFF

Compartilhe agora!
🔗 https://bit.ly/4AcBZu8
Válidos até hoje (05/11), em até 90% das respectivas categorias."""

POST_ML_OFERTAS = """Virou o dia, ofertas exclusivas:

💻 Notebook Lenovo IdeaPad Core 3, 8GB/128GB
💰 De ~~R$ 3.999~~ por R$ 3.389 | Pix: R$ 3.287,33
🔗 https://bit.ly/4ir6PJA"""


def test_parse_cupons_ml():
    from bot import cupons_ml
    c = {x["codigo"]: x for x in cupons_ml.parse(POST_ML_1, AGORA)}
    assert list(c) == ["SEMPREOFF", "MOMENTOPROMO", "GANHOUOFF"]
    assert c["SEMPREOFF"]["categoria"] == "Tecnologia" and c["SEMPREOFF"]["minimo"] == "R$2.199"
    assert c["SEMPREOFF"]["validade"] == AGORA.replace(day=6, hour=23, minute=59, second=0)
    assert c["MOMENTOPROMO"]["categoria"] is None and c["MOMENTOPROMO"]["maximo"] == "R$500"
    assert c["MOMENTOPROMO"]["validade"].month == 12 and c["MOMENTOPROMO"]["link"] == "https://bit.ly/4jVaBMn"
    lote_ = {x["codigo"]: x for x in cupons_ml.parse(POST_ML_LOTE, AGORA)}
    assert lote_["MODAKIDS"]["categoria"] == "Moda Infantil" and lote_["MODAKIDS"]["link"] == "https://bit.ly/4BHIUNj"
    up = {x["codigo"]: x for x in cupons_ml.parse(POST_ML_UPDATE, AGORA)}
    assert up["CLIENTESTOP"]["antes"] == "10%" and up["CLIENTESTOP"]["desconto"] == "15% OFF"
    assert up["CLIENTESTOP"]["categoria"] == "Tecnologia"
    assert up["MOMENTOPROMO"]["validade"] == AGORA.replace(hour=23, minute=59, second=0)
    assert cupons_ml.parse(POST_ML_OFERTAS, AGORA) == []
    assert cupons_ml.relevante({"categoria": None}) and cupons_ml.relevante({"categoria": "Moda Infantil"})
    assert not cupons_ml.relevante({"categoria": "Tecnologia"})
    assert cupons_ml.relevante({"categoria": "Tecnologia"}, "todas")


def test_tratar_mensagens_do_canal_ml():
    from bot import comandos, cupons_ml
    e, tg = est.novo(), TGCmd()
    log = lambda m: None
    n = cupons_ml.tratar_mensagem(POST_ML_1, tg, cfg_cmd(), e, AGORA, log=log)
    assert n == 2  # Tecnologia fica de fora
    canal = [t for c, t in tg.textos if c == "@canal"]
    assert "MOMENTOPROMO" in canal[0] and "GANHOUOFF" in canal[0] and "SEMPREOFF" not in canal[0]
    assert "Ativar o cupom" in canal[0] and "Cupons do Mercado Livre" in canal[0]
    # Repetido: não posta de novo
    assert cupons_ml.tratar_mensagem(POST_ML_1, tg, cfg_cmd(), e, AGORA, log=log) == 0
    # Atualização de um cupom já postado: edita e avisa
    cupons_ml.tratar_mensagem(POST_ML_UPDATE, tg, cfg_cmd(), e, AGORA, log=log)
    assert "35% OFF</b> ⬆️" in tg.editados[-1][2] and "Melhorou" in tg.textos[-1][1]
    assert "Desconto máx.: R$500" in tg.editados[-1][2]  # mantém as regras do post original
    # Esgotar um cupom risca só ele no post
    comandos.tratar_texto("esgotou ganhouoff", tg, None, e, cfg_cmd(), AGORA)
    texto = tg.editados[-1][2]
    assert "<s><b>🎟️ GANHOUOFF" in texto and "❌ esgotou" in texto and "Cupons do Mercado Livre" in texto
    # Vencido: GANHOUOFF esgotado, MOMENTOPROMO (atualizado: até hoje) encerra à noite
    cupons_ml.tratar_mensagem(POST_ML_LOTE, tg, cfg_cmd(), e, AGORA, log=log)
    comandos.verificar_cupons(tg, cfg_cmd(), e, AGORA + timedelta(days=1), log=log)
    assert e["cupons"]["MOMENTOPROMO"]["status"] == "encerrado"
    assert e["cupons"]["MODAKIDS"]["status"] == "ativo"  # sem data: continua
    # Nada de ofertas de produto
    assert cupons_ml.tratar_mensagem(POST_ML_OFERTAS, tg, cfg_cmd(), e, AGORA, log=log) == 0


def test_sessao_criptografada(tmp_path):
    from bot import cupons_ml
    arq = tmp_path / "s.enc"
    cupons_ml.guardar_seguro({"sessao": "1Babc"}, "hash123", arq)
    assert b"1Babc" not in arq.read_bytes()
    assert cupons_ml.ler_seguro("hash123", arq) == {"sessao": "1Babc"}


def test_reconfere_preco_antes_de_postar(monkeypatch):
    from bot import main
    monkeypatch.setattr(main, "dormir", lambda seg: None)
    produtos = [prod("MLB1"), prod("MLB2"), prod("MLB3")]
    infos = {"MLB1": info(50, 100, "MLB1"), "MLB2": info(60, 100, "MLB2"), "MLB3": info(70, 100, "MLB3")}

    class MLMuda(MLFalso):
        """Na segunda consulta, a MLB1 já voltou ao preço cheio."""
        def __init__(self, infos):
            super().__init__(infos)
            self.vezes = {}

        def catalogo(self, pid, titulo=None, imagem=None):
            self.vezes[pid] = self.vezes.get(pid, 0) + 1
            if pid == "MLB1" and self.vezes[pid] > 1:
                return InfoProduto("MLB1", "Fralda", 100, None, None, True)
            return self.infos[pid]

    produtos = [Produto(p.id, "catalogo", "", "https://meli.la/x", "fralda", None, 0) for p in produtos]
    cfg = Config(canal="@c", max_por_rodada=2, max_por_hora=10, max_por_dia=50, intervalo_min=4, intervalo_max=8)
    rodadas = []
    enviadas = main.rodar("normal", cfg, MLMuda(infos), TGFalso(), est.novo(), produtos, agora=AGORA,
                          tarefa=lambda: rodadas.append(1))
    assert [o.id for o in enviadas] == ["MLB2", "MLB3"]  # MLB1 acabou e foi pulada
    assert rodadas  # mensagens e cupons conferidos durante a espera entre posts


def test_vitrine_com_grupo_whatsapp(tmp_path):
    from bot import vitrine
    e = est.novo()
    o = avaliar(Produto("MLB1", "catalogo", "", "https://meli.la/A", "roupa", None, 0), info(60, 100, "MLB1"), e, AGORA)
    vitrine.guardar(e, [o], AGORA)
    arq = tmp_path / "i.html"
    assert vitrine.talvez_publicar(e, "@c", AGORA, arq, log=lambda m: None, grupo_wa="https://chat.whatsapp.com/X")
    h = arq.read_text()
    assert "Entrar no grupo do WhatsApp" in h and 'href="https://chat.whatsapp.com/' in h and 'data-wa="' in h and "t.me/c" in h
    g = (tmp_path / "grupo.html").read_text()
    assert "fbq('init','1161972522974367')" in g and "fbq('init','1161972522974367')" in h
    assert '"X"' in g and "intent://chat/?code=" in g and "whatsapp://chat?code=" in g


def test_arte_da_oferta():
    from PIL import Image
    import io
    from bot import arte
    o = avaliar(prod(), info(70, 100), est.novo(), AGORA)
    o.titulo = "Fralda Pampers Confort Sec Tamanho G Pacote com 92 Unidades Super Absorvente Noturna Extra"
    png = arte.gerar(o, foto=Image.new("RGBA", (500, 500), (200, 220, 255, 255)))
    img = Image.open(io.BytesIO(png))
    assert img.size == (1080, 1350)
    assert Image.open(io.BytesIO(arte.gerar(o))).size == (1080, 1350)  # sem foto também funciona


def test_pacote_do_dia_monta_tudo(monkeypatch):
    import random
    from datetime import datetime
    from PIL import Image
    from bot import arte, conteudo
    monkeypatch.setattr(arte, "foto_de_capa", lambda temas, rng=None: Image.new("RGB", (1200, 1600), (240, 230, 220)))
    itens = [{"id": f"MLB{i}", "titulo": f"Brinquedo legal número {i} com nome comprido para quebrar linha",
              "preco": 20.0 + i, "de": 40.0 + i, "desconto": 0.4 - i / 100, "link": f"https://meli.la/x{i}",
              "imagem": None, "categoria": "brinquedo"} for i in range(8)]
    itens.append({"id": "MLBadulto", "titulo": "Taco de sinuca", "preco": 10, "de": 50, "desconto": 0.8,
                  "link": "https://meli.la/y", "imagem": None, "categoria": "jogo"})
    estado = {"vitrine": {"em": "x", "itens": itens}}
    enviados = []

    class TG:
        def enviar_texto(self, c, t, html=False, **k): enviados.append(("txt", t))
        def enviar_album(self, c, pngs, leg=None): enviados.append(("album", len(pngs)))
        def enviar_video(self, c, mp4, leg=None): enviados.append(("video", len(mp4)))
        def enviar_foto(self, c, png, leg=None): enviados.append(("foto", leg))
        def enviar_documento(self, c, dados, nome, leg=None, tipo=None): enviados.append(("doc", nome))

    agora = datetime(2026, 11, 9, 10, tzinfo=FUSO)
    assert conteudo.montar_e_enviar(TG(), 1, estado, agora, rng=random.Random(1))
    assert ("album", 6) in enviados  # capa + 4 produtos + final
    assert not any("sinuca" in str(x) for x in enviados)
    assert any(t == "txt" and "#publi" in str(v) and "Comenta GRUPO" in str(v) for t, v in enviados)
    stories = [v for t, v in enviados if t == "foto" and v and v.startswith("📱")]
    assert stories and "meli.la" in stories[0]
    assert len(estado["pacote_usados"]) == 5  # dia 1 do lançamento: 1 carrossel (4) + 1 post
    assert any(t == "txt" and "dia 1 de 3" in str(v) for t, v in enviados)
    assert any(t == "txt" and "Prazer, Chocalho de Ofertas" in str(v) for t, v in enviados)
    assert ("album", 5) in enviados  # post fixado: capa + 3 + final
    assert estado["temas_recentes"] == {"brinquedos": "2026-11-09"}  # categoria com mais promoções

    # Dia 2: temático vira Reel (com capa), e o tema muda (brinquedos foi ontem)
    enviados.clear()
    assert conteudo.montar_e_enviar(TG(), 1, estado, datetime(2026, 11, 10, 10, tzinfo=FUSO), rng=random.Random(1))
    assert any(t == "video" for t, v in enviados) and ("doc", "capa_reel.png") in enviados

    # Dia normal (segunda): 1 carrossel + 2 posts + Reel
    enviados.clear()
    estado.pop("pacote_usados"); estado.pop("temas_recentes")
    assert conteudo.montar_e_enviar(TG(), 1, estado, datetime(2026, 11, 16, 10, tzinfo=FUSO), rng=random.Random(1))
    assert sum(1 for t, v in enviados if t == "album") == 1
    assert any(t == "video" for t, v in enviados)
    assert sum(1 for t, v in enviados if t == "foto" and v and "post do produto" in v) == 2


def test_pacote_pausa_sem_fotos(monkeypatch):
    from datetime import datetime
    from bot import arte, conteudo
    monkeypatch.setattr(arte, "foto_de_capa", lambda temas, rng=None: None)
    itens = [{"id": f"MLB{i}", "titulo": "Brinquedo", "preco": 20.0, "de": 40.0, "desconto": 0.5,
              "link": "https://meli.la/x", "imagem": None, "categoria": "brinquedo"} for i in range(5)]
    msgs = []

    class TG:
        def enviar_texto(self, c, t, html=False, **k): msgs.append(t)

    assert not conteudo.montar_e_enviar(TG(), 1, {"vitrine": {"itens": itens}}, datetime(2026, 11, 9, 10, tzinfo=FUSO))
    assert "pausado" in msgs[0]


def test_variedade_nicho_e_essenciais():
    from bot.ofertas import essencial, tipo_produto
    from bot.filtros import motivo_bloqueio
    assert motivo_bloqueio("Taco De Sinuca Bilhar Profissional Com Capa")
    assert tipo_produto("Babá Eletrônica Monitor 2.4") == tipo_produto("Baba Eletronica Baby Monitor Vb603")
    assert tipo_produto("Banheira Plástica Acqua Trio") == "banheira"
    assert essencial("Fralda Pom Pom Protek G 68 Unidades") and not essencial("Guitarra Infantil")


def test_areas_novas_filtros_e_comando():
    from bot.filtros import fora_da_faixa, motivo_bloqueio
    from bot import descoberta

    assert motivo_bloqueio("Jogo GTA V PS5 Mídia Física")
    assert motivo_bloqueio("Camisa Flamengo Tailandesa 2026")
    assert fora_da_faixa("Console Nintendo Switch OLED", "game") is None
    assert fora_da_faixa("Booster Cartas Pokémon Escarlate", "game") is None
    assert fora_da_faixa("Óculos de Natação Speedo Vanquisher", "esporte", "infantil")
    assert fora_da_faixa("Óculos de Natação Infantil Speedo", "esporte", "infantil") is None

    class MLAreas:
        def mais_vendidos(self, c):
            return [("catalogo", f"MLB{c}x{k}") for k in range(3)]

    achados = descoberta.descobrir_areas(MLAreas(), log=lambda m: None)
    cats = {d["categoria"] for d in achados.values()}
    assert {"roupa", "game", "livro", "escola", "esporte", "casa", "festa"} <= cats
    assert fora_da_faixa("Headset Gamer RGB Nintendo Switch", "game")
    assert fora_da_faixa("Lanterna Tática LED Recarregável", "roupa", "infantil")


def test_buscar_pegar_e_vigiar():
    from bot import busca, lote

    class MLBusca:
        def categoria_da_busca(self, termo):
            return "MLB1387", "Cadeiras de Bebê para Carro"

        def mais_vendidos(self, c):
            return [("catalogo", "MLB2"), ("catalogo", "MLB9")]

        def buscar_produtos(self, termo, limite=10):
            return [("MLB1", "Cadeirinha A"), ("MLB2", "Cadeirinha B")]

        def catalogo(self, pid, titulo=None, imagem=None):
            nomes = {"MLB1": "Cadeirinha Isofix A", "MLB2": "Cadeirinha Isofix B", "MLB9": "Cadeirinha Isofix C"}
            return InfoProduto(pid, nomes[pid], 100, 150 if pid == "MLB2" else None, None, True, item_id=pid + "0")

    e = est.novo()
    txt = busca.buscar("cadeirinha isofix", MLBusca(), e)
    assert "1. Cadeirinha Isofix B" in txt and "top 1 mais vendidos" in txt
    tg = TGFalso()
    assert busca.pegar("1 2", tg, e, cfg_cmd(), AGORA) is None
    assert len(e["lote_extra"]["ids"]) == 2 and e["manuais"]["MLB2"]["pedido"]
    ok, msg = lote.aplicar_resposta(e, "https://meli.la/aaa https://meli.la/bbb")
    assert ok and e["links"]["MLB2"] == "https://meli.la/aaa"
    assert "Vigiando" in busca.vigiar("Carrinho Travel System", e)
    busca.atualizar_vigias(MLBusca(), e, AGORA)
    assert e["manuais"]["MLB1"]["vigia"] == "carrinho travel system"
    assert "Parei" in busca.parar("carrinho travel system", e)


POST_LISTA = """Listão Cupom Mercado Livre #anúncio

R$ 50 OFF em R$ 349: MELIMAISPREDD (Exclusivo Meli+)
✅ Ative aqui para ajudar o grupo: https://mercadolivre.com.br/sec/31qRqvp

10% OFF em R$79, Limitado a R$100: HOJEMESMO
12% OFF, limite de R$200 (Tecnologia): CUPOMTECH
20%OFF (Móveis e Bebês e Pets): MOVEIS0511 BEBESPETS0511
15%OFF (Moda e Beleza): MODABELEZA0511
25% OFF Limitado a R$40 (Full) - FULL0411 (quem resgatou ontem)
👇Grupo só com cupom Mercado Livre: https://chat.whatsapp.com/XYZ"""


def test_parse_lista_de_terceiros():
    from bot import cupons_ml
    c = {x["codigo"]: x for x in cupons_ml.parse_lista(POST_LISTA, AGORA)}
    assert set(c) == {"MELIMAISPREDD", "HOJEMESMO", "CUPOMTECH", "MOVEIS0511", "BEBESPETS0511", "MODABELEZA0511"}
    assert c["MELIMAISPREDD"]["desconto"] == "R$50 OFF" and c["MELIMAISPREDD"]["minimo"] == "R$349"
    assert c["MELIMAISPREDD"]["nota"] == "Exclusivo Meli+"
    assert c["HOJEMESMO"]["minimo"] == "R$79" and c["HOJEMESMO"]["maximo"] == "R$100"
    assert c["BEBESPETS0511"]["validade"] == AGORA.replace(hour=23, minute=59, second=0)
    assert all(x["link"] is None for x in c.values())  # nunca repassa o link de quem postou
    assert cupons_ml.relevante(c["BEBESPETS0511"]) and not cupons_ml.relevante(c["CUPOMTECH"])


def test_canais_configurados(monkeypatch):
    from bot import cupons_ml
    monkeypatch.setenv("TG_CANAL_CUPONS", "https://t.me/+abc")
    monkeypatch.setenv("CUPONS_CANAIS_EXTRA", "https://t.me/cupombr, @outro")
    cs = cupons_ml.canais_configurados()
    assert [(c, k) for c, k, _ in cs] == [("https://t.me/+abc", "cupons_ml_ultimo"),
                                          ("cupombr", "cupons_extra_ultimo:cupombr"),
                                          ("outro", "cupons_extra_ultimo:outro")]
    assert cs[1][2] is cupons_ml.parse_lista


def test_cupom_de_terceiros_postado_sem_link():
    from bot import cupons_ml
    e, tg = est.novo(), TGCmd()
    n = cupons_ml.tratar_mensagem(POST_LISTA, tg, cfg_cmd(), e, AGORA, log=lambda m: None,
                                  parser=cupons_ml.parse_lista)
    canal = [t for c, t in tg.textos if c == "@canal"][0]
    assert n == 5 and "BEBESPETS0511" in canal and "CUPOMTECH" not in canal
    assert "mercadolivre.com.br/sec" not in canal and "whatsapp" not in canal
    assert "Exclusivo Meli+" in canal


def test_fila_whatsapp(tmp_path, monkeypatch):
    import json
    from bot import whatsapp
    monkeypatch.delenv("WA_FILA", raising=False)
    assert whatsapp.enfileirar("oi") is False  # sem fila configurada, não faz nada
    monkeypatch.setenv("WA_FILA", str(tmp_path / "fila"))
    assert whatsapp.enfileirar("*Oferta*", "https://img/x.jpg", AGORA)
    itens = [json.loads(p.read_text()) for p in (tmp_path / "fila").glob("*.json")]
    assert itens == [{"texto": "*Oferta*", "imagem": "https://img/x.jpg", "criado": AGORA.isoformat(), "loja": "ml"}]


def test_cupons_vao_para_fila_do_whatsapp(tmp_path, monkeypatch):
    from bot import cupons_ml
    monkeypatch.setenv("WA_FILA", str(tmp_path))
    e, tg = est.novo(), TGCmd()
    cupons_ml.tratar_mensagem(POST_LISTA, tg, cfg_cmd(), e, AGORA, log=lambda m: None, parser=cupons_ml.parse_lista)
    textos = [p.read_text() for p in tmp_path.glob("*.json")]
    assert len(textos) == 1 and "BEBESPETS0511" in textos[0] and "mercadolivre.com.br/sec" not in textos[0]


def test_cupom_de_lista_que_melhorou_atualiza_o_post():
    from bot import cupons_ml
    e, tg = est.novo(), TGCmd()
    cupons_ml.tratar_mensagem(POST_LISTA, tg, cfg_cmd(), e, AGORA, log=lambda m: None, parser=cupons_ml.parse_lista)
    novo = POST_LISTA.replace("R$ 50 OFF em R$ 349", "R$70 OFF em R$ 349")
    n = cupons_ml.tratar_mensagem(novo, tg, cfg_cmd(), e, AGORA, log=lambda m: None, parser=cupons_ml.parse_lista)
    assert n == 0  # não posta de novo, só atualiza
    avisos = [t for c, t in tg.textos if c == "@canal" and "Melhorou" in t]
    assert avisos and "R$70 OFF" in avisos[-1]
    # Repetido sem mudança: nada acontece
    antes = len(tg.textos)
    cupons_ml.tratar_mensagem(novo, tg, cfg_cmd(), e, AGORA, log=lambda m: None, parser=cupons_ml.parse_lista)
    assert len(tg.textos) == antes


def test_itens_de_casa_que_vazam_das_categorias_de_bebe():
    from bot.filtros import fora_da_faixa
    fora = ["Extensor de Torneira Cromado e Inox com Mangueira Flexível de 15 cm Para Pia",
            "Jogo De Lençol Queen 3 Peças 400 Fios Com Elástico Hotel",
            "Banheira Portátil Dobrável para Spa e Gelo de Alta Qualidade",
            "Kit 2 Redes Nylon Resistente Proteção Pássaros Morcegos",
            "Tenda Mosquiteiro Dobrável Para Cama Casal Solteiro",
            "Jogo De Mantimento 5 Potes Personalizado"]
    for t in fora:
        assert fora_da_faixa(t, "higiene"), t
    dentro = ["Banheira De Bebê Dobrável Portátil Com Termômetro",
              "Berço Co-sleeper Acoplado à Cama de Casal",
              "Fralda Pampers Confort Sec M 80 Unidades",
              "Rede de Proteção para Banho Bebê Toki Baby",
              "Jogo Banco Imobiliário Grande Estrela"]
    for t in dentro:
        assert fora_da_faixa(t, "higiene") is None, t


def test_cupom_na_oferta_so_quando_faz_sentido():
    from types import SimpleNamespace as N
    from bot import cupom_oferta as co, cupons, mensagens
    e = est.novo()
    blocos = [
        ("GERAL30", "<b>🎟️ GERAL30</b> 👉 <b>30% OFF</b>\nCompra mín.: R$1 · Desconto máx.: R$500", None),
        ("AUTO70", "<b>🎟️ AUTO70</b> 👉 <b>R$70 OFF</b>\n📂 Automotivo", None),
        ("BEBES20", "<b>🎟️ BEBES20</b> 👉 <b>20% OFF</b>\n📂 Móveis e Bebês e Pets\nCompra mín.: R$79 · Desconto máx.: R$60", None),
        ("SITETODO10", "<b>🎟️ SITETODO10</b> 👉 <b>R$10 OFF</b>\nCompra mín.: R$79", None),
        ("MELI50", "<b>🎟️ MELI50</b> 👉 <b>R$50 OFF</b>\n⭐ Exclusivo Meli+\nCompra mín.: R$100", None),
    ]
    cupons.publicar(TGCmd(), cfg_cmd(), e, "t", blocos, AGORA)
    banheira = N(titulo="Banheira", preco=389.9, preco_de=499.9, categoria="higiene", link="x", desconto=.2)
    cp = co.melhor_cupom(e, banheira, AGORA)
    assert cp["codigo"] == "BEBES20" and cp["economia"] == 60 and cp["preco"] == 329.9  # 20% limitado a R$60
    barato = N(titulo="Babador", preco=21.6, preco_de=30, categoria="alimentacao", link="x", desconto=.2)
    assert co.melhor_cupom(e, barato, AGORA) is None  # abaixo do mínimo de todos
    lego = N(titulo="LEGO", preco=99.0, preco_de=120, categoria="brinquedo", link="x", desconto=.2)
    assert co.melhor_cupom(e, lego, AGORA)["codigo"] == "SITETODO10"  # só o do site todo vale
    banheira.cupom = cp
    texto = mensagens.montar_whatsapp(banheira)
    assert "BEBES20" in texto and "R$ 329,90" in texto and "elegível" in texto


def test_resumo_traz_o_whatsapp(tmp_path):
    import json
    from bot import comandos
    hoje, ontem = AGORA.date().isoformat(), (AGORA.date() - timedelta(days=1)).isoformat()
    arq = tmp_path / "wa.json"
    arq.write_text(json.dumps({"dia": hoje, "enviados": 3, "membros": {ontem: 40, hoje: 47},
                               "apagados": {hoje: 2}, "conectado": True}))
    txt = "\n".join(comandos._resumo_whatsapp(AGORA, arq))
    assert "47" in txt and "+7 desde ontem" in txt and "Posts no grupo hoje: <b>3</b>" in txt
    assert "apagados: 2" in txt and "Conectado" in txt
    assert comandos._resumo_whatsapp(AGORA, tmp_path / "nao_existe.json") == []


def test_pagina_de_numeros(tmp_path):
    import json
    from bot import numeros
    e = est.novo()
    for k in range(5):
        dia = AGORA - timedelta(days=4 - k)
        e.setdefault("membros_hist", {})[dia.date().isoformat()] = 100 + k * 3
        est.registrar_post(e, f"MLB{k}", 50.0, dia, "Banheira Dobrável", 0.3)
    wa = tmp_path / "wa.json"
    hoje = AGORA.date().isoformat()
    wa.write_text(json.dumps({"dia": hoje, "enviados": 2, "membros": {hoje: 15}, "conectado": True}))
    arq = tmp_path / "docs" / "numeros.html"
    assert numeros.talvez_publicar(e, AGORA, arquivo=arq, arquivo_wa=wa)
    h = arq.read_text()
    assert "noindex" in h and "Números do Chocalho" in h and ">112<" in h  # último total do Telegram
    assert "▲ +3 desde ontem" in h and "Conectado" in h and "polyline" in h
    assert not numeros.talvez_publicar(e, AGORA, arquivo=arq, arquivo_wa=wa)  # menos de 10 min depois
    assert e["hist_dia"][hoje]["posts"] == 1


def test_shopee_assina_e_converte():
    import hashlib, json
    from bot import shopee

    class R:
        def __init__(self, j): self._j = j
        def json(self): return self._j

    class S:
        def post(self, url, data, headers, timeout):
            self.url, self.data, self.headers = url, data, headers
            return R({"data": {"productOfferV2": {"nodes": [
                {"itemId": 123, "productName": "Body Bebê Algodão", "priceMin": "35.00",
                 "priceDiscountRate": 30, "commissionRate": "0.08", "sales": 1500, "ratingStar": "4.8",
                 "imageUrl": "https://x/img.jpg", "offerLink": "https://s.shopee.com.br/abc", "shopType": [1]},
                {"itemId": 9, "productName": "Sem link", "priceMin": "10"}]}}})

    s = S()
    cli = shopee.Shopee("111", "segredo", session=s)
    ps = cli.buscar('body "bebê"')
    assert len(ps) == 1 and ps[0].id == "SHP123" and ps[0].preco_de == 50.0 and ps[0].loja_oficial
    assert ps[0].link == "https://s.shopee.com.br/abc"  # link da Shopee intacto
    cab = s.headers["Authorization"]
    ts = cab.split("Timestamp=")[1].split(",")[0]
    esperado = hashlib.sha256(f"111{ts}{s.data.decode()}segredo".encode()).hexdigest()
    assert cab.startswith("SHA256 Credential=111, ") and cab.endswith(f"Signature={esperado}")
    assert '\\"bebê\\"' in json.loads(s.data)["query"] or 'bebê' in json.loads(s.data)["query"]


def _produto_shopee(**k):
    from bot.shopee import ProdutoShopee
    base = dict(id="SHP1", titulo="Brinquedo Educativo Montessori Infantil", preco=34.99, preco_de=99.0,
                desconto=0.65, comissao=0.08, vendas=7733, nota=4.9, imagem="https://x/i.jpg",
                link="https://s.shopee.com.br/a", loja="Loja", loja_oficial=True, preco_max=49.9,
                link_produto="https://shopee.com.br/product/1/2")
    base.update(k)
    return ProdutoShopee(**base)


def test_shopee_regras_e_post():
    from bot import shopee_ofertas as so
    assert so.aprovado(_produto_shopee()) is None
    assert so.aprovado(_produto_shopee(nota=4.5)) == "nota baixa"
    assert so.aprovado(_produto_shopee(vendas=300)) == "poucas vendas"
    assert so.aprovado(_produto_shopee(comissao=0.03)) == "comissão baixa"
    assert so.aprovado(_produto_shopee(titulo="Mamadeira Anticólica Infantil"))  # NBCAL
    e = est.novo()
    o = so.para_oferta(_produto_shopee(), e, AGORA, "https://s.shopee.com.br/tg", "https://s.shopee.com.br/wa")
    t = mensagens.montar_telegram(o, random.Random(1))
    w = mensagens.montar_whatsapp(o, random.Random(1))
    assert "A partir de <b>R$ 34,99</b>" in t and "De " not in t  # sem o "de" inflado da Shopee
    assert "Ver oferta na Shopee" in t and "s.shopee.com.br/tg" in t
    assert "s.shopee.com.br/wa" in w and "+7 mil vendidos" in w and "⭐ 4,9" in w
    # "de/por" só com queda vista pelo próprio bot
    est.registrar_preco(e, "SHP1", 50.0, AGORA - timedelta(days=5))
    o2 = so.para_oferta(_produto_shopee(preco_max=0), e, AGORA)
    assert o2.preco_de == 50.0 and "De <s>R$ 50,00</s>" in mensagens.montar_telegram(o2, random.Random(1))


def test_shopee_rodar_posta_por_cima(monkeypatch, tmp_path):
    from bot import shopee_ofertas as so
    monkeypatch.setenv("SHOPEE_ATIVO", "1")
    monkeypatch.setenv("WA_FILA", str(tmp_path))

    class Shp:
        def buscar(self, termo, **k):
            return [_produto_shopee(id="SHP1"), _produto_shopee(id="SHP2", titulo="Body Bebê Algodão Kit 3"),
                    _produto_shopee(id="SHP3", titulo="Fralda Descartável Infantil", nota=4.2)]

        def link_curto(self, url, subs):
            return f"https://s.shopee.com.br/{subs[0]}"

    class Tg:
        def __init__(self): self.posts = []
        def enviar_oferta(self, chat, legenda, imagem=None): self.posts.append(legenda)

    class Cfg:
        hora_inicio, hora_fim, repost_dias, intervalo_min, intervalo_max, canal = 8, 22, 3, 0, 0, "@c"

    e, tg = est.novo(), Tg()
    agora = AGORA.replace(hour=20)
    feitas = so.rodar(Cfg, tg, e, agora, rng=random.Random(1), shp=Shp(), log=lambda m: None)
    assert [o.id for o in feitas] == ["SHP1", "SHP2"] and len(tg.posts) == 2  # SHP3: nota baixa
    assert e["contagem_dia"] == {}  # não gasta o limite do Mercado Livre
    assert e["hist_dia"][agora.date().isoformat()]["shopee"] == 2
    import json
    itens = [json.loads(p.read_text()) for p in tmp_path.glob("*.json")]
    assert {i["loja"] for i in itens} == {"shopee"} and all("s.shopee.com.br/whatsapp" in i["texto"] for i in itens)
    assert so.rodar(Cfg, tg, e, agora, rng=random.Random(1), shp=Shp(), log=lambda m: None) == []  # sem repetir


def test_cupom_marcado_como_geral_pelo_admin():
    from types import SimpleNamespace as N
    from bot import comandos, cupom_oferta as co, cupons
    e = est.novo()
    blocos = [
        ("CORREHOJE", "<b>🎟️ CORREHOJE</b> 👉 <b>20% OFF</b>\nCompra mín.: R$79 · Desconto máx.: R$60", None),
        ("SITETODO10", "<b>🎟️ SITETODO10</b> 👉 <b>R$10 OFF</b>\nCompra mín.: R$79", None),
    ]
    cupons.publicar(TGCmd(), cfg_cmd(), e, "t", blocos, AGORA)
    almofada = N(titulo="Almofada de banho", preco=81.01, preco_de=147.9, categoria="higiene", link="x", desconto=.45)
    assert co.melhor_cupom(e, almofada, AGORA)["codigo"] == "SITETODO10"  # sem a marca, o geral fica de fora
    r = comandos.tratar_texto("geral correhoje", None, None, e, cfg_cmd(), AGORA)
    assert "CORREHOJE" in r and e["cupons"]["CORREHOJE"]["geral"]
    cp = co.melhor_cupom(e, almofada, AGORA)
    assert cp["codigo"] == "CORREHOJE" and cp["economia"] == 16.2 and cp["preco"] == 64.81
    barato = N(titulo="Babador", preco=40.0, preco_de=50, categoria="alimentacao", link="x", desconto=.2)
    assert co.melhor_cupom(e, barato, AGORA) is None  # o mínimo de R$79 continua valendo
    assert "Não achei" in comandos.tratar_texto("geral NAOEXISTE", None, None, e, cfg_cmd(), AGORA)
    comandos.tratar_texto("restrito CORREHOJE", None, None, e, cfg_cmd(), AGORA)
    assert co.melhor_cupom(e, almofada, AGORA)["codigo"] == "SITETODO10"


def _pagina_social(pid, preco, promocoes=None, rotulo=None, outro=False):
    import json
    price = {"current_price": {"value": preco}, "previous_price": {"value": preco * 2}}
    if rotulo:
        price["discount_label"] = {"text": rotulo}
    comps = [{"type": "title", "title": {"text": "Produto"}}, {"type": "price", "price": price}]
    if promocoes is not None:
        comps.append({"type": "promotions", "promotions": promocoes})
    card = {"metadata": {"id": "MLB999", "product_id": "MLB777" if outro else pid}, "components": comps}
    return '<html><script>{"polycards":' + json.dumps([card]) + ',"x":1}</script></html>'


def test_cupom_lido_da_pagina_do_anuncio():
    from types import SimpleNamespace as N
    from bot import cupom_oferta as co, mensagens
    preco_cupom = [{"type": "coupon", "text": "{1} com Cupom",
                    "values": [{"key": "1", "type": "price", "price": {"value": 127.08}}]}]
    cp = co.ler_cupom_pagina(_pagina_social("MLB1", 138.13, preco_cupom), "MLB1", 138.13)
    assert cp == {"origem": "pagina", "preco": 127.08, "economia": 11.05, "desconto": ""}
    # card de outro produto: não usa
    assert co.ler_cupom_pagina(_pagina_social("MLB1", 138.13, preco_cupom, outro=True), "MLB1", 138.13) is None
    # só percentual
    cp = co.ler_cupom_pagina(_pagina_social("MLB1", 62.89, [{"type": "coupon", "text": "8% OFF com Cupom"}]),
                             "MLB1", 62.89)
    assert cp["preco"] is None and cp["desconto"] == "8% OFF"
    # preço do card já com cupom (rótulo "44% OFF com Cupom") e menor que o nosso
    cp = co.ler_cupom_pagina(_pagina_social("MLB1", 72.66, rotulo="44% OFF com Cupom"), "MLB1", 80.0)
    assert cp["preco"] == 72.66 and cp["economia"] == 7.34
    # sem cupom / economia irrisória / página sem JSON
    assert co.ler_cupom_pagina(_pagina_social("MLB1", 83.18, None, "51% OFF"), "MLB1", 83.18) is None
    assert co.ler_cupom_pagina(_pagina_social("MLB1", 79.5, rotulo="com Cupom"), "MLB1", 80.0) is None
    assert co.ler_cupom_pagina("<html>bloqueado</html>", "MLB1", 80.0) is None
    # texto do post
    o = N(titulo="Barraca", preco=138.13, preco_de=197.83, desconto=.3, categoria="brinquedo", link="https://meli.la/x",
          cupom={"origem": "pagina", "preco": 127.08, "economia": 11.05, "desconto": ""})
    t = mensagens.montar_telegram(o)
    assert "Com cupom do anúncio: <b>R$ 127,08</b>" in t and "Ative o cupom na página" in t and "elegível" not in t
    o.cupom = {"origem": "pagina", "preco": None, "economia": 0.0, "desconto": "8% OFF"}
    assert "Tem cupom de *8% OFF* no anúncio" in mensagens.montar_whatsapp(o)


def test_escolhe_entre_cupom_do_anuncio_e_do_canal():
    from types import SimpleNamespace as N
    from bot import cupom_oferta as co, cupons

    class Sessao:
        def __init__(self, texto):
            self.texto = texto

        def get(self, *a, **k):
            return N(text=self.texto)

    e = est.novo()
    cupons.publicar(TGCmd(), cfg_cmd(), e, "t",
                    [("SITETODO10", "<b>🎟️ SITETODO10</b> 👉 <b>R$10 OFF</b>\nCompra mín.: R$79", None)], AGORA)
    o = N(id="MLB1", titulo="Barraca", preco=138.13, categoria="brinquedo", link="https://meli.la/x")
    pag = _pagina_social("MLB1", 138.13, [{"type": "coupon", "text": "{1} com Cupom",
                                           "values": [{"type": "price", "price": {"value": 120.0}}]}])
    assert co.escolher_cupom(e, o, AGORA, Sessao(pag))["origem"] == "pagina"  # 18,13 > 10
    pag = _pagina_social("MLB1", 138.13, [{"type": "coupon", "text": "{1} com Cupom",
                                           "values": [{"type": "price", "price": {"value": 134.0}}]}])
    assert co.escolher_cupom(e, o, AGORA, Sessao(pag))["codigo"] == "SITETODO10"  # canal economiza mais
    assert co.escolher_cupom(e, o, AGORA, Sessao("<html></html>"))["codigo"] == "SITETODO10"
    o.link = "https://produto.mercadolivre.com.br/x?matt_word=y"  # link direto: nem abre a página
    assert co.escolher_cupom(e, o, AGORA, Sessao(pag))["codigo"] == "SITETODO10"


def test_bone_adulto_bloqueado():
    from bot.filtros import fora_da_faixa, motivo_bloqueio
    assert motivo_bloqueio("Boné New Era 9FORTY Aba Curva Yankees")
    assert fora_da_faixa("Boné Aba Reta Juvenil Snapback", "roupa")
    assert fora_da_faixa("Boné Infantil Dinossauro Ajustável", "roupa") is None
    assert fora_da_faixa("Boneca Bebê Reborn Menina", "brinquedo") is None


def test_mesmo_produto_outro_anuncio_nao_repete():
    from datetime import datetime, timedelta, timezone
    from bot import estado as est
    from bot.ofertas import parecido
    fuso = timezone(timedelta(hours=-3))
    agora = datetime(2026, 11, 11, 15, 0, tzinfo=fuso)
    e = {"postados": {"MLB1": {"quando": (agora - timedelta(days=1)).isoformat(),
                               "titulo": "Kit 3 Mantas Cobertor Microfibra Infantil Bebê Estampado", "preco": 40.0}},
         "shopee": {"titulos": {"SHP9": {"quando": (agora - timedelta(days=2)).isoformat(),
                                         "titulo": "Babá Eletrônica Baby Monitor Vb603 Visão Noturna"}}}}
    assert est.repetido(e, "Kit 3 Mantas Cobertor Microfibra Infantil Bebê Estampa Azul", agora)
    assert est.repetido(e, "Baba Eletronica Baby Monitor Vb603 Visao Noturna Dual Audio", agora)
    assert not est.repetido(e, "Mochila Escolar Infantil Dinossauro", agora)
    # outro anúncio do mesmo produto pode sair se estiver 5% mais barato
    assert est.repetido(e, "Kit 3 Mantas Cobertor Microfibra Infantil Bebê", agora, preco=39.0)
    assert not est.repetido(e, "Kit 3 Mantas Cobertor Microfibra Infantil Bebê", agora, preco=37.0)
    # depois de 3 dias pode voltar
    assert not est.repetido(e, "Kit 3 Mantas Cobertor Microfibra Infantil Bebê", agora + timedelta(days=3))
    assert not parecido("Patinete Infantil 3 Rodas Led", "Boneca Reborn Realista")


def test_preco_tipico_usa_mediana_e_ignora_pico():
    e = est.novo()
    for dias, preco in [(20, 100.0), (6, 140.0), (4, 100.0)]:  # pico de 2 dias antes da "promoção"
        est.registrar_preco(e, "MLB9", preco, AGORA - timedelta(days=dias))
    tipico, dias = est.preco_tipico(e, "MLB9", AGORA)
    assert tipico == 100.0 and dias == 20
    assert est.preco_tipico(e, "MLB0", AGORA) == (None, 0)


def test_queda_real_pesa_na_pontuacao():
    from bot.ofertas import pontuacao
    e = est.novo()
    est.registrar_preco(e, "MLB1", 70.0, AGORA - timedelta(days=10))  # sempre 70: "-30%" é de fachada
    fachada = avaliar(prod(), info(70, 100), e, AGORA)
    assert round(fachada.queda_real, 2) == 0 and fachada.dias_hist == 10
    e2 = est.novo()
    est.registrar_preco(e2, "MLB1", 100.0, AGORA - timedelta(days=10))  # era 100 de verdade
    real = avaliar(prod(), info(70, 100), e2, AGORA)
    assert pontuacao(real) > pontuacao(fachada) * 2
    e3 = est.novo()
    est.registrar_preco(e3, "MLB1", 70.0, AGORA - timedelta(days=2))  # pouco histórico: não mexe
    novo = avaliar(prod(), info(70, 100), e3, AGORA)
    assert pontuacao(novo) == pytest.approx(pontuacao(avaliar(prod(), info(70, 100), est.novo(), AGORA)))


def test_quem_sai_dos_mais_vendidos_continua_acompanhado():
    from bot.main import acompanhar_quem_saiu
    e = est.novo()
    e["descobertos"] = {"MLB1": {"tipo": "catalogo", "categoria": "brinquedo", "pos": 2},
                        "MLB2": {"tipo": "catalogo", "categoria": "roupa", "pos": 1, "regra": "infantil"}}
    acompanhar_quem_saiu(e, {"MLB1": {"tipo": "catalogo", "categoria": "brinquedo", "pos": 0}}, AGORA)
    assert list(e["acompanhados"]) == ["MLB2"] and e["acompanhados"]["MLB2"]["regra"] == "infantil"
    # depois de 30 dias para de acompanhar; se voltar aos mais vendidos, sai da lista de acompanhados
    acompanhar_quem_saiu(e, {"MLB2": {}}, AGORA)
    assert "MLB2" not in e["acompanhados"]


def test_shopee_acompanha_e_traz_queda_real():
    from bot import shopee_ofertas as so
    e = est.novo()
    so._marcar_acompanhado(e, _produto_shopee(id="SHP7"), AGORA - timedelta(days=12))
    est.registrar_preco(e, "SHP7", 50.0, AGORA - timedelta(days=12))

    class Shp:
        def item(self, iid):
            assert iid == "7"
            return _produto_shopee(id="SHP7", preco=40.0)

    caiu = so.acompanhar(Shp(), e, AGORA, log=lambda m: None)
    assert [p.id for p in caiu] == ["SHP7"]
    assert e["precos"]["SHP7"]["historico"][-1][1] == 40.0
    assert e["shopee"]["acompanhados"]["SHP7"]["visto"].startswith(AGORA.date().isoformat())


def test_cupom_sem_data_vale_ate_o_fim_do_dia_seguinte():
    from datetime import timedelta
    from bot import cupons
    e = est.novo()
    tg = TGCmd()
    cupons.publicar(tg, cfg_cmd(), e, "t", [("SEMDATA10", "<b>🎟️ SEMDATA10</b> 👉 10% OFF", None)], AGORA)
    fim = (AGORA + timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)
    assert e["cupons"]["SEMDATA10"]["validade"] == fim.isoformat(timespec="minutes")
    # cupom antigo, gravado sem validade: ganha o prazo pela data do post e encerra depois dele
    e["cupons"]["SEMDATA10"]["validade"] = None
    cupons.verificar(tg, cfg_cmd(), e, fim - timedelta(minutes=5))
    assert e["cupons"]["SEMDATA10"]["status"] == "ativo"
    cupons.verificar(tg, cfg_cmd(), e, fim + timedelta(minutes=1))
    assert e["cupons"]["SEMDATA10"]["status"] == "encerrado"


def test_foto_de_capa_evita_as_ja_usadas(tmp_path, monkeypatch):
    import random
    from bot import arte
    monkeypatch.setattr(arte, "USADAS", tmp_path / "usadas.json")
    fotos = sorted((arte.CAPAS / "passeio").glob("*.jpg"))
    for f in fotos[:-1]:
        arte.registrar_capa(f"passeio/{f.name}", "2026-01-01")
    for _ in range(5):
        assert arte.foto_de_capa(["passeio"], random.Random()).nome == f"passeio/{fotos[-1].name}"
    arte.registrar_capa(f"passeio/{fotos[-1].name}", "2026-02-01")
    assert arte.foto_de_capa(["passeio"]).nome == f"passeio/{fotos[0].name}"  # todas usadas: a mais antiga


def test_capas_novas_desenham():
    from PIL import Image
    from bot import tiktok
    foto = Image.new("RGB", (1200, 1600), (230, 220, 210))
    for estilo in ("faixas", "grandes", "classico"):
        img = tiktok.capa(foto, "Eles crescem\nrápido demais", "roupinhas de 0 a 6 meses", estilo=estilo, destaque=["rápido"])
        assert img.size == (1080, 1350)


def test_titulo_da_capa_prefere_duas_linhas():
    from PIL import Image, ImageDraw
    from bot import tiktok
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for tamanhos, larg in (((88, 84, 78, 72, 66, 60), 900), ((122, 112, 104, 96, 88, 80, 74), 936)):
        _, _, linhas = tiktok._linhas_caps(d, "O segredo daquele cheirinho de bebê", tamanhos, larg, max_linhas=4)
        assert len(linhas) == 2


def test_whatsapp_oferta_com_previa_do_link(tmp_path, monkeypatch):
    import json
    from bot import whatsapp
    monkeypatch.setenv("WA_FILA", str(tmp_path))
    from bot import ofertas
    o = ofertas.Oferta(id="MLB1", titulo="Banheira Dobrável", preco=99.9, preco_de=None, desconto=0,
                       abaixo_do_habitual=None, menor_preco_historico=False, link="https://meli.la/abc",
                       imagem="https://img/x.jpg", categoria="higiene")
    assert whatsapp.enfileirar_oferta(o, "*Oferta*\n👉 https://meli.la/abc\n_#publi_", AGORA)
    item = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert item["preview"] == {"link": "https://meli.la/abc", "titulo": "Banheira Dobrável", "imagem": "https://img/x.jpg"}
    assert item["imagem"] == "https://img/x.jpg"  # reserva, se a prévia falhar


def test_tipo_do_dia_vale_para_ml_e_shopee():
    from bot.ofertas import tipo_produto, tipos_do_dia
    assert tipo_produto("Maleta 48 Carrinhos + Tapete Pista 40x60") == tipo_produto(
        "Kit 48 Carrinhos Miniatura Nanotoyzzz Metal Fricção 1:64") == "carrinho de brinquedo"
    assert tipo_produto("Kit 3 Brinquedo Sensorial Ventosa") == "sensorial"
    e = est.novo()
    e["shopee"] = {"titulos": {"SHP1": {"titulo": "Kit 48 Carrinhos Miniatura Metal", "quando": AGORA.isoformat()}}}
    assert "carrinho de brinquedo" in tipos_do_dia(e, AGORA)
    assert "carrinho de brinquedo" not in tipos_do_dia(e, AGORA + timedelta(days=1))


def test_sutia_bloqueado():
    assert motivo_bloqueio("Kits Sutiãs Infantil Juvenil Algodão Cotton Liso")
    assert motivo_bloqueio("Sutiã Infantil Top Menina")
    assert motivo_bloqueio("Body Bebê Algodão Kit 3") is None


def test_baby_doll_adulto_bloqueado():
    from bot.filtros import fora_da_faixa
    for t in ["Baby Doll Short Doll Americano Gola V Liso Pijama Feminino",
              "Kit 4 Conjuntos Femininos Baby Doll Pijama Short Doll Estampado Sem Bojo",
              "Camiseta Baby Look Feminina Lisa", "Pijama Plus Size Feminino"]:
        assert fora_da_faixa(t, "", "infantil"), t
    for t in ["Pijama Infantil Bebê Menina Manga Curta com Estampas Fofas",
              "Baby Doll Infantil Menina Estampado", "Kit 2 Pijamas Manga Longa Bebê Menino"]:
        assert fora_da_faixa(t, "", "infantil") is None, t


def test_instagram_nao_vaza_token():
    from bot.instagram import Instagram, InstagramErro

    class Resp:
        status_code = 400
        headers = {"content-type": "application/json"}
        text = ""

        def json(self):
            return {"error": {"message": "token SEGREDO123 inválido", "code": 190}}

    class Sessao:
        def get(self, *a, **k):
            return Resp()

    ig = Instagram("SEGREDO123", "42", session=Sessao())
    try:
        ig.conta()
    except InstagramErro as e:
        assert "SEGREDO123" not in str(e) and "190" in str(e)
    else:
        raise AssertionError("deveria falhar")


def test_instagram_publica_carrossel():
    from bot.instagram import Instagram

    class R:
        def __init__(self, j): self.j, self.status_code, self.headers, self.text = j, 200, {"content-type": "application/json"}, ""
        def json(self): return self.j

    class S:
        def __init__(self): self.posts, self.n = [], 0
        def post(self, url, data, timeout):
            self.posts.append((url.rsplit("/", 1)[-1], {k: v for k, v in data.items() if k != "access_token"}))
            self.n += 1
            return R({"id": f"id{self.n}"})
        def get(self, url, params, timeout):
            return R({"status_code": "FINISHED", "permalink": "https://instagram.com/p/x"})

    s = S()
    mid, link = Instagram("tok", "123", session=s).publicar_carrossel(["https://a/1.jpg", "https://a/2.jpg"], "Legenda",
                                                                     dormir=lambda x: None)
    assert link == "https://instagram.com/p/x" and mid == "id4"
    assert s.posts[0] == ("media", {"image_url": "https://a/1.jpg", "is_carousel_item": "true"})
    assert s.posts[2] == ("media", {"media_type": "CAROUSEL", "children": "id1,id2", "caption": "Legenda"})
    assert s.posts[3] == ("media_publish", {"creation_id": "id3"})


class _IGFalso:
    """Imita a API do Instagram: 'saves' e 'ig_reels_avg_watch_time' falham sempre."""
    user_id = "42"

    def __init__(self):
        self.chamadas = []

    def _get(self, caminho, **params):
        from bot.instagram import InstagramErro
        self.chamadas.append((caminho, params))
        if caminho.endswith("/insights"):
            nomes = params["metric"].split(",")
            if "saves" in nomes or "ig_reels_avg_watch_time" in nomes:
                raise InstagramErro("HTTP 400: métrica inválida (código 100)")
            if params.get("breakdown"):
                return {"data": [{"name": n, "total_value": {"value": 5, "breakdowns": [
                    {"results": [{"dimension_values": ["FOLLOWER"], "value": 4},
                                 {"dimension_values": ["NON_FOLLOWER"], "value": 1}]}]}} for n in nomes]}
            if caminho.startswith("42/"):
                return {"data": [{"name": n, "total_value": {"value": 10}} for n in nomes]}
            return {"data": [{"name": n, "values": [{"value": 7}]} for n in nomes]}
        if caminho == "42/stories":
            return {"data": []}
        if caminho == "42/media":
            return {"data": [
                {"id": "p1", "media_product_type": "FEED", "media_type": "CAROUSEL_ALBUM",
                 "timestamp": "2026-11-12T15:00:00+0000", "caption": "Kit enxoval\ncom 10 peças", "permalink": "x"},
                {"id": "p2", "media_product_type": "REELS", "media_type": "VIDEO",
                 "timestamp": "2026-11-10T15:00:00+0000", "permalink": "y"},
                {"id": "velho", "media_product_type": "FEED", "timestamp": "2026-09-01T15:00:00+0000"},
            ], "paging": {}}
        if caminho == "42":
            return {"username": "chocalhodeofertas", "followers_count": 9, "follows_count": 3, "media_count": 9}
        raise AssertionError(caminho)

    metricas = None  # preenchido abaixo com o método real


def _ig_falso():
    from bot.instagram import Instagram
    ig = _IGFalso()
    ig.metricas = Instagram.metricas.__get__(ig)
    ig.posts_desde = Instagram.posts_desde.__get__(ig)
    ig.stories = Instagram.stories.__get__(ig)
    ig.conta = Instagram.conta.__get__(ig)
    ig.CAMPOS_MIDIA = Instagram.CAMPOS_MIDIA
    return ig


def test_insights_ig_coleta_dia_e_registra_ausentes(tmp_path):
    from datetime import datetime
    from bot import insights_ig
    agora = datetime(2026, 11, 13, 8, 5, tzinfo=insights_ig.FUSO)
    assert insights_ig.rodar(ig=_ig_falso(), agora=agora, pasta=tmp_path) == 0
    dados = json.loads((tmp_path / "2026-11-12.json").read_text())
    assert dados["dia"] == "2026-11-12" and dados["conta"]["seguidores"] == 9
    assert dados["conta_no_dia"]["metricas"]["reach"] == 10
    assert "saves" in dados["conta_no_dia"]["ausentes"]  # falhou e ficou registrado
    assert dados["conta_no_dia"]["metricas"]["follows_and_unfollows"]["FOLLOWER"] == 4
    assert [p["id"] for p in dados["posts"]] == ["p1", "p2"]  # o de setembro fica de fora
    assert dados["posts"][0]["legenda"] == "Kit enxoval com 10 peças"
    assert dados["posts"][1]["formato"] == "REELS" and "ig_reels_avg_watch_time" in dados["posts"][1]["ausentes"]
    assert dados["posts"][1]["metricas"]["reach"] == 7
    assert dados["conta_no_dia"]["janela"]["inicio"].startswith("2026-11-12T00:00:00-03:00")


def test_insights_ig_nao_coleta_o_mesmo_dia_duas_vezes(tmp_path):
    from datetime import datetime
    from bot import insights_ig
    agora = datetime(2026, 11, 13, 8, 5, tzinfo=insights_ig.FUSO)
    ig = _ig_falso()
    insights_ig.rodar(ig=ig, agora=agora, pasta=tmp_path)
    n = len(ig.chamadas)
    insights_ig.rodar(ig=ig, agora=agora, pasta=tmp_path)
    assert len(ig.chamadas) == n + 1  # só a checagem de stories


class _TGFalso:
    def __init__(self):
        self.textos, self.edicoes, self.toques = [], [], []

    def enviar_texto(self, chat, texto, html=False, botoes=None, responder_a=None, acoes=None):
        self.textos.append((texto, acoes))
        return {"message_id": len(self.textos)}

    def editar_texto(self, chat, mid, texto, html=True):
        self.edicoes.append((mid, texto))

    def responder_toque(self, cid, texto=None):
        self.toques.append(texto)


class _PubIG:
    def __init__(self):
        self.publicados = []

    def publicar_carrossel(self, urls, legenda):
        self.publicados.append(("carrossel", urls, legenda))
        return "m1", "https://instagram.com/p/x"

    def publicar_imagem(self, url, legenda):
        self.publicados.append(("post", [url], legenda))
        return "m2", "https://instagram.com/p/y"


class _Head:
    def head(self, *a, **k):
        return type("R", (), {"status_code": 200})()


def _png_teste():
    from PIL import Image
    import io as _io
    b = _io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(b, "PNG")
    return b.getvalue()


def _toque(pid, acao, chat="99"):
    return {"id": "c1", "data": f"ig:{acao}:{pid}", "message": {"chat": {"id": int(chat)}}}


@pytest.fixture
def ig_ligado(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_TOKEN", "t")
    monkeypatch.setenv("INSTAGRAM_USER_ID", "1")


def _oferta_pub(id_="MLB1", preco=50.0):
    from types import SimpleNamespace
    return SimpleNamespace(id=id_, titulo="Kit body bebê 5 peças", preco=preco)


def test_instagram_pub_aprovado_publica_no_horario(tmp_path, ig_ligado):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from bot import instagram_pub as pub
    fuso = ZoneInfo("America/Sao_Paulo")
    tg, ig, estado = _TGFalso(), _PubIG(), {"vitrine": {"itens": [{"id": "MLB1", "preco": 49.9}]}}
    agora = datetime(2026, 11, 13, 10, 0, tzinfo=fuso)
    pid = pub.oferecer(tg, "99", estado, agora, "carrossel", [_png_teste(), _png_teste()], "legenda", [_oferta_pub()], "18h", pasta=tmp_path)
    assert (tmp_path / pid / "01.jpg").exists() and tg.textos[-1][1][0][1] == f"ig:ok:{pid}"
    assert "às 18h" in tg.textos[-1][0]
    # sem aprovar, nada sai
    pub.publicar_pendentes(tg, "99", estado, agora.replace(hour=19), ig=ig, session=_Head(), pasta=tmp_path)
    assert not ig.publicados
    pub.tratar_toque(tg, "99", estado, _toque(pid, "ok"), agora)
    assert estado["ig_fila"][pid]["status"] == "aprovado"
    pub.publicar_pendentes(tg, "99", estado, agora.replace(hour=17), ig=ig, session=_Head(), pasta=tmp_path)
    assert not ig.publicados  # ainda não é a hora
    pub.publicar_pendentes(tg, "99", estado, agora.replace(hour=18, minute=10), ig=ig, session=_Head(), pasta=tmp_path)
    assert ig.publicados[0][0] == "carrossel" and ig.publicados[0][1][0].endswith(f"/ig-tmp/{pid}/01.jpg")
    assert estado["ig_fila"][pid]["status"] == "publicado"
    assert "Publicado no Instagram" in tg.edicoes[-1][1]


def test_instagram_pub_barra_preco_que_subiu(tmp_path, ig_ligado):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from bot import instagram_pub as pub
    fuso = ZoneInfo("America/Sao_Paulo")
    tg, ig = _TGFalso(), _PubIG()
    estado = {"vitrine": {"itens": [{"id": "MLB1", "preco": 59.9}]}}
    agora = datetime(2026, 11, 13, 10, 0, tzinfo=fuso)
    pid = pub.oferecer(tg, "99", estado, agora, "post", [_png_teste()], "leg", [_oferta_pub()], "20h30", pasta=tmp_path)
    pub.tratar_toque(tg, "99", estado, _toque(pid, "ok"), agora)
    pub.publicar_pendentes(tg, "99", estado, agora.replace(hour=20, minute=40), ig=ig, session=_Head(), pasta=tmp_path)
    assert not ig.publicados and estado["ig_fila"][pid]["status"] == "barrado"
    assert "subiu" in tg.textos[-1][0]


def test_instagram_pub_recusa_toque_alheio_e_expira(tmp_path, ig_ligado):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from bot import instagram_pub as pub
    fuso = ZoneInfo("America/Sao_Paulo")
    tg, ig, estado = _TGFalso(), _PubIG(), {}
    agora = datetime(2026, 11, 13, 10, 0, tzinfo=fuso)
    a = pub.oferecer(tg, "99", estado, agora, "post", [_png_teste()], "x", [_oferta_pub()], pasta=tmp_path)
    b = pub.oferecer(tg, "99", estado, agora, "post", [_png_teste()], "y", [_oferta_pub("MLB2")], pasta=tmp_path)
    pub.tratar_toque(tg, "99", estado, _toque(a, "ok", chat="12345"), agora)  # outra conversa
    assert estado["ig_fila"][a]["status"] == "pendente"
    pub.tratar_toque(tg, "99", estado, _toque(b, "nao"), agora)
    assert estado["ig_fila"][b]["status"] == "recusado"
    amanha = agora + timedelta(days=1)
    pub.publicar_pendentes(tg, "99", estado, amanha, ig=ig, session=_Head(), pasta=tmp_path)
    assert estado["ig_fila"][a]["status"] == "expirado" and not ig.publicados
    pub.publicar_pendentes(tg, "99", estado, agora + timedelta(days=3), ig=ig, session=_Head(), pasta=tmp_path)
    assert not (tmp_path / a).exists() and not (tmp_path / b).exists()


def test_instagram_pub_sem_token_nao_oferece(tmp_path, monkeypatch):
    from datetime import datetime
    from bot import instagram_pub as pub
    monkeypatch.delenv("INSTAGRAM_TOKEN", raising=False)
    estado = {}
    assert pub.oferecer(_TGFalso(), "99", estado, datetime(2026, 11, 13), "post", [_png_teste()], "x",
                        [_oferta_pub()], pasta=tmp_path) is None
    assert not estado


def test_tipos_novos_vao_na_frente():
    from types import SimpleNamespace as NS
    from bot.ofertas import priorizar_tipos_novos, tipo_produto
    assert tipo_produto("Totoka Plus Carrinho De Passeio Infantil") == "carrinho de bebe"
    assert tipo_produto("Sugador Aspirador Nasal Elétrico Infantil") == tipo_produto("Kit Aspirador Nasal Manual Buba")
    assert tipo_produto("Mosquiteiro Para Carrinho Bebê Conforto") == "mosquiteiro"
    e = est.novo()
    est.registrar_post(e, "MLB1", 50.0, AGORA - timedelta(hours=30), "Kit 4 Travas de Segurança Para Gaveta", 0.3)
    ofs = [NS(titulo="Kit 3 Travas De Geladeira E Gavetas Segurança"), NS(titulo="Xilofone Para Bebês Fisher-price")]
    assert [o.titulo[:3] for o in priorizar_tipos_novos(ofs, e, AGORA)] == ["Xil", "Kit"]
    # depois de 2 dias o tipo volta a concorrer normalmente
    assert priorizar_tipos_novos(ofs, e, AGORA + timedelta(days=2))[0].titulo.startswith("Kit")


def test_espelho_classifica_links():
    from bot import espelho
    assert espelho.classificar("https://www.mercadolivre.com.br/p/MLB19876543?matt_tool=1") == ("ml", "catalogo", "MLB19876543")
    assert espelho.classificar("https://produto.mercadolivre.com.br/MLB-4123456789-body-bebe") == ("ml", "item", "MLB4123456789")
    assert espelho.classificar("https://shopee.com.br/Body-Bebe-i.123456.22334455667") == ("shopee", "22334455667")
    assert espelho.classificar("https://shopee.com.br/opaanlp/1648150131/58252119510") == ("shopee", "58252119510")
    assert espelho.classificar("https://shopee.com.br/product/1648150131/58252119510?x=1") == ("shopee", "58252119510")
    assert espelho.classificar("https://www.amazon.com.br/dp/B0ABC") is None
    msg = "🔥 BAIXOU!\n\nKit 3 Bodies Bebê Manga Longa Algodão\n\nDe: R$ 89\nPor: R$ 49\n🛒 https://meli.la/abc"
    assert espelho.titulo_da_mensagem(msg) == "Kit 3 Bodies Bebê Manga Longa Algodão"


def test_espelho_coleta_e_vira_candidato(monkeypatch):
    from bot import espelho
    monkeypatch.setenv("FONTES_OFERTAS_TG", "@promosbaby, Canal Teste")
    e = est.novo()
    lidos = []

    def ler(lista):
        lidos.append(lista)
        return [[(10, "Body bebê https://meli.la/x1"), (11, "Fralda https://s.shopee.com.br/abc")],
                RuntimeError("não entrou")]

    destinos = {"https://meli.la/x1": "https://www.mercadolivre.com.br/p/MLB555?wid=",
                "https://s.shopee.com.br/abc": "https://shopee.com.br/Fralda-i.123456.777777"}
    n = espelho.coletar(None, e, AGORA, log=lambda m: None, ler=ler, expandir_url=lambda u, s=None: destinos[u])
    assert n == 2 and lidos[0] == [("@promosbaby", None), ("Canal Teste", None)]
    assert e["espelho"]["fontes"]["@promosbaby"] == 11
    assert espelho.candidatos_ml(e, AGORA)["MLB555"]["regra"] == "infantil"
    assert espelho.ids_shopee(e, AGORA) == ["SHP777777"]
    assert espelho.eh_do_espelho(e, "MLB555")
    # link repetido não conta de novo; depois de 48 h o candidato expira
    assert espelho.coletar(None, e, AGORA, log=lambda m: None, ler=lambda l: [[(12, "https://meli.la/x1")], []],
                           expandir_url=lambda u, s=None: destinos[u]) == 0
    assert espelho.candidatos_ml(e, AGORA + timedelta(hours=49)) == {}


def test_espelho_shopee_confere_pela_api():
    from bot import espelho, shopee_ofertas as so
    e = est.novo()
    espelho._estado(e)["shopee"] = {"SHP7": {"ate": (AGORA + timedelta(hours=5)).isoformat()},
                                    "SHP8": {"ate": (AGORA + timedelta(hours=5)).isoformat()}}

    class Shp:
        def item(self, iid):
            return _produto_shopee(id="SHP" + iid, titulo="Body Bebê Algodão" if iid == "7" else "Jaqueta de couro feminina")

    achados = so.do_espelho(Shp(), e, AGORA, log=lambda m: None)
    assert [p.id for p in achados] == ["SHP7"]
    assert e["espelho"]["shopee"]["SHP8"]["fora"]


def test_espelho_link_sem_produto_usa_o_nome(monkeypatch):
    from bot import espelho
    e = est.novo()
    monkeypatch.setenv("FONTES_OFERTAS_TG", "@canal")

    class ML:
        def buscar_produtos(self, termo, limite=10):
            return [("MLB321", "Kit 3 Bodies Bebê Manga Longa Algodão Branco")]

    msg_ml = "Kit 3 Bodies Bebê Manga Longa Algodão\nPor R$ 49\nhttps://meli.la/abc"
    msg_shp = "Banheira Dobrável Infantil Com Termômetro\nR$ 89\nhttps://s.shopee.com.br/xyz"
    destinos = {"https://meli.la/abc": "https://www.mercadolivre.com.br/social/fulano?matt_word=x",
                "https://s.shopee.com.br/xyz": "https://s.shopee.com.br/xyz"}
    n = espelho.coletar(ML(), e, AGORA, log=lambda m: None, ler=lambda l: [[(1, msg_ml), (2, msg_shp)]],
                        expandir_url=lambda u, s=None: destinos[u])
    assert n == 2
    assert "MLB321" in espelho.candidatos_ml(e, AGORA)
    assert list(espelho.titulos_shopee(e, AGORA)) == ["Banheira Dobrável Infantil Com Termômetro"]


def test_espelho_ignora_chamada_em_caixa_alta():
    from bot import espelho
    from bot.filtros import fora_da_faixa
    assert espelho.titulo_da_mensagem("CORRE QUE A SHOPEE TÁ COM DESCONTO\nBanheira Dobrável Infantil 35L") == "Banheira Dobrável Infantil 35L"
    assert fora_da_faixa("Hipoglós Creme Preventivo de Assaduras, 120g", "outros", "infantil") is None
    assert fora_da_faixa("Kit Com 5 Carrinhos Sortidos Hot Wheels Coloridos Mattel", "outros", "infantil") is None


def test_preco_por_unidade_so_quando_esta_claro():
    f = mensagens.preco_por_unidade
    assert f("Fralda Pampers Confort Sec XG 104 Unidades", 93.60) == (pytest.approx(0.90), "por fralda")
    assert f("Fralda Babysec 2 pacotes de 52 unidades", 110)[0] == pytest.approx(110 / 104)
    assert f("Lenços Umedecidos Huggies 384 unidades", 38.40) == (pytest.approx(10.0), "a cada 100 lenços")
    # na dúvida, não mostra nada
    assert f("Kit 3 Pacotes Fralda Pom Pom G 48 unidades", 120) is None      # 48 no total ou em cada pacote?
    assert f("Kit 10 Fraldas De Pano Cremer Luxo Bordada", 60) is None       # fralda de pano
    assert f("Bolsa Porta Fraldas com 3 unidades", 50) is None
    assert f("Fralda Pampers P 36 unidades + Lenços umedecidos 48 unidades", 50) is None
    assert f("Fralda Premium XG 104 Unidades", 2000) is None                 # preço por fralda absurdo
    assert f("Carrinho de Bebê Travel System", 900) is None


def test_preco_por_unidade_aparece_na_mensagem():
    from bot import ofertas
    o = ofertas.Oferta(id="MLB1", titulo="Fralda Pampers Confort Sec XG 104 Unidades", preco=93.60, preco_de=120.0,
                       desconto=0.22, abaixo_do_habitual=None, menor_preco_historico=False,
                       link="https://meli.la/x", imagem=None, categoria="fralda")
    assert "🧮 Sai a *R$ 0,90* por fralda" in mensagens.montar_whatsapp(o, random.Random(1))
    assert "🧮 Sai a <b>R$ 0,90</b> por fralda" in mensagens.montar_telegram(o, random.Random(1))
    o.titulo = "Banheira Dobrável Infantil"
    assert "🧮" not in mensagens.montar_whatsapp(o, random.Random(1))


def test_comando_bloquear_e_desbloquear():
    from bot import comandos, filtros
    e = est.novo()
    e["postados"]["MLB7"] = {"quando": AGORA.isoformat(), "preco": 30.0, "titulo": "Baby Doll Short Doll Feminino"}
    try:
        r = comandos.tratar_texto("bloquear Baby Doll", None, None, e, cfg_cmd(), AGORA)
        assert e["bloqueados"] == ["baby doll"] and "1 teriam sido barrados" in r
        assert motivo_bloqueio("Kit Baby-Doll Feminino Estampado") == "bloqueado por você: baby doll"
        assert motivo_bloqueio("Body Bebê Algodão") is None
        assert "já estava" in comandos.tratar_texto("bloquear baby doll", None, None, e, cfg_cmd(), AGORA)
        assert "baby doll" in comandos.tratar_texto("bloqueados", None, None, e, cfg_cmd(), AGORA)
        assert "3 letras" in comandos.tratar_texto("bloquear ab", None, None, e, cfg_cmd(), AGORA)
        assert "liberada" in comandos.tratar_texto("desbloquear BABY DOLL", None, None, e, cfg_cmd(), AGORA)
        assert e["bloqueados"] == [] and motivo_bloqueio("Kit Baby Doll Feminino") is None
    finally:
        filtros.definir_bloqueios([])


def test_comando_fila_do_whatsapp(tmp_path, monkeypatch):
    from bot import comandos, whatsapp
    monkeypatch.setenv("WA_FILA", str(tmp_path))
    assert "vazia" in comandos.tratar_texto("fila", None, None, est.novo(), cfg_cmd(), AGORA)
    for nome, loja in (("Banheira Dobrável Infantil", "ml"), ("Kit Body Bebê", "shopee"), ("Mochila Escolar", "ml")):
        whatsapp.enfileirar(f"*🪇 Chacoalhou o preço!*\n\n🛁 {nome}\n\nPor *R$ 50,00*\n\n👉 https://meli.la/x", None, AGORA, loja)
    r = comandos.tratar_texto("fila", None, None, est.novo(), cfg_cmd(), AGORA)
    assert "1. [ML] 🛁 Banheira Dobrável Infantil" in r and "2. [Shopee] 🛁 Kit Body Bebê" in r
    assert "Kit Body" in comandos.tratar_texto("tirar 2", None, None, est.novo(), cfg_cmd(), AGORA)
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert "2 item" in comandos.tratar_texto("limpar fila", None, None, est.novo(), cfg_cmd(), AGORA)
    assert not list(tmp_path.glob("*.json"))


def test_aviso_de_bot_parado_uma_vez_por_dia():
    from bot import comandos
    tg, e, cfg = TGCmd(), est.novo(), cfg_cmd()
    agora = AGORA.replace(hour=15, minute=0)
    e["postados"]["MLB1"] = {"quando": (agora - timedelta(hours=1)).isoformat(), "preco": 10.0, "titulo": "x"}
    assert not comandos.avisar_se_parado(tg, cfg, e, agora)            # postou há 1 h: tudo certo
    e["postados"]["MLB1"]["quando"] = (agora - timedelta(hours=4)).isoformat()
    e["shopee"] = {"postados": {"SHP1": (agora - timedelta(hours=5)).isoformat(timespec="minutes")}}
    assert comandos.avisar_se_parado(tg, cfg, e, agora) and "4 h" in tg.textos[-1][1]
    assert not comandos.avisar_se_parado(tg, cfg, e, agora)            # só 1 aviso por dia
    e["aviso_parado"] = None
    assert not comandos.avisar_se_parado(tg, cfg, e, agora.replace(hour=9))   # começo do dia não conta


def test_selo_menor_preco_so_com_base():
    from bot.ofertas import selo_menor_preco
    e = est.novo()
    for dias, preco in [(40, 120.0), (20, 100.0), (18, 110.0)]:
        est.registrar_preco(e, "MLB1", preco, AGORA - timedelta(days=dias))
    assert selo_menor_preco(e, "MLB1", 95.0, AGORA) == 30        # menor da janela de 30 dias
    assert selo_menor_preco(e, "MLB1", 100.0, AGORA) == 30       # empata com o menor (visto só 2 dias) e já esteve mais caro
    assert selo_menor_preco(e, "MLB1", 105.0, AGORA) is None     # já esteve mais barato (100)
    est.registrar_preco(e, "MLB1", 98.0, AGORA)                  # hoje mais cedo já esteve a 98
    assert selo_menor_preco(e, "MLB1", 100.0, AGORA) is None
    e2 = est.novo()
    est.registrar_preco(e2, "MLB2", 100.0, AGORA - timedelta(days=16))
    assert selo_menor_preco(e2, "MLB2", 100.0, AGORA) is None    # preço parado: sem selo
    assert selo_menor_preco(e2, "MLB2", 90.0, AGORA) == 16       # 16 dias de histórico: diz 16, não 30
    e3 = est.novo()
    est.registrar_preco(e3, "MLB3", 100.0, AGORA - timedelta(days=9))
    assert selo_menor_preco(e3, "MLB3", 80.0, AGORA) is None     # menos de 14 dias acompanhando
    assert selo_menor_preco(e3, "MLB9", 80.0, AGORA) is None


def test_selo_aparece_no_post():
    e = est.novo()
    est.registrar_preco(e, "MLB1", 100.0, AGORA - timedelta(days=20))
    o = avaliar(prod(), info(70, 100), e, AGORA)
    assert o.selo_dias == 20
    assert "📉 Menor preço que o Chocalho viu em 20 dias" in mensagens.montar_whatsapp(o, random.Random(1))
    assert "📉" not in mensagens.montar_whatsapp(avaliar(prod(), info(70, 100), est.novo(), AGORA), random.Random(1))


def test_queda_real_vira_oferta_sem_de_no_anuncio():
    e = est.novo()
    est.registrar_preco(e, "MLB1", 100.0, AGORA - timedelta(days=10))
    assert avaliar(prod(), info(95), e, AGORA) is None              # só 5% abaixo do normal: não é oferta
    o = avaliar(prod(), info(85), e, AGORA)                         # 15% abaixo do normal, sem "de" no anúncio
    assert o and o.preco_de is None and o.preco_normal == 100.0
    assert "📉 Baixou: vinha custando R$ 100,00 no histórico do Chocalho" in mensagens.montar_whatsapp(o, random.Random(1))
    e2 = est.novo()
    est.registrar_preco(e2, "MLB1", 100.0, AGORA - timedelta(days=3))
    assert avaliar(prod(), info(85), e2, AGORA) is None             # pouco histórico: não vale ainda
    com_de = avaliar(prod(), info(70, 100), e, AGORA)               # com "de" do anúncio, mostra só o de/por
    assert com_de.preco_normal is None


def test_desconto_minimo_por_tipo_de_oferta(monkeypatch):
    from bot import cupom_oferta, espelho
    from bot.main import avaliar_oferta, desconto_minimo
    cfg = Config(min_desconto=0.20)
    e = est.novo()
    e["descobertos"] = {"MLB1": {"tipo": "item", "categoria": "fralda", "pos": 1},
                        "MLB2": {"tipo": "item", "categoria": "fralda", "pos": 9}}
    espelho._estado(e)["ml"]["MLB3"] = {"ate": (AGORA + timedelta(hours=5)).isoformat(timespec="minutes")}
    assert desconto_minimo(cfg, e, "MLB1") == 0.15     # entre os 3 mais vendidos
    assert desconto_minimo(cfg, e, "MLB2") == 0.20
    assert desconto_minimo(cfg, e, "MLB3") == 0.10     # veio de um canal de ofertas
    assert avaliar_oferta(cfg, e, prod("MLB1"), info(84, 100, "MLB1"), AGORA)          # 16% e é top 3
    assert avaliar_oferta(cfg, e, prod("MLB2"), info(84, 100, "MLB2"), AGORA) is None  # 16% e não é top
    # cupom do canal que completa os 20%: 12% do anúncio + cupom levando a R$ 75
    monkeypatch.setattr(cupom_oferta, "melhor_cupom", lambda est_, o, ag: {"codigo": "X", "preco": 75.0, "economia": 13.0})
    assert avaliar_oferta(cfg, e, prod("MLB2"), info(88, 100, "MLB2"), AGORA)
    monkeypatch.setattr(cupom_oferta, "melhor_cupom", lambda est_, o, ag: {"codigo": "X", "preco": 85.0, "economia": 3.0})
    assert avaliar_oferta(cfg, e, prod("MLB2"), info(88, 100, "MLB2"), AGORA) is None


def test_shopee_busca_por_categoria_com_rodizio():
    from bot import shopee_ofertas as so
    chamadas = []

    class Shp:
        def buscar(self, termo="", ordem=2, pagina=1, limite=50, categoria=None):
            chamadas.append((termo, categoria, pagina))
            return [_produto_shopee(id=f"SHP{len(chamadas)}", titulo=f"Brinquedo Infantil Modelo {len(chamadas)}")]

    e = est.novo()
    so.buscar_candidatos(Shp(), e, AGORA, log=lambda m: None)
    cats = [c for c in chamadas if c[1]]
    assert len(chamadas) == so.TERMOS_POR_RODADA + 2 and cats == [("", 100683, 1), ("", 100684, 1)]
    chamadas.clear()
    e["shopee"]["cat"] = len(so.CATEGORIAS)          # deu a volta: começa a página 2
    so.buscar_candidatos(Shp(), e, AGORA, log=lambda m: None)
    assert [c for c in chamadas if c[1]][0] == ("", 100683, 2)
    chamadas.clear()
    so.buscar_candidatos(Shp(), e, AGORA, log=lambda m: None, termos=["fralda"])   # busca pedida: sem categorias
    assert chamadas == [("fralda", None, 1)]


def test_shopee_espelho_aceita_200_vendas():
    from bot import shopee_ofertas as so
    p = _produto_shopee(vendas=250)
    assert so.aprovado(p) == "poucas vendas" and so.aprovado(p, so.VENDAS_MIN_ESPELHO) is None
    assert so.aprovado(_produto_shopee(vendas=150), so.VENDAS_MIN_ESPELHO) == "poucas vendas"


def test_shopee_busca_sem_palavra_nao_manda_keyword():
    from bot.shopee import Shopee
    vistos = []

    class S(Shopee):
        def _chamar(self, consulta, **k):
            vistos.append(consulta)
            return {"productOfferV2": {"nodes": []}}

    s = S("1", "x")
    s.buscar("", categoria=100684, pagina=2)
    s.buscar("fralda")
    assert "keyword" not in vistos[0] and "productCatId:100684" in vistos[0] and "page:2" in vistos[0]
    assert 'keyword:"fralda"' in vistos[1]


# ---------- bloco 3: meia-noite, calendário, histórico sem vai-e-vem, resumos e gráfico ----------

def test_janela_da_meia_noite(monkeypatch):
    from bot import ciclo, horario
    from bot.ofertas import vagas_da_rodada
    monkeypatch.delenv("DATAS_MEIA_NOITE", raising=False)
    d = lambda dia, h, m=0, mes=11: datetime(2026, mes, dia, h, m, tzinfo=FUSO)  # noqa: E731
    assert not horario.meia_noite(d(26, 23, 29)) and horario.meia_noite(d(26, 23, 30))   # véspera da Black Friday
    assert horario.meia_noite(d(27, 0, 59)) and not horario.meia_noite(d(27, 1, 0))
    assert not horario.meia_noite(d(27, 23, 40))                                          # a virada seguinte não conta
    assert horario.meia_noite(d(11, 23, 45, mes=12)) and horario.meia_noite(d(12, 0, 10, mes=12))  # 12.12
    assert horario.ativo(d(26, 23, 40), 8, 22) and not horario.ativo(d(25, 23, 40), 8, 22)
    assert horario.ativo(d(20, 9), 8, 22) and not horario.ativo(d(20, 22), 8, 22)
    # O ciclo acorda às 23h30 na véspera e volta ao normal depois da 1h
    assert ciclo.proximo_horario(d(26, 21, 50), 8, 22) == d(26, 23, 30)
    assert ciclo.proximo_horario(d(26, 23, 50), 8, 22) == d(27, 0, 10)
    assert ciclo.proximo_horario(d(27, 0, 50), 8, 22) == d(27, 8, 2)
    assert ciclo.proximo_horario(d(20, 21, 50), 8, 22) == d(21, 8, 2)
    # Na janela vale só o limite por hora (com reforço), fora da conta do dia
    assert vagas_da_rodada(d(27, 0, 10), 2, 4, 50, 0, 0) == 2
    assert vagas_da_rodada(d(26, 23, 40), 2, 4, 50, 5, 50) == 1 and vagas_da_rodada(d(26, 23, 40), 2, 4, 50, 6, 50) == 0
    assert vagas_da_rodada(d(20, 9), 2, 4, 50, 0, 50) == 0                                 # dia normal: limite do dia vale
    monkeypatch.setenv("DATAS_MEIA_NOITE", "")
    assert not horario.meia_noite(d(26, 23, 40)) and horario.proxima_janela(d(1, 9)) is None


def test_rodada_posta_na_virada_da_black_friday(monkeypatch):
    monkeypatch.delenv("DATAS_MEIA_NOITE", raising=False)
    produtos, ml = cenario()
    cfg = Config(canal="@canal", max_por_rodada=1)
    virada = datetime(2026, 11, 27, 0, 10, tzinfo=FUSO)
    assert [o.id for o in rodar("normal", cfg, ml, TGFalso(), est.novo(), produtos, agora=virada)] == ["MLB2"]
    comum = datetime(2026, 11, 20, 0, 10, tzinfo=FUSO)
    assert rodar("normal", cfg, ml, TGFalso(), est.novo(), produtos, agora=comum) == []


def test_calendario_sazonal():
    from datetime import date
    from bot import sazonal
    from bot.ofertas import Oferta, pontuacao
    assert sazonal.carnaval(2027) == date(2027, 2, 9) and sazonal.pascoa(2026) == date(2026, 4, 5)
    assert sazonal.epocas(date(2026, 12, 1)) == ["Natal", "verão"]
    assert "volta às aulas" in sazonal.epocas(date(2027, 1, 10)) and "Carnaval" in sazonal.epocas(date(2027, 2, 1))
    assert sazonal.epocas(date(2027, 4, 20)) == []
    natal, janeiro = date(2026, 12, 1), date(2027, 1, 10)
    assert sazonal.peso("Boneca Fashion Com Acessórios", natal) == 1.2
    assert sazonal.peso("Jogo de Lençol Para Berço", natal, "quarto") == 1.0          # "jogo" de cama não é brinquedo
    assert sazonal.peso("Fralda Descartável M 80 un", natal, "fralda") == 1.0
    assert sazonal.peso("Mochila Escolar Infantil", janeiro) == 1.35 and sazonal.peso("Mochila Escolar Infantil", natal) == 1.0
    assert sazonal.peso("Piscina Inflável 1000 Litros", janeiro) == 1.2
    assert sazonal.peso("Boneca", None) == 1.0
    assert "mochila infantil" in sazonal.termos_shopee(janeiro) and sazonal.termos_shopee(date(2027, 4, 20)) == []
    o = Oferta(id="MLB1", titulo="Mochila Escolar Infantil", preco=70, preco_de=100, desconto=0.3,
               abaixo_do_habitual=None, menor_preco_historico=False, link="x", imagem=None, categoria="escola")
    assert pontuacao(o, None, datetime(2027, 1, 10, 9, tzinfo=FUSO)) == pytest.approx(pontuacao(o) * 1.35)
    assert pontuacao(o, None, AGORA) == pontuacao(o)


def test_shopee_busca_termo_da_epoca():
    from bot import shopee_ofertas as so

    class Shp:
        def __init__(self): self.termos = []
        def buscar(self, termo, **k):
            self.termos.append(termo)
            return []

    e, shp = est.novo(), Shp()
    so.buscar_candidatos(shp, e, datetime(2027, 1, 10, 9, tzinfo=FUSO), log=lambda m: None)
    so.buscar_candidatos(shp, e, datetime(2027, 1, 10, 9, 20, tzinfo=FUSO), log=lambda m: None)
    da_epoca = [t for t in shp.termos if t in ("mochila infantil", "lancheira infantil")]
    assert da_epoca == ["mochila infantil", "lancheira infantil"]      # uma por rodada, em rodízio


def test_historico_sem_vai_e_vem():
    """Produto que alterna entre dois preços no ML: cada preço fica uma vez por dia e vale o menor do dia."""
    from bot.ofertas import selo_menor_preco
    e = est.novo()
    for dias in range(20, 0, -1):
        for preco in (323.48, 309.0, 323.48, 309.0, 323.48):
            est.registrar_preco(e, "MLB1", preco, AGORA - timedelta(days=dias))
    hist = e["precos"]["MLB1"]["historico"]
    assert len(hist) == 40 and hist[-1][1] == 323.48                 # 2 por dia; o último é o preço em vigor
    assert est.preco_tipico(e, "MLB1", AGORA) == (309.0, 20)         # o "normal" é o preço baixo de todo dia
    assert selo_menor_preco(e, "MLB1", 309.0, AGORA) is None         # aparece todo dia: não é menor preço "novo"
    assert selo_menor_preco(e, "MLB1", 289.0, AGORA) == 20           # queda de verdade ganha o selo
    assert avaliar(prod(), info(309.0), e, AGORA) is None            # e não vira "baixou" só por alternar
    o = avaliar(prod(), info(270.0), e, AGORA)
    assert o and o.preco_normal == 309.0
    # Dados antigos (gravados antes desta regra) são enxugados ao carregar
    e2 = {"precos": {"MLB2": {"min": 10, "historico": [["2026-11-01", 10], ["2026-11-01", 12], ["2026-11-01", 10],
                                                       ["2026-11-01", 12], ["2026-11-02", 12], ["2026-11-02", 10]]}}}
    est.compactar_precos(e2)
    assert e2["precos"]["MLB2"]["historico"] == [["2026-11-01", 10], ["2026-11-01", 12], ["2026-11-02", 12], ["2026-11-02", 10]]
    serie = est.serie_diaria(e2, "MLB2", datetime(2026, 11, 4, 9, tzinfo=FUSO))
    assert [p for _, p in serie] == [10, 10, 10]                      # dia 3 sem registro repete o preço em vigor


def test_selo_do_site_usa_a_mesma_regra():
    from bot import vitrine
    e = est.novo()
    est.registrar_preco(e, "MLB1", 100.0, AGORA - timedelta(days=9))
    assert vitrine.selo(e, {"id": "MLB1", "preco": 97.0}, AGORA) == (None, None)   # 9 dias: ainda sem "menor preço"
    assert vitrine.selo(e, {"id": "MLB1", "preco": 85.0}, AGORA) == ("baixou", 100.0)
    e2 = est.novo()
    est.registrar_preco(e2, "MLB1", 100.0, AGORA - timedelta(days=20))
    assert vitrine.selo(e2, {"id": "MLB1", "preco": 95.0}, AGORA) == ("menor", 20)
    assert vitrine._selo_txt({"selo": "menor30", "selo_dias": 20}) == "Menor preço em 20 dias"


def test_tabela_de_fraldas(monkeypatch, tmp_path):
    from bot import resumos
    assert resumos.tamanho_fralda("Fralda Pampers Confort Sec Tamanho G, 92 Un") == "G"
    assert resumos.tamanho_fralda("Huggies Fralda Descartável Máxima Proteção XG - 16 Un") == "XG"
    assert resumos.tamanho_fralda("Fralda Descartável Turma da Mônica Baby Recém-Nascido RN Pacote 36 Unidades") == "RN"
    assert resumos.tamanho_fralda("Fralda Protect & Sec 90 Unidades Tamanho Médio Personal Baby") == "M"
    assert resumos.tamanho_fralda("Fralda Infantil Tamanhos P M G 50 Unidades") is None      # mais de um tamanho
    assert resumos.tamanho_fralda("Fralda P/ Bebê 30 Unidades") is None                      # "P/" é "para"
    assert resumos.item_fralda("MLB1", "ml", "Trocador de Fralda Portátil M", 30, "https://meli.la/a") is None
    produtos = [prod("MLB1"), prod("MLB2"), prod("MLB3"), prod("MLB4"), prod("MLB5")]
    produtos[4].link_afiliado = "https://www.mercadolivre.com.br/p/MLB5?matt_word=x"       # sem link oficial
    infos = {
        "MLB1": InfoProduto("MLB1", "Fralda Marca A Tamanho M 80 Unidades", 64.0, None, None, True),
        "MLB2": InfoProduto("MLB2", "Fralda Marca B M 50 Unidades", 35.0, None, None, True),
        "MLB3": InfoProduto("MLB3", "Fralda Marca A Tamanho G 60 Unidades", 60.0, None, None, True),
        "MLB4": InfoProduto("MLB4", "Fralda Marca C RN 36 Unidades", 18.0, None, None, True),
        "MLB5": InfoProduto("MLB5", "Fralda Marca D Tamanho G 100 Unidades", 50.0, None, None, True),
    }
    e = est.novo()
    resumos.guardar_fraldas_ml(e, produtos, infos, AGORA, lambda link: "matt_word=" not in link)
    assert {i["id"] for i in e["fraldas_ml"]["itens"]} == {"MLB1", "MLB2", "MLB3", "MLB4"}

    class Shp:
        def buscar(self, termo, **k):
            return [_produto_shopee(id="SHP1", titulo="Fralda Marca E Tamanho G 100 Unidades", preco=70.0, preco_max=0),
                    _produto_shopee(id="SHP2", titulo="Fralda Marca F Tamanho M 100 Unidades", preco=20.0, nota=4.0),
                    _produto_shopee(id="SHP3", titulo="Fralda Marca G Tamanho P 40 Unidades", preco=20.0, preco_max=45.0)]

    links = lambda shp, p, log: ("https://s.shopee.com.br/tg", "https://s.shopee.com.br/wa")  # noqa: E731
    escolhidas = resumos.tabela_fraldas(e, AGORA, Shp(), lambda m: None, links)
    assert [(i["tam"], i["id"]) for i in escolhidas] == [("RN", "MLB4"), ("M", "MLB2"), ("G", "SHP1")]
    texto = resumos.montar_fraldas(escolhidas, AGORA, "whatsapp", {"M": 0.80, "G": 0.70})
    assert "*M* · *R$ 0,70* por fralda ⬇️ ontem era R$ 0,80" in texto and "*G* · *R$ 0,70* por fralda\n" in texto
    assert "https://s.shopee.com.br/wa" in texto and "na Shopee" in texto and "#publi" in texto
    # Só sai ligado, uma vez por dia, a partir das 10h
    tg, cfg = TGCmd(), cfg_cmd()
    monkeypatch.setenv("WA_FILA", str(tmp_path))
    monkeypatch.setenv("SHOPEE_ATIVO", "1")
    assert not resumos.talvez_fraldas(tg, cfg, e, AGORA, Shp(), lambda m: None, links) and not tg.textos   # desligado
    monkeypatch.setenv("FRALDAS_ATIVO", "1")
    assert not resumos.talvez_fraldas(tg, cfg, e, AGORA.replace(hour=9), Shp(), lambda m: None, links)
    assert resumos.talvez_fraldas(tg, cfg, e, AGORA, Shp(), lambda m: None, links)
    assert tg.textos[0][0] == "@canal" and "s.shopee.com.br/tg" in tg.textos[0][1] and len(list(tmp_path.glob("*.json"))) == 1
    assert not resumos.talvez_fraldas(tg, cfg, e, AGORA, Shp(), lambda m: None, links)                     # já saiu hoje
    assert e["fraldas_tabela"]["valores"]["RN"] == 0.5


def test_top_5_do_dia(monkeypatch, tmp_path):
    from types import SimpleNamespace as N
    from bot import resumos
    e = est.novo()
    agora = AGORA.replace(hour=21, minute=4)
    nomes = ["Fralda Descartável M", "Banheira Dobrável", "Mochila Escolar", "Boneca de Pano", "Tapete de Atividades",
             "Cadeira de Alimentação"]
    for k, (nome, de) in enumerate(zip(nomes, [100, 90, 80, 75, 72, 71])):
        o = N(id=f"MLB{k}", titulo=nome, preco=70.0, preco_de=float(de), link=f"https://meli.la/{k}", imagem=None,
              categoria="higiene", selo_dias=20 if k == 5 else None)
        resumos.registrar(e, o, agora, "ml", "catalogo")
    shp_o = N(id="SHP9", titulo="Livro Infantil Colorir", preco=20.0, preco_de=None, link="https://s.shopee.com.br/tg",
              link_wa="https://s.shopee.com.br/wa", imagem=None, categoria="livro", vendas=9000, nota=4.9, a_partir=True)
    resumos.registrar(e, shp_o, agora, "shopee")
    resumos.registrar(e, shp_o, agora, "shopee")                       # o mesmo produto não entra duas vezes
    assert len(e["posts_dia"]["itens"]) == 7
    top = resumos.escolher_top(e["posts_dia"]["itens"])
    # 3 do ML + a da Shopee; como sobrou vaga, completa com mais uma do ML (a do selo vem antes)
    assert [i["id"] for i in top] == ["MLB0", "MLB1", "MLB2", "MLB5", "SHP9"]
    assert [i["id"] for i in resumos.escolher_top(e["posts_dia"]["itens"], n=4)] == ["MLB0", "MLB1", "MLB2", "SHP9"]
    # Confere o preço na hora: quem subiu ou acabou sai; quem baixou entra com o preço novo
    precos = {"MLB0": 75.0, "MLB1": 65.0, "MLB2": None, "MLB3": 70.0, "MLB4": 70.0, "MLB5": 70.0, "SHP9": 20.0}
    top = resumos.escolher_top(e["posts_dia"]["itens"], conferir=lambda i: precos[i["id"]], log=lambda m: None)
    assert [i["id"] for i in top] == ["MLB1", "MLB5", "MLB3", "MLB4", "SHP9"] and top[0]["preco"] == 65.0
    texto = resumos.montar_top(top, agora, "whatsapp")
    assert texto.startswith("*🪇 As 5 melhores ofertas de hoje no Chocalho*") and "1️⃣" in texto and "5️⃣" in texto
    assert "De ~R$ 90,00~ por *R$ 65,00* (-28%) · Mercado Livre" in texto and "A partir de *R$ 20,00* · Shopee" in texto
    assert "📉 Menor preço que o Chocalho viu em 20 dias" in texto and "https://s.shopee.com.br/wa" in texto
    assert "Preços conferidos às 21h04" in texto and "Ver oferta na Shopee" in resumos.montar_top(top, agora, "telegram")
    # Postagem: só ligado, às 21h, uma vez
    ml = MLFalso({f"MLB{k}": InfoProduto(f"MLB{k}", nomes[k], 70.0, None, None, True) for k in range(6)})

    class Shp:
        def item(self, item_id):
            return _produto_shopee(id=f"SHP{item_id}", preco=20.0)

    tg, cfg = TGCmd(), cfg_cmd()
    monkeypatch.setenv("WA_FILA", str(tmp_path))
    assert not resumos.talvez_top(tg, cfg, e, agora, ml, Shp(), lambda m: None)
    monkeypatch.setenv("TOP5_ATIVO", "1")
    assert not resumos.talvez_top(tg, cfg, e, agora.replace(hour=20), ml, Shp(), lambda m: None)
    assert resumos.talvez_top(tg, cfg, e, agora, ml, Shp(), lambda m: None)
    assert tg.textos[0][0] == "@canal" and "As 5 melhores" in tg.textos[0][1] and len(list(tmp_path.glob("*.json"))) == 1
    assert not resumos.talvez_top(tg, cfg, e, agora, ml, Shp(), lambda m: None)
    # No dia seguinte a lista começa do zero
    resumos.registrar(e, shp_o, agora + timedelta(days=1), "shopee")
    assert len(e["posts_dia"]["itens"]) == 1


def test_rodada_guarda_post_do_dia_e_fraldas():
    produtos, ml = cenario()
    e = est.novo()
    rodar("normal", Config(canal="@canal", max_por_rodada=1), ml, TGFalso(), e, produtos, agora=AGORA)
    assert [i["id"] for i in e["posts_dia"]["itens"]] == ["MLB2"] and e["posts_dia"]["itens"][0]["tipo"] == "item"
    assert e["fraldas_ml"]["itens"] == []


def test_grafico_de_preco(monkeypatch):
    from types import SimpleNamespace as N
    from bot import grafico
    e = est.novo()
    for dias, preco in [(25, 89.9), (18, 94.9), (10, 89.9)]:
        est.registrar_preco(e, "MLB1", preco, AGORA - timedelta(days=dias))
    serie = grafico.serie_diaria(e, "MLB1", AGORA)
    assert len(serie) == 26 and serie[0][1] == 89.9 and serie[8][1] == 94.9 and serie[-1][1] == 89.9
    o = N(id="MLB1", titulo="Fralda Marca A Tamanho G 92 Un", preco=64.9, imagem="https://img/x.jpg", selo_dias=25, loja="ml")
    png = grafico.da_oferta(o, e, AGORA)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert grafico.gerar(o.titulo, serie, "shopee", formato="4x5")[:4] == b"\x89PNG"
    assert grafico.da_oferta(N(id="MLB9", titulo="x", preco=10, imagem=None), e, AGORA) is None        # sem histórico
    e9 = est.novo()
    est.registrar_preco(e9, "MLB1", 100.0, AGORA - timedelta(days=5))
    assert grafico.da_oferta(o, e9, AGORA) is None                                                     # menos de 14 dias

    class Tg:
        def __init__(self): self.chamadas = []
        def enviar_oferta(self, chat, legenda, imagem=None): self.chamadas.append("normal")
        def enviar_oferta_com_grafico(self, chat, legenda, imagem, png): self.chamadas.append("album")

    tg = Tg()
    grafico.enviar_oferta(tg, "@c", "legenda", o, e, AGORA)                 # desligado: post normal
    monkeypatch.setenv("GRAFICO_ATIVO", "1")
    grafico.enviar_oferta(tg, "@c", "legenda", o, e, AGORA)                 # ligado e com selo: álbum
    o.selo_dias = None
    grafico.enviar_oferta(tg, "@c", "legenda", o, e, AGORA)                 # sem selo: post normal
    assert tg.chamadas == ["normal", "album", "normal"]


def test_telegram_album_com_grafico():
    from bot.telegram import Telegram

    class S:
        def post(self, url, data=None, files=None, json=None, timeout=None):
            self.url, self.data, self.files = url, data, files
            return Resp(200, {"ok": True, "result": [{"message_id": 1}, {"message_id": 2}]})

    s = S()
    Telegram("T", session=s).enviar_oferta_com_grafico("@c", "<b>oi</b>", "https://img/x.jpg", b"png")
    midia = json.loads(s.data["media"])
    assert s.url.endswith("sendMediaGroup") and midia[0]["media"] == "https://img/x.jpg" and midia[0]["parse_mode"] == "HTML"
    assert midia[1]["media"] == "attach://grafico" and "grafico" in s.files


def test_colchao_de_solteiro_fica_de_fora():
    from bot.filtros import fora_da_faixa
    assert fora_da_faixa("Colchão Solteiro 188x88cm Espuma D20 Gazin", "quarto")
    assert fora_da_faixa("Jogo de Cama Solteiro Infantil Dinossauros 3 Peças", "quarto") is None
    assert fora_da_faixa("Berço 3 em 1 Vira Cama de Solteiro", "quarto") is None


def test_origem_do_espelho_aparece_para_o_admin():
    from types import SimpleNamespace as N
    from bot import comandos, espelho, resumos
    e = est.novo()
    e["espelho"] = {"ml": {"MLB1": {"fonte": "babypromokids", "ate": "2099-01-01"}}, "shopee": {}}
    assert espelho.fonte(e, "MLB1") == "babypromokids" and espelho.fonte(e, "MLB2") is None
    o = N(id="MLB1", titulo="Banheira Dobrável", preco=70.0, preco_de=100.0, link="https://meli.la/a", imagem=None,
          categoria="higiene", desconto=0.3)
    resumos.registrar(e, o, AGORA, "ml")
    assert e["posts_dia"]["itens"][0]["fonte"] == "babypromokids"
    tg = TGCmd()
    comandos.enviar_copias(tg, "123", avaliar(prod(), info(70, 100), est.novo(), AGORA), random.Random(1), fonte="babypromokids")
    assert "Copiada do canal @babypromokids" in tg.textos[-1][1]
    texto = comandos.montar_resumo(e, cfg_cmd(), TGCmd(), AGORA)
    assert "Copiadas de outros canais hoje: <b>1</b>" in texto and "@babypromokids → Banheira Dobrável (ML)" in texto


def test_link_de_anuncio_pausado_e_descartado():
    from bot import lote
    e = est.novo()
    e["lote"] = {"dia": "2026-11-05", "ids": ["MLB1", "MLB2"],
                 "urls": ["https://produto.mercadolivre.com.br/MLB-111-produto-_JM",
                          "https://produto.mercadolivre.com.br/MLB-222-produto-_JM"]}
    ok, _ = lote.aplicar_resposta(e, "https://meli.la/AAA https://meli.la/BBB")
    assert ok and e["links_item"] == {"MLB1": "MLB111", "MLB2": "MLB222"}
    # MLB1: o anúncio do link continua ativo, mas outro vendedor está mais barato → o post usa o preço do anúncio do link
    i1 = InfoProduto("MLB1", "Banheira", 60.0, 100.0, None, True, "MLB999",
                     ativos={"MLB999": (60.0, 100.0), "MLB111": (70.0, 100.0)})
    assert lote.conferir_anuncio(e, "MLB1", i1) and i1.preco == 70.0 and i1.item_id == "MLB111"
    # MLB2: o anúncio do link pausou → link descartado, produto volta para o lote
    i2 = InfoProduto("MLB2", "Berço", 300.0, 400.0, None, True, "MLB888", ativos={"MLB888": (300.0, 400.0)})
    assert not lote.conferir_anuncio(e, "MLB2", i2)
    assert "MLB2" not in e["links"] and "MLB2" not in e["links_item"]
    # Sem anúncio anotado (link antigo) ou sem consulta ao catálogo: segue como antes
    assert lote.conferir_anuncio(e, "MLB3", i2)
    assert lote.conferir_anuncio(e, "MLB1", InfoProduto("MLB1", "Banheira", 60.0, None, None, True))


def test_rodada_nao_posta_link_de_anuncio_pausado():
    produtos = [Produto("MLB1", "catalogo", "https://www.mercadolivre.com.br/p/MLB1", "https://meli.la/AAA", "higiene", None, 0)]
    infos = {"MLB1": InfoProduto("MLB1", "Banheira Dobrável Infantil", 50.0, 100.0, None, True, "MLB888",
                                 ativos={"MLB888": (50.0, 100.0)})}
    e = est.novo()
    e["links"] = {"MLB1": "https://meli.la/AAA"}
    e["links_item"] = {"MLB1": "MLB111"}
    cfg = Config(canal="@canal", max_por_rodada=1, link_modo="oficial", matt_word="chocalho", matt_tool="1")
    assert rodar("normal", cfg, MLFalso(infos), TGFalso(), e, produtos, agora=AGORA) == []
    assert "MLB1" not in e["links"] and e["aguardando_link"] == 1
