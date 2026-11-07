"""Decide se o preço de um produto é uma oferta que vale postar."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Oferta:
    id: str
    titulo: str
    preco: float
    preco_de: Optional[float]  # preço "de" informado pelo próprio Mercado Livre
    desconto: float  # 0.30 = 30%
    abaixo_do_habitual: Optional[float]  # % abaixo do preço de referência da planilha
    menor_preco_historico: bool
    link: str
    imagem: Optional[str]
    categoria: str

    @property
    def forca(self):
        """Usado para ordenar: a melhor oferta vai primeiro."""
        return max(self.desconto, self.abaixo_do_habitual or 0) + (0.05 if self.menor_preco_historico else 0)


def avaliar(produto, info, estado, agora: datetime, min_desconto=0.15, repost_dias=3):
    """Retorna uma Oferta, ou None se não for hora de postar esse produto."""
    if not info or not info.disponivel or not info.preco:
        return None
    preco = float(info.preco)

    preco_de = None
    desconto = 0.0
    if info.preco_original and info.preco_original > preco:
        preco_de = float(info.preco_original)
        desconto = 1 - preco / preco_de

    abaixo = None
    if produto.preco_referencia and produto.preco_referencia > preco:
        abaixo = 1 - preco / produto.preco_referencia

    reg = estado["precos"].get(produto.id)
    menor_hist = bool(reg and len(reg["historico"]) >= 3 and preco < reg["min"] * 0.98)

    if not (desconto >= min_desconto or (abaixo or 0) >= min_desconto or menor_hist):
        return None

    postado = estado["postados"].get(produto.id)
    if postado:
        dias = (agora - datetime.fromisoformat(postado["quando"])).total_seconds() / 86400
        # Repete só depois de alguns dias, ou se o preço caiu mais 5%
        if dias < repost_dias and preco > postado["preco"] * 0.95:
            return None

    return Oferta(
        id=produto.id,
        titulo=info.titulo,
        preco=preco,
        preco_de=preco_de,
        desconto=desconto,
        abaixo_do_habitual=abaixo,
        menor_preco_historico=menor_hist,
        link=produto.link_afiliado,
        imagem=info.imagem,
        categoria=produto.categoria,
    )


# Comissão por categoria: roupa paga 16%, a maioria 12%
PESO_CATEGORIA = {"roupa": 1.3}

# Horários de pico (almoço e noite) recebem mais posts
PESO_HORA = {12: 1.6, 13: 1.6, 19: 1.6, 20: 1.6, 21: 1.6}


def pontuacao(oferta, posicao=None):
    """Desconto x comissão da categoria x popularidade (posição nos mais vendidos)."""
    bonus = 0.0
    if posicao is not None:
        bonus = 0.15 if posicao < 3 else 0.08 if posicao < 8 else 0.0
    return oferta.forca * PESO_CATEGORIA.get(oferta.categoria, 1.0) * (1 + bonus)


def meta_ate_agora(max_por_dia, hora, inicio=8, fim=22):
    """Quantos posts já 'deveriam' ter saído até o fim desta hora (ritmo do dia)."""
    pesos = {h: PESO_HORA.get(h, 1.0) for h in range(inicio, fim)}
    total = sum(pesos.values()) or 1
    feito = sum(v for h, v in pesos.items() if h <= hora)
    return int(max_por_dia * feito / total + 0.999)


def limite_hora(max_por_hora, hora):
    """No pico, até 2 posts a mais por hora."""
    return max_por_hora + (2 if hora in PESO_HORA else 0)
