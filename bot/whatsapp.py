"""Fila de posts para o grupo do WhatsApp.

O bot (Python) só deixa um arquivo na pasta WA_FILA; quem posta é o serviço
em wa/servico.mjs, que roda junto com o ciclo e controla o ritmo. Sem WA_FILA
(ex.: rodando local ou nos testes), não faz nada.
"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path


PONTOS_AVISO = 9.0  # cupons, tabela de fraldas e resumo do dia: sempre passam na frente das ofertas


def forca(oferta):
    """Quão forte é a oferta, para o grupo do WhatsApp receber as melhores (o limite diário de lá é pequeno).
    Queda vista pelo próprio bot vale mais que o "de" do anúncio; selo e cupom somam um pouco."""
    preco = getattr(oferta, "preco", 0) or 0
    normal, de = getattr(oferta, "preco_normal", None), getattr(oferta, "preco_de", None)
    real = 1 - preco / normal if normal and normal > preco else 0
    anuncio = 1 - preco / de if de and de > preco else 0
    pontos = max(real * 1.5, min(anuncio, 0.6) * 0.6)
    pontos += 0.05 if getattr(oferta, "selo_dias", None) else 0
    pontos += 0.05 if getattr(oferta, "cupom", None) else 0
    return round(pontos, 4)


def enfileirar(texto, imagem=None, agora=None, loja="ml", png=None, preview=None, pontos=PONTOS_AVISO, oferta=None,
               categoria=None, mencionar=False):
    """png: bytes de uma arte pronta (vai junto na fila e tem prioridade sobre a URL da foto).
    pontos: prioridade na fila (o serviço posta primeiro o que tem mais pontos).
    categoria: o serviço evita duas ofertas seguidas da mesma categoria.
    mencionar: menção oculta (todos do grupo notificados, sem "@" no texto). Só quando o Leonardo pede
    (comando `marcar`): nunca automático."""
    pasta = os.environ.get("WA_FILA")
    if not pasta or not texto:
        return False
    p = Path(pasta)
    p.mkdir(parents=True, exist_ok=True)
    quando = agora or datetime.now().astimezone()
    base = time.time_ns()
    if png:
        arq = (p / f"{base}.png").resolve()
        arq.write_bytes(png)
        imagem = str(arq)
        if preview:
            preview = {**preview, "imagem": imagem}  # prévia do link usa a arte pronta (cartão com a marca)
    item = {"texto": texto, "imagem": imagem or None, "criado": quando.isoformat(), "loja": loja, "pontos": pontos}
    if preview:
        item["preview"] = preview
    if oferta:
        item["oferta"] = oferta
    if categoria:
        item["categoria"] = categoria
    if mencionar:
        item["mencionar"] = True
    nome = p / f"{base}.json"
    tmp = nome.with_suffix(".tmp")
    tmp.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    tmp.rename(nome)
    return True


def cartao_da_oferta(oferta, session=None):
    """Cartão com a marca para a prévia (PREVIA_MARCA=1, aprovado pelo Leonardo). Desligado ou falhou → None
    (a prévia usa a foto do anúncio, como antes)."""
    if os.environ.get("PREVIA_MARCA") != "1":
        return None
    try:
        from . import arte

        foto = arte.baixar_foto(oferta.imagem, session)
        return arte.cartao_previa(foto) if foto is not None else None
    except Exception:  # noqa: BLE001 — sem cartão, segue com a foto do anúncio
        return None


def enfileirar_oferta(oferta, texto, agora=None, loja="ml", mencionar=False):
    """Oferta para o grupo como texto com a prévia grande do link (foto + nome do produto),
    igual aos grupos de ofertas grandes. O serviço monta a prévia com a foto do anúncio;
    se não conseguir, manda a foto com o texto na legenda."""
    m = re.search(r"https?://\S+", texto or "")
    preview = None
    cartao = None
    if m and getattr(oferta, "imagem", None):
        preview = {"link": m.group(0), "titulo": oferta.titulo, "imagem": oferta.imagem}
        cartao = cartao_da_oferta(oferta)
    meta = ({"id": oferta.id, "preco": oferta.preco}  # para conferir o preço antes de sair (conferir_fila)
            if getattr(oferta, "id", None) and getattr(oferta, "preco", None) else None)
    from .ofertas import categoria_efetiva

    return enfileirar(texto, getattr(oferta, "imagem", None), agora, loja, png=cartao, preview=preview,
                      pontos=PONTOS_AVISO if mencionar else forca(oferta), oferta=meta,
                      categoria=categoria_efetiva(getattr(oferta, "categoria", ""), oferta.titulo), mencionar=mencionar)


SUBIU_TOLERANCIA = 0.02  # subiu mais que 2% desde que entrou na fila → não sai no grupo


def conferir_fila(estado, agora, ml=None, shp=None, log=print):
    """A cada rodada (uns 20 min), confere pela API o preço das ofertas que esperam no grupo do WhatsApp.
    Subiu mais de 2%, acabou o estoque ou o anúncio do link saiu → tira da fila (e anota para a página da fila).
    Baixou → fica, com o texto de quando entrou (a pessoa encontra um preço melhor). Sem como conferir → fica."""
    from . import lote

    pasta = os.environ.get("WA_FILA")
    if not pasta or not Path(pasta).is_dir():
        return 0
    tirados = 0
    reg = estado.get("wa_conferidos") or {}
    if reg.get("dia") != agora.date().isoformat():
        reg = {"dia": agora.date().isoformat(), "itens": []}
    for arq in sorted(Path(pasta).glob("*.json")):
        try:
            item = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = item.get("oferta") or {}
        if not meta.get("id") or not meta.get("preco"):
            continue
        try:
            if item.get("loja") == "shopee":
                if shp is None:
                    continue
                p = shp.item(int(str(meta["id"]).removeprefix("SHP")))
                agora_preco = p.preco if p else None
            else:
                if ml is None:
                    continue
                info = ml.catalogo(meta["id"], "-", None)
                if not lote.conferir_anuncio(estado, meta["id"], info, log, getattr(ml, "procurar_anuncio", None)):
                    agora_preco = None
                else:
                    agora_preco = info.preco if info.disponivel else None
        except Exception as e:  # noqa: BLE001 — sem conferir agora: deixa na fila
            log(f"WhatsApp: não deu para conferir {meta['id']}: {type(e).__name__}")
            continue
        motivo = None
        if agora_preco is None:
            motivo = "acabou"
        elif agora_preco > meta["preco"] * (1 + SUBIU_TOLERANCIA):
            motivo = "subiu"
        if motivo:
            try:
                arq.unlink()
            except OSError:
                continue
            tirados += 1
            link = re.search(r"https?://\S+", item.get("texto") or "")
            reg["itens"].append({"h": agora.isoformat(), "k": link.group(0) if link else None, "r": motivo,
                                 "l": item.get("loja") or "ml", "de": meta["preco"], "agora": agora_preco})
            log(f"WhatsApp: tirei {meta['id']} da fila ({'o preço subiu' if motivo == 'subiu' else 'acabou'}).")
    reg["itens"] = reg["itens"][-100:]
    estado["wa_conferidos"] = reg
    return tirados
