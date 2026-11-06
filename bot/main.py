"""Rodada do bot: busca preços, acha ofertas e posta.

Uso:
    python -m bot.main --modo normal       # posta no canal (respeita horário)
    python -m bot.main --modo teste        # manda tudo só para você, no privado
    python -m bot.main --modo diagnostico  # verifica se está tudo configurado
"""
import argparse
import csv
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from . import afiliado, cofre
from . import estado as est
from . import mensagens
from .descoberta import descobrir
from .filtros import motivo_bloqueio
from .mercadolivre import AcessoNegado, ErroML, MercadoLivre, extrair_id, link_produto, renovar_token, token_do_app
from .ofertas import avaliar
from .telegram import Telegram, TelegramErro

RAIZ = Path(__file__).resolve().parent.parent
ARQ_PRODUTOS = RAIZ / "produtos.csv"
ARQ_ESTADO = RAIZ / "data" / "estado.json"
FUSO = ZoneInfo("America/Sao_Paulo")


@dataclass
class Produto:
    id: str
    tipo: str
    link_produto: str
    link_afiliado: str
    categoria: str
    preco_referencia: Optional[float]
    linha: int


@dataclass
class Config:
    telegram_token: str = ""
    canal: str = ""
    admin_chat: str = ""
    ml_client_id: str = ""
    ml_client_secret: str = ""
    ml_refresh_token: str = ""
    min_desconto: float = 0.15
    max_por_rodada: int = 1
    max_por_hora: int = 2
    chance_postar: float = 1.0  # do ambiente vem 70%
    max_por_dia: int = 25
    repost_dias: int = 3
    hora_inicio: int = 8
    hora_fim: int = 22
    matt_word: str = ""
    matt_tool: str = ""
    por_categoria: int = 8
    horas_descoberta: int = 20

    @classmethod
    def do_ambiente(cls):
        e = os.environ.get

        def num(nome, padrao, tipo=float):
            valor = (e(nome) or "").strip().replace(",", ".")
            return tipo(valor) if valor else padrao

        return cls(
            telegram_token=e("TELEGRAM_BOT_TOKEN", ""),
            canal=e("TELEGRAM_CANAL", ""),
            admin_chat=e("TELEGRAM_ADMIN_CHAT_ID", ""),
            ml_client_id=e("ML_CLIENT_ID", ""),
            ml_client_secret=e("ML_CLIENT_SECRET", ""),
            ml_refresh_token=e("ML_REFRESH_TOKEN", ""),
            min_desconto=num("MIN_DESCONTO", 15) / 100,
            max_por_rodada=num("MAX_POSTS_POR_RODADA", 1, int),
            max_por_hora=num("MAX_POSTS_POR_HORA", 2, int),
            chance_postar=num("CHANCE_POSTAR", 70) / 100,
            max_por_dia=num("MAX_POSTS_POR_DIA", 25, int),
            repost_dias=num("REPOST_DIAS", 3, int),
            hora_inicio=num("HORA_INICIO", 8, int),
            hora_fim=num("HORA_FIM", 22, int),
            matt_word=e("AFILIADO_MATT_WORD", ""),
            matt_tool=e("AFILIADO_MATT_TOOL", ""),
            por_categoria=num("POR_CATEGORIA", 8, int),
            horas_descoberta=num("HORAS_DESCOBERTA", 20, int),
        )


def log(msg):
    print(msg, flush=True)


def carregar_produtos(caminho=ARQ_PRODUTOS):
    """Lê o produtos.csv. Linhas começando com # são comentários."""
    caminho = Path(caminho)
    if not caminho.exists():
        return [], ["produtos.csv não encontrado"]
    linhas = [
        (n, l) for n, l in enumerate(caminho.read_text(encoding="utf-8-sig").splitlines(), 1)
        if l.strip() and not l.lstrip().startswith("#")
    ]
    if not linhas:
        return [], []
    leitor = csv.DictReader([l for _, l in linhas])
    produtos, avisos, vistos = [], [], set()
    for (n, _), linha in zip(linhas[1:], leitor):
        linha = {(k or "").strip(): (v or "").strip() for k, v in linha.items()}
        link, afiliado = linha.get("link_produto", ""), linha.get("link_afiliado", "")
        if not link:
            continue
        try:
            tipo, pid = extrair_id(link)
        except ValueError as e:
            avisos.append(f"linha {n}: {e}")
            continue
        if pid in vistos:
            avisos.append(f"linha {n}: produto {pid} repetido — ignorado")
            continue
        motivo = motivo_bloqueio(link)
        if motivo:
            avisos.append(f"linha {n}: bloqueado ({motivo})")
            continue
        ref = linha.get("preco_referencia", "").replace("R$", "").strip()
        if "," in ref:  # formato brasileiro: 1.299,90
            ref = ref.replace(".", "").replace(",", ".")
        try:
            ref = float(ref) if ref else None
        except ValueError:
            avisos.append(f"linha {n}: preco_referencia inválido, ignorado")
            ref = None
        vistos.add(pid)
        produtos.append(
            Produto(pid, tipo, link, afiliado, (linha.get("categoria") or "outros").lower(), ref, n)
        )
    return produtos, avisos


def conectar_ml(cfg: Config):
    """Gera o token do ML (se configurado) e já salva o refresh_token novo."""
    if not (cfg.ml_client_id and cfg.ml_client_secret):
        return MercadoLivre(), "sem token"
    refresh = cofre.ler(cfg.ml_client_secret) or cfg.ml_refresh_token
    if not refresh:
        # Sem autorização do usuário: tenta o token só do app (Client Credentials)
        try:
            return MercadoLivre(token_do_app(cfg.ml_client_id, cfg.ml_client_secret)), "token do app"
        except AcessoNegado as e:
            log(f"Client Credentials não funcionou ({e}).")
            return MercadoLivre(), "sem token — falta rodar 'Configurar token do Mercado Livre'"
    access, novo_refresh = renovar_token(cfg.ml_client_id, cfg.ml_client_secret, refresh)
    # O ML troca o refresh_token a cada uso: guarda o novo na hora
    cofre.guardar(novo_refresh, cfg.ml_client_secret)
    return MercadoLivre(access), "com token"


def montar_lista(cfg: Config, da_planilha, estado):
    """Junta os produtos da planilha com os descobertos e garante o link de afiliado."""
    lista, vistos = [], set()
    for p in da_planilha:
        if not p.link_afiliado:
            p.link_afiliado = afiliado.montar(link_produto(p.tipo, p.id), cfg.matt_word, cfg.matt_tool)
        lista.append(p)
        vistos.add(p.id)
    for pid, d in estado.get("descobertos", {}).items():
        if pid in vistos:
            continue
        url = link_produto(d["tipo"], pid)
        lista.append(Produto(pid, d["tipo"], url, afiliado.montar(url, cfg.matt_word, cfg.matt_tool),
                             d["categoria"], None, 0))
    return lista


def atualizar_descoberta(cfg: Config, ml, estado, agora, forcar=False):
    ultima = estado.get("descoberta_em")
    if not forcar and ultima:
        horas = (agora - datetime.fromisoformat(ultima)).total_seconds() / 3600
        if horas < cfg.horas_descoberta:
            return False
    achados = descobrir(ml, cfg.por_categoria, log)
    if achados:
        estado["descobertos"] = achados
        estado["descoberta_em"] = agora.isoformat(timespec="minutes")
        validos = set(achados) | set(estado["postados"])
        estado["cache"] = {k: v for k, v in estado.get("cache", {}).items() if k in validos}
    return True


def buscar_infos(ml: MercadoLivre, produtos, estado=None):
    infos = {}
    cache = (estado or {}).setdefault("cache", {}) if estado is not None else {}
    ids_itens = [p.id for p in produtos if p.tipo == "item"]
    if ids_itens:
        try:
            infos.update(ml.itens(ids_itens))
        except AcessoNegado:
            log(f"Aviso: o Mercado Livre bloqueou {len(ids_itens)} anúncio(s) avulso(s). "
                "Na planilha, use links de catálogo (com /p/ no endereço).")

    def um(p):
        titulo, imagem = cache.get(p.id, (None, None))
        try:
            return p.id, ml.catalogo(p.id, titulo, imagem)
        except (ErroML, AcessoNegado) as e:
            log(f"Aviso: {p.id}: {e}")
            return p.id, None

    catalogo = [p for p in produtos if p.tipo == "catalogo"]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for pid, info in ex.map(um, catalogo):
            if info:
                infos[pid] = info
                cache[pid] = [info.titulo, info.imagem]
    return infos


def rodar(modo, cfg: Config, ml, tg, estado, produtos, agora=None, rng=random):
    """Uma rodada completa. Retorna a lista de ofertas enviadas."""
    agora = agora or datetime.now(FUSO)
    infos = buscar_infos(ml, produtos, estado)

    candidatas = []
    for p in produtos:
        info = infos.get(p.id)
        if not info:
            log(f"Sem dados para {p.id} (linha {p.linha}) — anúncio pode ter sido removido.")
            continue
        motivo = motivo_bloqueio(info.titulo)
        if motivo:
            log(f"Bloqueado {p.id}: {motivo} — '{info.titulo[:60]}'")
            continue
        oferta = avaliar(p, info, estado, agora, cfg.min_desconto, cfg.repost_dias)
        if info.preco:
            est.registrar_preco(estado, p.id, float(info.preco), agora)
        if oferta:
            candidatas.append(oferta)

    candidatas.sort(key=lambda o: o.forca, reverse=True)
    log(f"{len(produtos)} produtos verificados, {len(candidatas)} ofertas encontradas.")

    if modo == "teste":
        if not candidatas:
            log("Nenhuma oferta agora. No modo teste, mando um exemplo com o primeiro produto.")
            candidatas = _exemplo(produtos, infos)
        enviadas = []
        for o in candidatas[: max(cfg.max_por_rodada, 1)]:
            _enviar(tg, cfg.admin_chat, o, rng, rotulo="[TESTE] ")
            enviadas.append(o)
        return enviadas

    if not (cfg.hora_inicio <= agora.hour < cfg.hora_fim):
        log(f"Fora do horário de postagem ({cfg.hora_inicio}h–{cfg.hora_fim}h). Só atualizei os preços.")
        return []

    # Sorteio: nem toda rodada posta, para os horários não ficarem certinhos
    if rng.random() > cfg.chance_postar:
        log("Sorteio: esta rodada não posta (deixa os horários mais naturais).")
        return []

    vagas = min(
        cfg.max_por_rodada,
        cfg.max_por_hora - est.posts_ultima_hora(estado, agora),
        cfg.max_por_dia - est.posts_hoje(estado, agora),
    )
    enviadas = []
    for o in candidatas[: max(vagas, 0)]:
        try:
            tg.enviar_oferta(cfg.canal, mensagens.montar_telegram(o, rng), o.imagem)
        except TelegramErro as e:
            log(f"Erro ao postar {o.id} no canal: {e}")
            continue
        est.registrar_post(estado, o.id, o.preco, agora)
        enviadas.append(o)
        log(f"Postado: {o.id} {mensagens.brl(o.preco)} (-{round(o.desconto * 100)}%)")
        if cfg.admin_chat:
            try:
                _copias(tg, cfg.admin_chat, o, rng)
            except TelegramErro as e:
                log(f"Aviso: não consegui mandar a cópia para você: {e}")
        time.sleep(1)
    return enviadas


def _exemplo(produtos, infos):
    from .ofertas import Oferta

    for p in produtos:
        info = infos.get(p.id)
        if info and info.preco and not motivo_bloqueio(info.titulo):
            de = info.preco_original if (info.preco_original or 0) > info.preco else None
            return [
                Oferta(p.id, info.titulo, float(info.preco), de, (1 - info.preco / de) if de else 0,
                       None, False, p.link_afiliado, info.imagem, p.categoria)
            ]
    return []


def _enviar(tg, chat, oferta, rng, rotulo=""):
    if not chat:
        log("TELEGRAM_ADMIN_CHAT_ID não configurado — mostrando aqui no log:\n")
        log(mensagens.montar_whatsapp(oferta, rng))
        return
    tg.enviar_oferta(chat, rotulo + mensagens.montar_telegram(oferta, rng), oferta.imagem)
    _copias(tg, chat, oferta, rng)


def _copias(tg, chat, oferta, rng):
    """Uma mensagem com o texto do WhatsApp e botões que abrem WhatsApp e X já preenchidos."""
    wa = mensagens.montar_whatsapp(oferta, rng)
    tg.enviar_texto(chat, "📋 Pronto para compartilhar:\n\n" + wa,
                    botoes=mensagens.botoes_compartilhar(wa, mensagens.montar_x(oferta)))


def diagnostico(cfg: Config, produtos, avisos):
    """Confere cada peça e explica o que falta."""
    rel = ["🩺 Diagnóstico do Chocalho de Ofertas", ""]
    ok = True

    tg = None
    if not cfg.telegram_token:
        rel.append("❌ Falta o secret TELEGRAM_BOT_TOKEN.")
        ok = False
    else:
        tg = Telegram(cfg.telegram_token)
        try:
            bot = tg.eu()
            rel.append(f"✅ Bot do Telegram: @{bot['username']}")
        except TelegramErro as e:
            rel.append(f"❌ Token do Telegram recusado: {e}")
            tg, ok = None, False

    if tg and not cfg.canal:
        rel.append("❌ Falta o secret TELEGRAM_CANAL (ex.: @chocalhodeofertas).")
        ok = False
    elif tg:
        try:
            m = tg.membro(cfg.canal, bot["id"])
            if m.get("status") == "administrator" and m.get("can_post_messages", True):
                rel.append(f"✅ Bot é administrador de {cfg.canal} e pode postar.")
            else:
                rel.append(f"❌ Bot está em {cfg.canal} mas não é admin com permissão de postar.")
                ok = False
        except TelegramErro as e:
            rel.append(f"❌ Não consegui acessar o canal {cfg.canal}: {e}")
            ok = False

    if tg and not cfg.admin_chat:
        rel.append("⚠️ TELEGRAM_ADMIN_CHAT_ID não configurado (é onde chegam os testes e as cópias).")
        try:
            chats = {}
            for u in tg.atualizacoes():
                chat = (u.get("message") or {}).get("chat") or {}
                if chat.get("type") == "private":
                    chats[chat["id"]] = chat.get("first_name", "")
            if chats:
                for cid, nome in chats.items():
                    rel.append(f"   → Achei uma conversa com {nome}: chat ID = {cid}")
            else:
                rel.append("   → Mande um 'oi' para o seu bot no Telegram e rode o diagnóstico de novo.")
        except TelegramErro:
            pass

    rel.append("")
    rel.append(f"📦 Produtos na planilha: {len(produtos)}")
    rel.extend(f"   ⚠️ {a}" for a in avisos)

    try:
        ml, modo_ml = conectar_ml(cfg)
        rel.append(f"🔎 Mercado Livre: testando acesso ({modo_ml})...")
        amostra = produtos[:3]
        if not amostra:
            # Testa a descoberta com os 3 mais vendidos de Bebês
            amostra = [Produto(pid, tipo, "", "", "outros", None, 0)
                       for tipo, pid in ml.mais_vendidos("MLB1384")[:3]]
            rel.append(f"   ✅ Lista de mais vendidos acessível ({len(amostra)} de exemplo).")
        infos = buscar_infos(ml, amostra)
        for p in amostra:
            i = infos.get(p.id)
            if i and i.preco:
                rel.append(f"   ✅ {p.id}: {mensagens.brl(i.preco)} — {i.titulo[:50]}")
            else:
                rel.append(f"   ❌ {p.id}: sem preço")
        if cfg.matt_word and cfg.matt_tool:
            rel.append("✅ Link de afiliado automático, ex.: "
                       + afiliado.montar(link_produto("catalogo", "MLB123"), cfg.matt_word, cfg.matt_tool))
        else:
            ok = False
            rel.append("❌ Faltam AFILIADO_MATT_WORD / AFILIADO_MATT_TOOL.")
    except AcessoNegado as e:
        ok = False
        rel.append(f"❌ Mercado Livre recusou o acesso: {e}")
        if not cofre.ler(cfg.ml_client_secret or "x"):
            rel.append("   → Precisa configurar o token do ML (veja o README, passo 'Token do Mercado Livre').")
    except ErroML as e:
        ok = False
        rel.append(f"❌ Erro no Mercado Livre: {e}")

    rel.append("")
    rel.append("Tudo certo! 🎉" if ok else "Corrija os itens com ❌ e rode de novo.")
    texto = "\n".join(rel)
    log(texto)
    if tg and cfg.admin_chat:
        try:
            tg.enviar_texto(cfg.admin_chat, texto)
        except TelegramErro:
            pass
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["normal", "teste", "diagnostico"], default="normal")
    args = ap.parse_args(argv)
    cfg = Config.do_ambiente()
    produtos, avisos = carregar_produtos()
    for a in avisos:
        log(f"Aviso: {a}")

    if args.modo == "diagnostico":
        return 0 if diagnostico(cfg, produtos, avisos) else 1

    if not cfg.telegram_token or (args.modo == "normal" and not cfg.canal):
        log("Faltam secrets do Telegram. Rode o modo diagnostico para ver o que falta.")
        return 1

    estado = est.carregar(ARQ_ESTADO)
    try:
        ml, _ = conectar_ml(cfg)
        agora = datetime.now(FUSO)
        atualizar_descoberta(cfg, ml, estado, agora)
        lista = montar_lista(cfg, produtos, estado)
        if not lista:
            log("Nenhum produto para acompanhar (planilha vazia e descoberta sem resultado).")
            return 0
        rodar(args.modo, cfg, ml, Telegram(cfg.telegram_token), estado, lista, agora=agora)
    except AcessoNegado as e:
        log(f"Mercado Livre recusou o acesso: {e}\nRode o modo diagnostico para ver o que fazer.")
        return 1
    finally:
        est.salvar(ARQ_ESTADO, estado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
