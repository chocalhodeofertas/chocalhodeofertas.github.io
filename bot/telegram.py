"""Envio de mensagens pelo Telegram."""
import requests


class TelegramErro(Exception):
    pass


class Telegram:
    def __init__(self, token: str, session=None):
        self._url = f"https://api.telegram.org/bot{token}/"
        self.s = session or requests.Session()

    def _chamar(self, metodo, **dados):
        try:
            r = self.s.post(self._url + metodo, json=dados, timeout=30)
            j = r.json()
        except (requests.RequestException, ValueError) as e:
            # Não repassa a mensagem original: ela contém a URL com o token
            raise TelegramErro(f"falha de conexão com o Telegram ({type(e).__name__})")
        if not j.get("ok"):
            raise TelegramErro(j.get("description") or "erro desconhecido")
        return j["result"]

    def eu(self):
        return self._chamar("getMe")

    def membro(self, chat, user_id):
        return self._chamar("getChatMember", chat_id=chat, user_id=user_id)

    def membros(self, chat):
        return self._chamar("getChatMemberCount", chat_id=chat)

    def atualizacoes(self, offset=None):
        dados = {"limit": 100, "allowed_updates": ["message", "chat_member"]}
        if offset:
            dados["offset"] = offset
        return self._chamar("getUpdates", **dados)

    def enviar_texto(self, chat, texto, html=False, botoes=None):
        """botoes: lista de (rótulo, url), um botão por linha."""
        dados = {"chat_id": chat, "text": texto, "link_preview_options": {"is_disabled": True}}
        if html:
            dados["parse_mode"] = "HTML"
        if botoes:
            dados["reply_markup"] = {"inline_keyboard": [[{"text": t, "url": u}] for t, u in botoes]}
        return self._chamar("sendMessage", **dados)

    def enviar_oferta(self, chat, legenda_html, imagem=None):
        """Manda com foto; se a foto falhar, manda só o texto."""
        if imagem:
            try:
                return self._chamar(
                    "sendPhoto", chat_id=chat, photo=imagem, caption=legenda_html, parse_mode="HTML"
                )
            except TelegramErro:
                pass
        return self.enviar_texto(chat, legenda_html, html=True)
