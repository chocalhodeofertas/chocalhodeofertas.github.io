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
        dados = {"limit": 100, "allowed_updates": ["message", "chat_member", "callback_query"]}
        if offset:
            dados["offset"] = offset
        return self._chamar("getUpdates", **dados)

    def editar_texto(self, chat, message_id, texto, html=True):
        dados = {"chat_id": chat, "message_id": message_id, "text": texto,
                 "link_preview_options": {"is_disabled": True}}
        if html:
            dados["parse_mode"] = "HTML"
        return self._chamar("editMessageText", **dados)

    def enviar_texto(self, chat, texto, html=False, botoes=None, responder_a=None, acoes=None):
        """botoes: lista de (rótulo, url), um botão por linha.
        acoes: lista de (rótulo, callback_data), lado a lado numa linha (o bot recebe o toque)."""
        dados = {"chat_id": chat, "text": texto, "link_preview_options": {"is_disabled": True}}
        if responder_a:
            dados["reply_parameters"] = {"message_id": responder_a}
        if html:
            dados["parse_mode"] = "HTML"
        if botoes:
            dados["reply_markup"] = {"inline_keyboard": [[{"text": t, "url": u}] for t, u in botoes]}
        if acoes:
            dados["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in acoes]]}
        return self._chamar("sendMessage", **dados)

    def responder_toque(self, callback_id, texto=None):
        """Tira o 'carregando' do botão tocado (e mostra um aviso curto, se houver)."""
        dados = {"callback_query_id": callback_id}
        if texto:
            dados["text"] = texto[:190]
        return self._chamar("answerCallbackQuery", **dados)

    def enviar_foto(self, chat, png, legenda=None, nome="arte.png"):
        """Envia uma imagem gerada pelo bot (bytes)."""
        dados = {"chat_id": str(chat)}
        if legenda:
            dados["caption"] = legenda
        try:
            r = self.s.post(self._url + "sendPhoto", data=dados, files={"photo": (nome, png, "image/png")},
                            timeout=60)
            j = r.json()
        except (requests.RequestException, ValueError) as e:
            raise TelegramErro(f"falha de conexão com o Telegram ({type(e).__name__})")
        if not j.get("ok"):
            raise TelegramErro(j.get("description") or "erro desconhecido")
        return j["result"]

    def _multipart(self, metodo, dados, arquivos, timeout=120):
        try:
            r = self.s.post(self._url + metodo, data=dados, files=arquivos, timeout=timeout)
            j = r.json()
        except (requests.RequestException, ValueError) as e:
            raise TelegramErro(f"falha de conexão com o Telegram ({type(e).__name__})")
        if not j.get("ok"):
            raise TelegramErro(j.get("description") or "erro desconhecido")
        return j["result"]

    def enviar_album(self, chat, pngs, legenda=None):
        """Até 10 imagens num álbum só (para salvar o carrossel de uma vez)."""
        import json as _json
        midia, arquivos = [], {}
        for i, png in enumerate(pngs[:10]):
            item = {"type": "photo", "media": f"attach://f{i}"}
            if i == 0 and legenda:
                item["caption"] = legenda
            midia.append(item)
            arquivos[f"f{i}"] = (f"slide{i + 1}.png", png, "image/png")
        return self._multipart("sendMediaGroup", {"chat_id": str(chat), "media": _json.dumps(midia)}, arquivos)

    def enviar_documento(self, chat, dados_arq, nome, legenda=None, tipo="application/octet-stream"):
        """Manda como arquivo (sem compressão do Telegram)."""
        dados = {"chat_id": str(chat)}
        if legenda:
            dados["caption"] = legenda
        return self._multipart("sendDocument", dados, {"document": (nome, dados_arq, tipo)})

    def enviar_video(self, chat, mp4, legenda=None, nome="reel.mp4"):
        dados = {"chat_id": str(chat), "supports_streaming": "true", "width": "1080", "height": "1920"}
        if legenda:
            dados["caption"] = legenda
        return self._multipart("sendVideo", dados, {"video": (nome, mp4, "video/mp4")}, timeout=300)

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
