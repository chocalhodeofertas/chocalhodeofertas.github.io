# DESIGN.md: Chocalho de Ofertas (site)

## Mundo visual
Refinado e confiável, não infantil. Campo noturno de uva com texto branco e lavanda; o pink só aparece na ação (WhatsApp) e nas marcas de queda de preço.
Recusa o visual de panfleto amarelo de promoção e o visual pastel arredondado de colagem.

## Cores
- Noite `#1E0524` (fundo do topo), uva `#3A0A40`, texto escuro `#24062A`
- Roxo `#8E2BB0` (nome da loja), lavanda `#F1E1FB` / `#E4CDF5` (segunda linha do título), névoa `#FBF7FD` (seções claras)
- Pink de ação `#DC1173` (passa AA com branco; o `#EA137A` da marca fica no logo e nas artes), pink escuro `#C80E66`
- Suave `#6B4F72`, linha `#EADCF1`

## Tipografia
Schibsted Grotesk (variável, subconjunto em `docs/fonts/schibsted.woff2`). Título 800 com espaçamento apertado; corpo 400/500.

## Forma
Raio 12-14 px (sem cantos de bala). Sombras neutras, nunca brilho colorido. Sem porcentagem em nenhum lugar.

## Peças
- Topo: marca + "Atualizado HH:MM", título em duas linhas, frase com número de produtos acompanhados, botão largo do WhatsApp, link pequeno do Telegram.
- Celular com o feed de ofertas rolando (pausável, para fora da tela, respeita movimento reduzido).
- Destaques do histórico: selos "Baixou de verdade" (≤ 90% do preço típico, 7+ dias) e "Menor preço em 30 dias".
- Grade de ofertas ML + Shopee com filtro por categoria; botão fixo do WhatsApp no celular quando os botões principais saem da tela.
