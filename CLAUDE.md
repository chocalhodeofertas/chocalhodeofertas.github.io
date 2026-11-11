# Chocalho de Ofertas: mapa técnico

Bot de ofertas de afiliado (Mercado Livre + Shopee) para produtos de bebês e crianças até ~14 anos.
Posta no canal do Telegram e no grupo do WhatsApp; gera artes para Instagram/TikTok.
Textos para o dono do projeto sempre em português do Brasil.

## Como roda
- `.github/workflows/ciclo.yml`: ciclo de ~5,5 h que se redispara sozinho (`python -m bot.ciclo`).
  Sobe junto `node wa/servico.mjs` (WhatsApp) e commita `data/` no fim.
- `.github/workflows/inspecao.yml`: ferramenta de teste, roda `python -m tools.<script> "<args>"`.
  O que for gravado em `saida/` vai para o branch `tmp-saida`, para baixar com git clone.
- Disparar workflow: `gh api -X POST repos/chocalhodeofertas/chocalhodeofertas.github.io/actions/workflows/<arq>.yml/dispatches -f ref=main -f 'inputs[script]=...'`.
  Pelo proxy do container não dá para criar variáveis nem segredos (403): padrões ficam no próprio workflow (`vars.X || 'padrão'`).
- Testes: `python3 -m pytest -q tests` (tudo em `tests/test_bot.py`). Rodar antes de cada commit.
- Antes de dar push: `git pull --rebase` (o ciclo commita `data/` sozinho).

## Módulos principais (bot/)
- `main.py`: rodada do ML (descoberta, avaliação, ritmo, postagem); chama Shopee, cupons, vitrine e números.
- `ofertas.py`: `Oferta`, `avaliar`, `pontuacao`, `tipo_produto`, ritmo (`limite_hora`, `meta_ate_agora`).
- Histórico de preços (`estado.precos`, só quando o preço muda): `estado.preco_tipico` = mediana dia a dia dos últimos 30 dias.
  Com 7+ dias de histórico, `ofertas.peso_queda_real` dá +30% na pontuação para queda real ≥ 10% e -40% para desconto "de fachada" (< 3%).
  Quem sai dos mais vendidos do ML vai para `estado.acompanhados` (30 dias, 1/3 por rodada); na Shopee, produtos aprovados vão para
  `shopee.acompanhados` e 15 por rodada são reconferidos por `itemId` (queda real ≥ 10% vira candidato).
- Repetição: `estado.repetido` compara títulos (ML + Shopee) dos últimos 3 dias; volta antes só se o preço cair 5%.
- `filtros.py`: bloqueios (NBCAL, remédio, +14 anos, réplica) e `fora_da_faixa` (casa/adulto, exige sinal infantil).
- `mensagens.py`: textos do Telegram/WhatsApp, frases de abertura por produto, linha de cupom, Shopee ("A partir de", nota e vendas).
- `cupons_ml.py` + `cupom_oferta.py`: lê cupons (canal oficial do ML + @cupombr via Telethon) e aplica o melhor cupom compatível na oferta.
- `shopee.py`: cliente da Open API de afiliados (GraphQL, assinatura SHA256). Repete em erro 10000/10030.
- `shopee_ofertas.py`: ofertas da Shopee por cima das do ML (limite próprio: `SHOPEE_MAX_DIA` 50, `SHOPEE_MAX_HORA` 4).
  Regras: nota ≥ 4,7, vendas ≥ 500, comissão ≥ 5%, só preço final; "de/por" só com queda vista pelo próprio bot.
  Links via `generateShortLink` com subId `telegram` / `whatsapp`.
- `whatsapp.py` + `wa/servico.mjs`: fila em `fila_wa/`; o serviço (Baileys) posta com aquecimento automático
  (4 → 20 posts/dia em 30 dias), só das 7h às 23h, alterna ML/Shopee, pausa 48 h se o WhatsApp sinalizar restrição, apaga links de não-admins.
- `numeros.py`: página escondida `docs/numeros-bcfc6fce.html` (membros, ofertas, cupons, WhatsApp).
- `comandos.py`: comandos do admin no Telegram e resumo diário (inclui WhatsApp).
- `tiktok.py`: renderizador dos carrosséis 1080x1350 (capa, produto, CTA).

## Ferramentas (tools/, rodar pelo workflow inspecao)
- `testar_shopee`: prévia de busca da Shopee só para o admin.
- `exemplos_shopee`: 3 posts de exemplo da Shopee só para o admin.
- `produto_shopee <itemId>`: dados e foto de um produto da Shopee (foto vai para `saida/`).
- `baixar nome=url ...`: baixa arquivos para `saida/` (o container não alcança mlstatic/Shopee/Canva).

## Regras que o código precisa respeitar
- NBCAL: nunca mamadeira, bico, chupeta, fórmula/leite infantil.
- Links de afiliado oficiais e sem alteração; Shopee só pela API oficial (nada de raspar o site); cupons só oficiais.
- Segredos só em GitHub Secrets; nunca imprimir tokens em log.
