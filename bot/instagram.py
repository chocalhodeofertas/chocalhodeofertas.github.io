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

    def _post(self, caminho: str, **dados):
        dados["access_token"] = self.token
        try:
            r = self.s.post(f"{BASE}/{caminho}", data=dados, timeout=60)
        except requests.RequestException as e:
            raise InstagramErro(self._limpar(e)) from None
        try:
            j = r.json()
        except ValueError:
            j = {}
        if r.status_code != 200 or "error" in j:
            erro = j.get("error", {}) if isinstance(j, dict) else {}
            raise InstagramErro(self._limpar(
                f"HTTP {r.status_code}: {erro.get('error_user_msg') or erro.get('message') or r.text[:200]} "
                f"(código {erro.get('code')})"))
        return j

    def _esperar_pronto(self, container_id, tentativas=30, espera=5, dormir=None):
        import time
        dormir = dormir or time.sleep
        for _ in range(tentativas):
            st = self._get(container_id, fields="status_code,status").get("status_code")
            if st == "FINISHED":
                return
            if st in ("ERROR", "EXPIRED"):
                raise InstagramErro(f"o Instagram recusou a mídia ({st})")
            dormir(espera)
        raise InstagramErro("o Instagram demorou demais para processar as imagens")

    def publicar_carrossel(self, urls_imagens, legenda, dormir=None):
        """Publica um carrossel (2 a 10 imagens JPEG em URLs públicas). Devolve (id, link)."""
        if not 2 <= len(urls_imagens) <= 10:
            raise InstagramErro("o carrossel precisa ter de 2 a 10 imagens")
        filhos = []
        for url in urls_imagens:
            filhos.append(self._post(f"{self.user_id}/media", image_url=url, is_carousel_item="true")["id"])
        for f in filhos:
            self._esperar_pronto(f, dormir=dormir)
        cont = self._post(f"{self.user_id}/media", media_type="CAROUSEL", children=",".join(filhos),
                          caption=legenda)["id"]
        self._esperar_pronto(cont, dormir=dormir)
        mid = self._post(f"{self.user_id}/media_publish", creation_id=cont)["id"]
        link = self._get(mid, fields="permalink").get("permalink")
        return mid, link

    def conta(self):
        return self._get(self.user_id, fields="username,name,followers_count,follows_count,media_count")

    def limite_publicacao(self):
        dados = self._get(f"{self.user_id}/content_publishing_limit", fields="quota_usage,config")
        return (dados.get("data") or [{}])[0]

    def posts(self, limite=10):
        dados = self._get(f"{self.user_id}/media", limit=limite,
                          fields="id,caption,media_type,timestamp,permalink,like_count,comments_count")
        return dados.get("data", [])

    CAMPOS_MIDIA = "id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count"

    def posts_desde(self, desde_ts, maximo=200):
        """Posts do feed/reels publicados a partir de `desde_ts` (epoch), do mais novo ao mais velho."""
        from datetime import datetime
        achados, depois = [], None
        while len(achados) < maximo:
            params = {"limit": 50, "fields": self.CAMPOS_MIDIA}
            if depois:
                params["after"] = depois
            dados = self._get(f"{self.user_id}/media", **params)
            pagina = dados.get("data", [])
            for p in pagina:
                if datetime.strptime(p["timestamp"], "%Y-%m-%dT%H:%M:%S%z").timestamp() < desde_ts:
                    return achados
                achados.append(p)
            depois = ((dados.get("paging") or {}).get("cursors") or {}).get("after")
            if not pagina or not (dados.get("paging") or {}).get("next"):
                break
        return achados

    def stories(self):
        return self._get(f"{self.user_id}/stories", fields=self.CAMPOS_MIDIA).get("data", [])

    def metricas(self, obj_id, nomes, **params):
        """Lê métricas de insights. Se o pedido conjunto falhar, tenta uma a uma.

        Devolve (valores, ausentes): ausentes = {métrica: motivo} para o que o Instagram não entregou.
        """
        def ler(lista):
            dados = self._get(f"{obj_id}/insights", metric=",".join(lista), **params)
            vals = {}
            for m in dados.get("data", []):
                if "total_value" in m:
                    tv = m["total_value"] or {}
                    quebras = tv.get("breakdowns")
                    if quebras:
                        vals[m["name"]] = {"total": tv.get("value"), **{
                            "_".join(r.get("dimension_values", [])) or "?": r.get("value")
                            for b in quebras for r in b.get("results", [])}}
                    else:
                        vals[m["name"]] = tv.get("value")
                else:
                    pontos = m.get("values") or []
                    vals[m["name"]] = pontos[-1].get("value") if pontos else None
            return vals

        try:
            valores = ler(nomes)
            ausentes = {n: "não veio na resposta" for n in nomes if n not in valores}
            return valores, ausentes
        except InstagramErro:
            pass
        valores, ausentes = {}, {}
        for n in nomes:
            try:
                valores.update(ler([n]))
                if n not in valores:
                    ausentes[n] = "não veio na resposta"
            except InstagramErro as e:
                ausentes[n] = str(e)[:160]
        return valores, ausentes

    def insights_conta(self, metricas=("reach", "views", "accounts_engaged", "total_interactions"), dias=7):
        import time
        fim = int(time.time())
        dados = self._get(f"{self.user_id}/insights", metric=",".join(metricas), period="day",
                          metric_type="total_value", since=fim - dias * 86400, until=fim)
        return {m["name"]: (m.get("total_value") or {}).get("value") for m in dados.get("data", [])}
