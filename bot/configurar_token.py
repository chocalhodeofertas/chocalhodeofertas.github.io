"""Primeira autorização do Mercado Livre (roda pelo GitHub Actions).

Troca o código que aparece na URL depois de autorizar o app por um
refresh_token, e salva como secret ML_REFRESH_TOKEN no repositório.
"""
import os
import sys

from .mercadolivre import AcessoNegado, ErroML, salvar_secret, trocar_codigo


def main():
    cid = os.environ.get("ML_CLIENT_ID")
    secret = os.environ.get("ML_CLIENT_SECRET")
    codigo = (os.environ.get("CODIGO") or "").strip()
    redirect = (os.environ.get("REDIRECT_URI") or "").strip()
    faltando = [n for n, v in [("ML_CLIENT_ID", cid), ("ML_CLIENT_SECRET", secret),
                               ("código", codigo), ("redirect_uri", redirect)] if not v]
    if faltando:
        print("Faltando: " + ", ".join(faltando))
        return 1
    # Aceita a URL inteira colada, não só o código
    if "code=" in codigo:
        codigo = codigo.split("code=", 1)[1].split("&", 1)[0]
    try:
        _, refresh = trocar_codigo(cid, secret, codigo, redirect)
    except (AcessoNegado, ErroML) as e:
        print(f"Não deu certo: {e}")
        print("O código vale poucos minutos e só pode ser usado uma vez. Gere outro e tente de novo.")
        return 1
    if salvar_secret("ML_REFRESH_TOKEN", refresh):
        print("✅ Token do Mercado Livre salvo! Agora rode o bot no modo diagnostico.")
        return 0
    print("Consegui o token, mas não consegui salvá-lo. Confira se o secret GH_PAT está configurado.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
