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
    assert pontuacao(roupa) > pontuacao(brinq)  # 20% de roupa vale mais que 24% de brinquedo
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
    textos = {mensagens._abertura(o, _r.Random(i)) for i in range(40)}
    assert any(t in mensagens.CHAMADAS["fralda"] for t in textos)
    assert any(t in mensagens.ABERTURAS for t in textos)


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
    assert "https://t.me/chocalho" in h and "Body &lt;bebê&gt; &amp; cia" in h and "-40%" in h
    assert "https://meli.la/A" in h and "#publi" in h and 'data-f="roupa"' in h
    # Mesma hora: não reescreve; hora seguinte sem mudança: também não
    assert not vitrine.talvez_publicar(e, "@chocalho", AGORA, arq, log=lambda m: None)
    assert not vitrine.talvez_publicar(e, "@chocalho", AGORA + timedelta(hours=1), arq, log=lambda m: None)
    o.preco = 55
    vitrine.guardar(e, [o], AGORA)
    assert vitrine.talvez_publicar(e, "@chocalho", AGORA + timedelta(hours=1), arq, log=lambda m: None)


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
    assert "Entrar no grupo do WhatsApp" in h and 'href="grupo.html"' in h and "t.me/c" in h
    g = (tmp_path / "grupo.html").read_text()
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
