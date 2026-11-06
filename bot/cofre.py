"""Guarda o refresh_token do Mercado Livre criptografado no repositório.

O ML troca o refresh_token a cada uso, então o bot precisa salvar o novo em
algum lugar. Em vez de exigir um token do GitHub para atualizar secrets, ele
grava o valor criptografado em data/token_ml.enc. A chave vem do
ML_CLIENT_SECRET, que fica só nos secrets do GitHub.
"""
import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ARQ_TOKEN = Path(__file__).resolve().parent.parent / "data" / "token_ml.enc"


def _fernet(client_secret: str) -> Fernet:
    chave = hashlib.sha256(("chocalho-de-ofertas:" + client_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def guardar(refresh_token: str, client_secret: str, caminho=ARQ_TOKEN):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(_fernet(client_secret).encrypt(refresh_token.encode()) + b"\n")


def ler(client_secret: str, caminho=ARQ_TOKEN):
    """Retorna o refresh_token, ou None se não existir/não der para abrir."""
    caminho = Path(caminho)
    if not caminho.exists() or not caminho.read_bytes().strip():
        return None
    try:
        return _fernet(client_secret).decrypt(caminho.read_bytes().strip()).decode()
    except InvalidToken:
        return None
