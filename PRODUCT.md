# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Famílias brasileiras com bebês e crianças até ~14 anos: mães e pais (muitos de primeira viagem), gestantes, e também tias, dindas e avós comprando presente. Chegam pelo celular, quase sempre de dentro do Instagram, TikTok ou WhatsApp (navegador interno do app), vindos da bio, de stories, de Reels ou de anúncio. Querem comprar o que a criança precisa pagando menos, sem caçar promoção sozinhos.

## Product Purpose
O Chocalho de Ofertas é um canal de ofertas de afiliado (Mercado Livre e Shopee) de produtos para bebês e crianças. Um bot procura, filtra e posta ofertas o dia todo no grupo do WhatsApp e no canal do Telegram. O site público (chocalhodeofertas.github.io) existe para levar a pessoa ao grupo do WhatsApp; a vitrine de ofertas do momento prova que vale a pena entrar. Sucesso do site = entradas no grupo; cliques em oferta são secundários.

## Positioning
O bot acompanha o preço de cada produto todo dia (histórico de 30 dias): sabe quando um preço baixou de verdade e quando o desconto é "de fachada". Por isso o Chocalho mostra preço e histórico, não porcentagem. Filtra o que não serve para criança (réplicas, itens adultos, NBCAL) e não repete o mesmo tipo de produto no dia.

## Operating Context
- O `docs/index.html` é gerado pelo bot (`bot/vitrine.py`) no máximo 1x por hora, com até 60 ofertas atuais; nunca editar o HTML à mão.
- `docs/grupo.html` é a página-ponte que abre o grupo do WhatsApp sozinha; é o destino da bio e dos anúncios.
- Página estática no GitHub Pages, sem backend; um único arquivo HTML com CSS e JS embutidos.
- Visitantes vêm de navegadores internos de apps em celulares, muitas vezes Android de entrada e internet móvel.

## Capabilities and Constraints
- Ofertas do Mercado Livre e da Shopee (decisão de 14/11/2026: as duas lojas no site, com o nome da loja no card).
- Telegram (2 membros) fica como link discreto; o WhatsApp é a ação principal.
- Na Shopee só aparece preço final ("A partir de" quando há opções); "de/por" só quando o próprio bot viu o preço cair.
- Links de afiliado oficiais, sem alteração. Shopee só pela API oficial.
- Nada de mamadeira, bico, chupeta, fórmula ou leite infantil (NBCAL), remédios, réplicas ou itens adultos.
- Pixel da Meta ainda não instalado (aguarda o ID do Leonardo); `grupo.html` já dispara `Lead` quando o Pixel existir.

## Brand Commitments
- Nome: Chocalho de Ofertas. Logo e ícone em `assets/marca/` (ursinho com chocalho, "Chocalho" branco em faixa uva, "de Ofertas" em faixa pink).
- Paleta da marca já usada nas artes: lavanda (#F1E1FB), uva (#3A0A40), roxo (#8E2BB0), pink (#EA137A). Fontes já usadas: Fredoka, Poppins.
- Texto sempre em português do Brasil.
- Nunca "achadinhos de bebê e criança" nem "ofertas de bebê e criança" (não tratar criança como produto); usar "produtos para bebês e crianças".
- Sem porcentagem em destaque; preço em "de/por" ou valor.
- Não explicar a comissão em detalhes; basta o aviso #publi de links de afiliado.
- O ursinho é ícone, não imagem de capa.

## Evidence on Hand
- Ofertas reais do bot (`data/estado.json`: `vitrine`, `postados`, `precos`, `shopee`).
- Página de números (membros: WhatsApp 11, Telegram 2 em 14/11/2026).
- Não existem depoimentos, avaliações de clientes nem números de economia comprovados: não inventar.

## Product Principles
1. O grupo do WhatsApp é o destino; tudo no site aponta para ele.
2. Mostrar o preço como ele é: valor e histórico, nunca porcentagem inflada.
3. Rápido e leve no celular, dentro do navegador do Instagram.
4. Falar com a família, não com caçador de promoção: cuidado, não gritaria de liquidação.

## Accessibility & Inclusion
Público amplo, de várias idades e aparelhos: contraste alto, texto legível no celular, áreas de toque grandes, funcionar com internet lenta.
