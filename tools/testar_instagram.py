"""Teste da API do Instagram: confere o token e manda um resumo SÓ para o admin.

Não publica nada. Uso (workflow "Inspecionar"): script = testar_instagram.
"""
import html
import json
import os
import sys
from pathlib import Path

from bot.instagram import Instagram, InstagramErro
from bot.telegram import Telegram


def main():
    ig = Instagram(os.environ.get("INSTAGRAM_TOKEN"), os.environ.get("INSTAGRAM_USER_ID"))
    resultado, linhas = {}, ["📸 <b>Teste da API do Instagram</b> (nada foi publicado)"]
    passos = [("conta", ig.conta), ("limite", ig.limite_publicacao),
              ("posts", lambda: ig.posts(5)), ("insights_7d", ig.insights_conta)]
    for nome, chamada in passos:
        try:
            resultado[nome] = chamada()
            print("OK", nome)
        except InstagramErro as e:
            resultado[nome] = {"erro": str(e)}
            print("ERRO", nome, e)
    conta = resultado["conta"]
    if "erro" in conta:
        return "não consegui ler a conta: " + conta["erro"]
    linhas.append(f"✅ Conta @{html.escape(conta.get('username', '?'))}: {conta.get('followers_count')} seguidores, "
                  f"{conta.get('media_count')} posts")
    lim = resultado["limite"]
    linhas.append("✅ Publicação liberada: " + (f"{lim.get('quota_usage', 0)} de {(lim.get('config') or {}).get('quota_total', 50)} posts usados nas últimas 24 h"
                                               if "erro" not in lim else "❌ " + html.escape(lim["erro"])))
    ins = resultado["insights_7d"]
    linhas.append("✅ Insights (7 dias): " + (", ".join(f"{k} {v}" for k, v in ins.items())
                                              if "erro" not in ins else "❌ " + html.escape(ins["erro"])))
    posts = resultado["posts"]
    if isinstance(posts, list):
        linhas.append(f"✅ Leitura de posts: {len(posts)} mais recentes")
    else:
        linhas.append("❌ Posts: " + html.escape(posts["erro"]))
    Path("saida").mkdir(exist_ok=True)
    Path("saida/instagram.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1))
    texto = "\n".join(linhas)
    print(texto)
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_ADMIN_CHAT_ID"):
        Telegram(os.environ["TELEGRAM_BOT_TOKEN"]).enviar_texto(os.environ["TELEGRAM_ADMIN_CHAT_ID"], texto, html=True)
    return None


if __name__ == "__main__":
    try:
        erro = main()
    except InstagramErro as e:
        erro = str(e)
    if erro and os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_ADMIN_CHAT_ID"):
        Telegram(os.environ["TELEGRAM_BOT_TOKEN"]).enviar_texto(
            os.environ["TELEGRAM_ADMIN_CHAT_ID"], f"⚠️ Teste do Instagram falhou: {erro}")
    sys.exit(1 if erro else 0)
