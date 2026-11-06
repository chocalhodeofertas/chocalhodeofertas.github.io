from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
    return InfoProduto(pid, "Fralda Teste G", preco, original, "https://img/x-O.jpg", True)


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

    def enviar_texto(self, chat, texto, html=False):
        self.enviados.append(("texto", chat, texto))


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
    assert [t[1] for t in tg.enviados[1:]] == ["123", "123"]  # cópias WhatsApp e X
    assert "MLB2" in e["postados"] and "MLB3" not in e["precos"]
    # Na rodada seguinte não repete a MLB2, posta a MLB1
    enviadas = rodar("normal", cfg, ml, TGFalso(), e, produtos, agora=AGORA + timedelta(hours=1))
    assert [o.id for o in enviadas] == ["MLB1"]


def test_rodada_fora_do_horario():
    produtos, ml = cenario()
    tg, e = TGFalso(), est.novo()
    madrugada = AGORA.replace(hour=3)
    assert rodar("normal", Config(canal="@c"), ml, tg, e, produtos, agora=madrugada) == []
    assert tg.enviados == [] and e["precos"]  # preços registrados mesmo assim


def test_limite_diario():
    produtos, ml = cenario()
    e = est.novo()
    e["contagem_dia"] = {AGORA.date().isoformat(): 12}
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
        "MLB1": {"tipo": "item", "categoria": "outros"},
        "MLB2": {"tipo": "catalogo", "categoria": "outros"},
        "MLB3": {"tipo": "catalogo", "categoria": "roupa"},
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
