"""Rodada do bot: busca preços, acha ofertas e posta.

Uso:
    python -m bot.main --modo normal       # posta no canal (respeita horário)
    python -m bot.main --modo teste        # manda tudo só para você, no privado
    python -m bot.main --modo diagnostico  # verifica se está tudo configurado
"""
import argparse
import csv
import html
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

from . import afiliado, cofre, comandos, cupom_oferta, cupons_ml, lote, vitrine, whatsapp
from . import estado as est
from . import mensagens
from .descoberta import descobrir, descobrir_areas
from .filtros import fora_da_faixa, motivo_bloqueio
from .mercadolivre import AcessoNegado, ErroML, MercadoLivre, extrair_id, link_produto, renovar_token, token_do_app
from .ofertas import avaliar, limite_hora, meta_ate_agora, pontuacao, tipo_produto
from .telegram import Telegram, TelegramErro

RAIZ = Path(__file__).resolve().parent.parent
ARQ_PRODUTOS = RAIZ / "produtos.csv"
ARQ_ESTADO = RAIZ / "data" / "estado.json"
FUSO = ZoneInfo("America/Sao_Paulo")
GRUPO_WHATSAPP = "https://chat.whatsapp.com/FOwEWWIjfKoFWmD8Xsv5lq"


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
    chance_postar: float = 1.0
    max_por_dia: int = 25
    repost_dias: int = 3
    hora_inicio: int = 8
    hora_fim: int = 22
    matt_word: str = ""
    matt_tool: str = ""
    por_categoria: int = 15
    horas_descoberta: int = 20
    link_modo: str = "oficial"  # "oficial" (meli.la via Linkbuilder) ou "direto"
    lote_tamanho: int = 30
    lotes_por_dia: int = 3
    # Intervalo aleatório entre posts da mesma rodada e atraso antes do 1º (minutos).
    # Padrão 0 aqui (testes); no GitHub vem do ambiente: 4–8 e até 3.
    intervalo_min: float = 0
    intervalo_max: float = 0
    atraso_max: float = 0

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
            chance_postar=num("CHANCE_POSTAR", 100) / 100,
            max_por_dia=num("MAX_POSTS_POR_DIA", 25, int),
            repost_dias=num("REPOST_DIAS", 3, int),
            hora_inicio=num("HORA_INICIO", 8, int),
            hora_fim=num("HORA_FIM", 22, int),
            matt_word=e("AFILIADO_MATT_WORD", ""),
            matt_tool=e("AFILIADO_MATT_TOOL", ""),
            por_categoria=max(num("POR_CATEGORIA", 15, int), 15),
            link_modo=(e("LINK_MODO") or "oficial").strip().lower(),
            lote_tamanho=min(num("LOTE_TAMANHO", 30, int), 30),  # limite do Linkbuilder
            lotes_por_dia=num("LOTES_POR_DIA", 3, int),
            intervalo_min=num("INTERVALO_MIN", 4),
            intervalo_max=num("INTERVALO_MAX", 8),
            atraso_max=num("ATRASO_MAX", 3),
            horas_descoberta=num("HORAS_DESCOBERTA", 20, int),
        )


def dormir(segundos):
    if segundos > 0:
        time.sleep(segundos)


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
    links = estado.get("links", {})
    for p in da_planilha:
        if not p.link_afiliado and p.id in links:
            p.link_afiliado = links[p.id]
        if not p.link_afiliado:
            p.link_afiliado = afiliado.montar(link_produto(p.tipo, p.id), cfg.matt_word, cfg.matt_tool)
        lista.append(p)
        vistos.add(p.id)
    extras = {**estado.get("manuais", {}), **estado.get("descobertos", {})}
    for pid, d in extras.items():
        if pid in vistos:
            continue
        url = link_produto(d["tipo"], pid)
        link = links.get(pid) or afiliado.montar(url, cfg.matt_word, cfg.matt_tool)
        lista.append(Produto(pid, d["tipo"], url, link, d["categoria"], None, 0))
    return lista


def atualizar_descoberta(cfg: Config, ml, estado, agora, forcar=False):
    from .busca import atualizar_vigias

    atualizar_vigias(ml, estado, agora, log)
    ultima = estado.get("descoberta_em")
    if not forcar and ultima:
        horas = (agora - datetime.fromisoformat(ultima)).total_seconds() / 3600
        if horas < cfg.horas_descoberta:
            return False
    achados = descobrir(ml, cfg.por_categoria, log)
    if achados and estado.get("areas_novas"):
        for pid, d in descobrir_areas(ml, log).items():
            achados.setdefault(pid, d)
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


def _esperar(segundos, tarefa=None, passo=120):
    """Espera; se houver tarefa (mensagens e cupons), roda ela a cada 2 min enquanto isso."""
    if not tarefa:
        dormir(segundos)
        return
    resta = segundos
    while resta > 0:
        trecho = min(passo, resta)
        dormir(trecho)
        resta -= trecho
        try:
            tarefa()
        except Exception as e:  # noqa: BLE001
            log(f"Aviso: tarefa rápida falhou: {e}")


def _reconferir(ml, produto, oferta, estado, cfg, agora):
    """Confere o preço de novo logo antes de postar. None = a oferta acabou."""
    if produto is None:
        return oferta
    try:
        if produto.tipo == "catalogo":
            info = ml.catalogo(produto.id, oferta.titulo, oferta.imagem)
        else:
            info = ml.itens([produto.id]).get(produto.id)
    except (ErroML, AcessoNegado):
        return oferta  # sem como conferir agora: vale a consulta de minutos atrás
    nova = avaliar(produto, info, estado, agora, cfg.min_desconto, cfg.repost_dias)
    if nova is None:
        log(f"{oferta.id}: o preço mudou antes do post; pulei.")
        return None
    nova.categoria = oferta.categoria
    return nova


def rodar(modo, cfg: Config, ml, tg, estado, produtos, agora=None, rng=random, tarefa=None):
    """Uma rodada completa. Retorna a lista de ofertas enviadas."""
    agora = agora or datetime.now(FUSO)
    infos = buscar_infos(ml, produtos, estado)

    candidatas = []
    for p in produtos:
        info = infos.get(p.id)
        if not info:
            log(f"Sem dados para {p.id} (linha {p.linha}) — anúncio pode ter sido removido.")
            continue
        motivo = motivo_bloqueio(info.titulo) or fora_da_faixa(
            info.titulo, p.categoria, (estado.get("descobertos", {}).get(p.id) or {}).get("regra"))
        if motivo:
            log(f"Bloqueado {p.id}: {motivo} — '{info.titulo[:60]}'")
            continue
        oferta = avaliar(p, info, estado, agora, cfg.min_desconto, cfg.repost_dias)
        if info.preco:
            est.registrar_preco(estado, p.id, float(info.preco), agora)
        if oferta:
            candidatas.append(oferta)

    posicoes = {pid: d.get("pos") for pid, d in estado.get("descobertos", {}).items()}
    manuais = estado.get("manuais", {})
    # Pedidos seus (busca/vigia) passam na frente
    candidatas.sort(key=lambda o: pontuacao(o, posicoes.get(o.id))
                    * (2.0 if (manuais.get(o.id) or {}).get("pedido") or (manuais.get(o.id) or {}).get("vigia") else 1.0),
                    reverse=True)
    if modo == "normal" and cfg.admin_chat:
        avisados = estado.setdefault("vigias_avisados", {})
        hoje = agora.date().isoformat()
        for o in candidatas:
            termo = (manuais.get(o.id) or {}).get("vigia")
            if termo and avisados.get(o.id) != hoje:
                avisados[o.id] = hoje
                try:
                    tg.enviar_texto(cfg.admin_chat, f"🔔 Promoção de <b>{html.escape(termo)}</b>: "
                                    f"{html.escape(o.titulo[:70])} por {mensagens.brl(o.preco)} "
                                    f"(-{round(o.desconto * 100)}%)\nhttps://www.mercadolivre.com.br/p/{o.id}", html=True)
                except TelegramErro:
                    pass
    log(f"{len(produtos)} produtos verificados, {len(candidatas)} ofertas encontradas.")

    if modo == "normal" and cfg.link_modo == "oficial":
        # Só posta quem já tem link oficial; o resto vai para o lote do Linkbuilder
        oficiais = [o for o in candidatas if not _link_direto(o.link)]
        sem_link = [(o, getattr(infos.get(o.id), "item_id", None)) for o in candidatas if _link_direto(o.link)]
        log(f"{len(oficiais)} com link oficial, {len(sem_link)} aguardando link.")
        estado["aguardando_link"] = len(sem_link)
        vitrine.guardar(estado, oficiais, agora)
        _talvez_mandar_lote(cfg, tg, estado, sem_link, agora)
        candidatas = oficiais

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

    # Ritmo: mais posts no almoço e à noite, sem gastar o limite do dia cedo demais
    vagas = min(
        cfg.max_por_rodada,
        limite_hora(cfg.max_por_hora, agora.hour) - est.posts_ultima_hora(estado, agora),
        min(cfg.max_por_dia, meta_ate_agora(cfg.max_por_dia, agora.hour, cfg.hora_inicio, cfg.hora_fim))
        - est.posts_hoje(estado, agora),
    )
    vagas = max(vagas, 0)
    enviadas = []
    if vagas and candidatas and cfg.atraso_max:
        # Atraso inicial: as rodadas começam em horário fixo, os posts não
        _esperar(rng.uniform(0, cfg.atraso_max) * 60, tarefa)
    por_id = {p.id: p for p in produtos}
    hoje = agora.date().isoformat()
    tipos_hoje = {tipo_produto(v.get("titulo", "")) for v in estado["postados"].values()
                  if v.get("quando", "").startswith(hoje) and v.get("titulo")}
    esperar_antes = False
    for o in candidatas:
        if len(enviadas) >= vagas:
            break
        tp = tipo_produto(o.titulo)
        if tp in tipos_hoje:
            continue  # já saiu um desse tipo hoje (ex.: outra babá eletrônica)
        if esperar_antes:
            espera = rng.uniform(cfg.intervalo_min, max(cfg.intervalo_max, cfg.intervalo_min))
            log(f"Próximo post em {espera:.1f} min.")
            _esperar(espera * 60, tarefa)
            esperar_antes = False
        o = _reconferir(ml, por_id.get(o.id), o, estado, cfg, agora)
        if o is None:
            continue  # tenta a próxima da fila, sem esperar de novo
        o.cupom = cupom_oferta.escolher_cupom(estado, o, agora, log=log)
        try:
            tg.enviar_oferta(cfg.canal, mensagens.montar_telegram(o, rng), o.imagem)
        except TelegramErro as e:
            log(f"Erro ao postar {o.id} no canal: {e}")
            continue
        esperar_antes = True
        whatsapp.enfileirar(mensagens.montar_whatsapp(o, rng), o.imagem, agora)
        est.registrar_post(estado, o.id, o.preco, agora, o.titulo, o.desconto)
        if o.cupom:
            est.contar_dia(estado, agora, "com_cupom")
        tipos_hoje.add(tp)
        enviadas.append(o)
        log(f"Postado: {o.id} {mensagens.brl(o.preco)} (-{round(o.desconto * 100)}%)")
        if cfg.admin_chat:
            try:
                comandos.enviar_copias(tg, cfg.admin_chat, o, rng)
            except TelegramErro as e:
                log(f"Aviso: não consegui mandar a cópia para você: {e}")
    return enviadas


def _link_direto(link):
    return "matt_word=" in (link or "")


def _talvez_mandar_lote(cfg, tg, estado, sem_link, agora):
    """Manda um lote para o Linkbuilder quando não há outro pendente.

    O próximo lote sai assim que você responde o anterior, até LOTES_POR_DIA.
    """
    if not cfg.admin_chat or not (cfg.hora_inicio <= agora.hour < cfg.hora_fim):
        return
    hoje = agora.date().isoformat()
    pendente = estado.get("lote") or {}
    if pendente.get("dia") == hoje and len(pendente.get("ids", [])) <= cfg.lote_tamanho:
        return  # ainda esperando sua resposta
    feitos = (estado.get("lotes_dia") or {}).get(hoje, 0)
    if feitos >= cfg.lotes_por_dia:
        return
    urls = lote.montar_lote(estado, sem_link, cfg.lote_tamanho, agora)
    if not urls:
        return
    try:
        tg.enviar_texto(cfg.admin_chat, lote.texto_lote(urls, feitos + 1, cfg.lotes_por_dia), html=True)
        estado["lotes_dia"] = {hoje: feitos + 1}
        log(f"Lote {feitos + 1} de {len(urls)} URLs enviado para o Linkbuilder.")
    except TelegramErro as e:
        estado["lote"] = None
        log(f"Aviso: não consegui mandar o lote: {e}")


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
    comandos.enviar_copias(tg, chat, oferta, rng)


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


def tarefas_rapidas(cfg, ml, tg, estado):
    """Suas mensagens, o canal de cupons e a validade dos cupons."""
    agora = datetime.now(FUSO)
    if not (cfg.hora_inicio <= agora.hour < cfg.hora_fim):
        return
    if cfg.admin_chat:
        comandos.processar(tg, ml, estado, cfg, agora, log)
    cupons_ml.processar(tg, cfg, estado, agora, log)
    comandos.verificar_cupons(tg, cfg, estado, agora, log)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["normal", "teste", "diagnostico", "rapido"], default="normal")
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
    if args.modo == "rapido":
        # Entre as rodadas: só suas mensagens e o canal de cupons (leve)
        try:
            ml, _ = conectar_ml(cfg)
            tarefas_rapidas(cfg, ml, Telegram(cfg.telegram_token), estado)
        except AcessoNegado as e:
            log(f"Mercado Livre recusou o acesso: {e}")
        finally:
            est.salvar(ARQ_ESTADO, estado)
        return 0
    try:
        ml, _ = conectar_ml(cfg)
        agora = datetime.now(FUSO)
        atualizar_descoberta(cfg, ml, estado, agora)
        lista = montar_lista(cfg, produtos, estado)
        if not lista:
            log("Nenhum produto para acompanhar (planilha vazia e descoberta sem resultado).")
            return 0
        tg = Telegram(cfg.telegram_token)
        if cfg.admin_chat and args.modo == "normal":
            comandos.processar(tg, ml, estado, cfg, agora, log)
            lista = montar_lista(cfg, produtos, estado)
        tarefa = (lambda: tarefas_rapidas(cfg, ml, tg, estado)) if args.modo == "normal" else None
        rodar(args.modo, cfg, ml, tg, estado, lista, agora=agora, tarefa=tarefa)
        if args.modo == "normal":
            from . import shopee_ofertas
            try:
                shopee_ofertas.rodar(cfg, tg, estado, datetime.now(FUSO), log=log,
                                     esperar=lambda s: _esperar(s, tarefa))
            except Exception as e:  # a Shopee nunca derruba o ciclo do Mercado Livre
                log(f"Aviso: Shopee falhou nesta rodada: {type(e).__name__}: {e}")
            if cfg.hora_inicio <= agora.hour < cfg.hora_fim:
                cupons_ml.processar(tg, cfg, estado, agora, log)
            comandos.verificar_cupons(tg, cfg, estado, agora, log)
            comandos.talvez_resumo_diario(tg, estado, cfg, agora, log)
            from . import conteudo
            if os.environ.get("PACOTE_AUTO") == "1":  # pausado: só sai quando você pede "pacote"
                conteudo.talvez_enviar(tg, cfg, estado, agora, hora=int(os.environ.get("PACOTE_HORA") or 10), log=log)
            vitrine.talvez_publicar(estado, cfg.canal, agora, log=log,
                                    grupo_wa=os.environ.get("WHATSAPP_GRUPO") or GRUPO_WHATSAPP)
            from . import numeros
            numeros.talvez_publicar(estado, agora, tg, cfg.canal, log=log)
    except AcessoNegado as e:
        log(f"Mercado Livre recusou o acesso: {e}\nRode o modo diagnostico para ver o que fazer.")
        return 1
    finally:
        est.salvar(ARQ_ESTADO, estado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
