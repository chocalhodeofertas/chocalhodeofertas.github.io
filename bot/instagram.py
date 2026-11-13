"""Cliente mínimo da API do Instagram (login unificado, token de usuário do sistema).

O token e o ID vêm dos GitHub Secrets INSTAGRAM_TOKEN e INSTAGRAM_USER_ID.
Nunca imprimir o token: as mensagens de erro passam por `_limpar`.
"""
import os

import requests

VERSAO = os.environ.get("INSTAGRAM_API_VERSAO") or "v26.0"
BASE = f"https://graph.facebook.com/{VERSAO}"


class InstagramErro(Exception):
    pass


class Instagram:
    def __init__(self, token: str, user_id: str, session=None):
        if not token or not user_id:
            raise InstagramErro("faltam os segredos INSTAGRAM_TOKEN e/ou INSTAGRAM_USER_ID")
        self.token = token
        self.user_id = str(user_id).strip()
        self.s = session or requests.Session()

    def _limpar(self, texto: str) -> str:
        return str(texto).replace(self.token, "***")

    def _get(self, caminho: str, **params):
        params["access_token"] = self.token
        try:
            r = self.s.get(f"{BASE}/{caminho}", params=params, timeout=30)
        except requests.RequestException as e:
            raise InstagramErro(self._limpar(e)) from None
        dados = r.json() if r.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
        if r.status_code != 200 or "error" in dados:
            erro = dados.get("error", {}) if isinstance(dados, dict) else {}
            raise InstagramErro(self._limpar(
                f"HTTP {r.status_code}: {erro.get('message') or r.text[:200]} (código {erro.get('code')})"))
        return dados

    def conta(self):
        return self._get(self.user_id, fields="username,name,followers_count,follows_count,media_count")

    def limite_publicacao(self):
        dados = self._get(f"{self.user_id}/content_publishing_limit", fields="quota_usage,config")
        return (dados.get("data") or [{}])[0]

    def posts(self, limite=10):
        dados = self._get(f"{self.user_id}/media", limit=limite,
                          fields="id,caption,media_type,timestamp,permalink,like_count,comments_count")
        return dados.get("data", [])

    def insights_conta(self, metricas=("reach", "views", "accounts_engaged", "total_interactions"), dias=7):
        import time
        fim = int(time.time())
        dados = self._get(f"{self.user_id}/insights", metric=",".join(metricas), period="day",
                          metric_type="total_value", since=fim - dias * 86400, until=fim)
        return {m["name"]: (m.get("total_value") or {}).get("value") for m in dados.get("data", [])}
