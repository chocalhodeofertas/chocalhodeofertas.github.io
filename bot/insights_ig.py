"""Coleta diária dos números do Instagram, para o relatório semanal.

- Uma vez por dia (na primeira rodada da manhã): grava data/instagram/AAAA-MM-DD.json com
  os números da CONTA no dia anterior (janela 00h–24h de Brasília) e um retrato de cada post
  dos últimos 30 dias (números ACUMULADOS desde a publicação até a hora da coleta).
- A cada rodada: guarda o último retrato dos stories no ar em data/instagram/stories.json
  (os números de story somem 24 h depois da publicação).

Métrica que o Instagram não entregar fica registrada em "ausentes", com o motivo.
Uso: python -m bot.insights_ig
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.instagram import Instagram, InstagramErro

FUSO = ZoneInfo("America/Sao_Paulo")
PASTA = Path("data/instagram")
DIAS_POSTS = 30
DIAS_STORIES = 60

METRICAS_CONTA = ["reach", "views", "accounts_engaged", "total_interactions", "likes", "comments",
                  "saves", "shares", "replies", "profile_links_taps"]
METRICAS_FEED = ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions",
                 "profile_visits", "profile_activity", "follows"]
METRICAS_REELS = ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions",
                  "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
METRICAS_STORY = ["reach", "views", "replies", "shares", "total_interactions", "navigation",
                  "profile_visits", "follows"]

NOTA = ("conta_no_dia = números da conta só naquele dia (janela de Brasília). "
        "posts[].metricas = números acumulados de cada post desde a publicação até coletado_em. "
        "Seguidores ganhos por dia = diferença de conta.seguidores entre dias seguidos; "
        "a API não diz qual post trouxe cada seguidor.")


def _legenda(p):
    return " ".join((p.get("caption") or "").split())[:120]


def _metricas_midia(p):
    tipo = p.get("media_product_type") or "FEED"
    if tipo == "REELS":
        return METRICAS_REELS
    if tipo == "STORY":
        return METRICAS_STORY
    return METRICAS_FEED


def retrato_midia(ig, p):
    params = {"breakdown": "story_navigation_action_type"} if p.get("media_product_type") == "STORY" else {}
    nomes = _metricas_midia(p)
    if params:  # "navigation" exige quebra; as outras métricas vão sem ela
        valores, ausentes = ig.metricas(p["id"], [n for n in nomes if n != "navigation"])
        v2, a2 = ig.metricas(p["id"], ["navigation"], **params)
        valores.update(v2), ausentes.update(a2)
    else:
        valores, ausentes = ig.metricas(p["id"], nomes)
    return {
        "id": p["id"],
        "formato": p.get("media_product_type") or "FEED",
        "tipo_midia": p.get("media_type"),
        "publicado_em": p.get("timestamp"),
        "link": p.get("permalink"),
        "legenda": _legenda(p),
        "curtidas": p.get("like_count"),
        "comentarios": p.get("comments_count"),
        "metricas": valores,
        "ausentes": ausentes,
    }


def coletar_dia(ig, dia, agora):
    inicio = datetime(dia.year, dia.month, dia.day, tzinfo=FUSO)
    fim = inicio + timedelta(days=1)
    janela = {"since": int(inicio.timestamp()), "until": int(fim.timestamp())}
    conta = ig.conta()
    m_conta, a_conta = ig.metricas(ig.user_id, METRICAS_CONTA, period="day", metric_type="total_value", **janela)
    m2, a2 = ig.metricas(ig.user_id, ["follows_and_unfollows"], period="day", metric_type="total_value",
                         breakdown="follow_type", **janela)
    m_conta.update(m2), a_conta.update(a2)
    posts = [retrato_midia(ig, p) for p in ig.posts_desde((agora - timedelta(days=DIAS_POSTS)).timestamp())]
    return {
        "dia": dia.isoformat(),
        "coletado_em": agora.isoformat(timespec="seconds"),
        "nota": NOTA,
        "conta": {"usuario": conta.get("username"), "seguidores": conta.get("followers_count"),
                  "seguindo": conta.get("follows_count"), "posts": conta.get("media_count")},
        "conta_no_dia": {"janela": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
                         "metricas": m_conta, "ausentes": a_conta},
        "posts": posts,
    }


def atualizar_stories(ig, agora, pasta=PASTA):
    arq = pasta / "stories.json"
    salvos = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    for s in ig.stories():
        r = retrato_midia(ig, s)
        r["coletado_em"] = agora.isoformat(timespec="seconds")
        salvos[s["id"]] = r
    corte = (agora - timedelta(days=DIAS_STORIES)).isoformat()
    salvos = {k: v for k, v in salvos.items() if (v.get("publicado_em") or "") >= corte[:10]}
    pasta.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(salvos, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(salvos)


def _avisar_admin(texto, agora, pasta=PASTA):
    """No máximo um aviso por dia, para não lotar o Telegram se o token cair."""
    marca = pasta / "_ultimo_aviso.txt"
    hoje = agora.date().isoformat()
    if marca.exists() and marca.read_text().strip() == hoje:
        return
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if token and chat:
        from bot.telegram import Telegram
        try:
            Telegram(token).enviar_texto(chat, texto)
        except Exception as e:  # aviso é opcional; não derruba a coleta
            print("Aviso ao admin falhou:", type(e).__name__)
            return
    pasta.mkdir(parents=True, exist_ok=True)
    marca.write_text(hoje)


def rodar(ig=None, agora=None, pasta=PASTA):
    agora = agora or datetime.now(FUSO)
    if not (os.environ.get("INSTAGRAM_TOKEN") and os.environ.get("INSTAGRAM_USER_ID")) and ig is None:
        print("Instagram: sem token configurado; pulando coleta.")
        return 0
    ig = ig or Instagram(os.environ["INSTAGRAM_TOKEN"], os.environ["INSTAGRAM_USER_ID"])
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        n = atualizar_stories(ig, agora, pasta)
        print(f"Instagram: {n} stories guardados.")
        ontem = agora.date() - timedelta(days=1)
        arq = pasta / f"{ontem.isoformat()}.json"
        if arq.exists():
            return 0
        dados = coletar_dia(ig, ontem, agora)
        arq.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        faltas = len(dados["conta_no_dia"]["ausentes"]) + sum(bool(p["ausentes"]) for p in dados["posts"])
        print(f"Instagram: dia {ontem} coletado ({len(dados['posts'])} posts; {faltas} itens com métrica ausente).")
        return 0
    except InstagramErro as e:
        print("Instagram: coleta falhou:", e)
        _avisar_admin(f"⚠️ Coleta de números do Instagram falhou: {e}", agora, pasta)
        return 1


if __name__ == "__main__":
    sys.exit(rodar())
