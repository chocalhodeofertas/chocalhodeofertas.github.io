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
- `.github/workflows/vigia.yml`: cron de 30 em 30 min; se não houver execução do ciclo rodando ou na fila, religa e avisa o admin
  (respeita o ciclo desligado de propósito).
- Testes: `python3 -m pytest -q tests` (tudo em `tests/test_bot.py`). Rodar antes de cada commit.
- Antes de dar push: `git pull --rebase` (o ciclo commita `data/` sozinho).

## Módulos principais (bot/)
- `main.py`: rodada do ML (descoberta, avaliação, ritmo, postagem); chama Shopee, cupons, vitrine e números.
- `ofertas.py`: `Oferta`, `avaliar`, `pontuacao`, `tipo_produto`, ritmo (`limite_hora`, `meta_ate_agora`).
- `horario.py`: horário de postagem (`ativo`) + janela da meia-noite (`DATAS_MEIA_NOITE`, padrão Black Friday 27/11 e 12.12):
  das 23h30 da véspera à 1h o ciclo, o ML, a Shopee e o WhatsApp (`wa/comum.mjs: naMeiaNoite`) também postam;
  na janela vale só o limite por hora (`ofertas.vagas_da_rodada`), fora da conta do dia (WhatsApp: até 6 extras).
- `sazonal.py`: calendário do ano (Natal, volta às aulas, verão, Carnaval, Páscoa, inverno, festa junina, Dia das Crianças,
  Halloween). Produto da época ganha peso em `ofertas.pontuacao(..., agora)` e em `shopee_ofertas.pontos`; a busca da Shopee
  ganha 1 palavra-chave da época por rodada. Não muda o que é oferta, só a ordem.
- Histórico de preços (`estado.precos`): no mesmo dia cada preço fica uma vez só (último registro = preço em vigor;
  `estado.compactar_precos` enxuga dados antigos ao carregar). `estado.serie_diaria` = MENOR preço de cada dia (no ML ~8% dos
  produtos alternam entre dois preços a cada consulta; o menor do dia é o que estava disponível).
  `estado.preco_tipico` = mediana dessa série nos últimos 30 dias (hoje fica de fora).
  Com 7+ dias de histórico, `ofertas.peso_queda_real` dá +30% na pontuação para queda real ≥ 10% e -40% para desconto "de fachada" (< 3%).
  Quem sai dos mais vendidos do ML vai para `estado.acompanhados` (30 dias, 1/3 por rodada); na Shopee, produtos aprovados vão para
  `shopee.acompanhados` e 15 por rodada são reconferidos por `itemId` (queda real ≥ 10% vira candidato).
- Quando vira oferta (ML, `main.avaliar_oferta`): desconto do anúncio ≥ `MIN_DESCONTO` (20%); ≥ 15% se está entre os 3 mais vendidos
  da categoria; ≥ 10% se veio do espelho; ≥ 10% + cupom do canal que leve o total a 20%; ou queda real ≥ 10% sobre o preço típico
  (7+ dias de histórico), mesmo sem "de" no anúncio (o post mostra "📉 Baixou: vinha custando R$ X no histórico do Chocalho").
- Selo no post (`ofertas.selo_menor_preco`, ML e Shopee): "📉 Menor preço que o Chocalho viu em N dias" com 14+ dias de histórico,
  preço atual = mínimo da janela (até 30 dias, contando hoje mais cedo), preço já 3% mais alto na janela e esse nível de preço
  visto em no máximo 3 dias (quem alterna entre dois preços não ganha selo). O site (`vitrine.selo`) usa a mesma função e
  mostra "Menor preço em N dias". Decisão do Leonardo apesar da cláusula 5.4 do ML.
- Repetição: `REPOST_DIAS` (padrão 7 no workflow): mesmo produto e títulos parecidos (ML + Shopee) não voltam antes disso; volta antes só se o preço cair 5%.
  Tipo do dia (`ofertas.tipos_do_dia`) soma ML e Shopee; sem tipo conhecido, usa a primeira palavra que diz o que é o produto.
  `ofertas.priorizar_tipos_novos`: tipo que saiu nas últimas 48 h vai para o fim da fila (só entra se faltar alternativa).
- `espelho.py`: lê canais de ofertas do Telegram (`FONTES_OFERTAS_TG`, padrão no ciclo.yml) pela sessão Telethon;
  links do ML/Shopee viram candidatos por 48 h (`estado.espelho`). ML: catálogo direto; anúncio avulso → busca o catálogo pelo título.
  Passam pelos mesmos filtros (regra "infantil", NBCAL, repetição); desconto mínimo 10% e +20% na pontuação.
  Origem visível para o admin: `espelho.fonte` → linha "🔁 Copiada do canal @x" na cópia do ML, aviso no post da Shopee
  e lista no resumo diário (`posts_dia[].fonte`). Shopee: `shopee_ofertas.do_espelho` confere por itemId.
- `filtros.py`: bloqueios (NBCAL, remédio, +14 anos, réplica) e `fora_da_faixa` (casa/adulto, exige sinal infantil).
- `mensagens.py`: `preco_por_unidade` (fralda descartável: por fralda; lenço umedecido: a cada 100; só com quantidade clara no título). Textos do Telegram/WhatsApp, frases de abertura por produto, linha de cupom, Shopee ("A partir de", nota e vendas).
- `lote.py`: lote do Linkbuilder (não existe API oficial do ML para gerar link; é manual). Cada link oficial abre UM anúncio
  (o vencedor quando o lote foi montado): `estado.links_item` guarda qual (lotes antigos vieram de `data/links_item_inicial.json`).
  `lote.conferir_anuncio` (na rodada e antes de postar): anúncio fora da lista de ativos do catálogo (pausado/sem estoque) →
  link descartado e o produto volta ao lote; ativo → o post usa o preço DESSE anúncio. Catálogo com mais de 20 anúncios:
  `ml.procurar_anuncio` olha as páginas seguintes antes de descartar. O histórico segue com o menor preço do catálogo. Prioriza candidatos do espelho (valem 48 h)
  e rebaixa o que é parecido com algo postado na semana.
- `cupons_ml.py` + `cupom_oferta.py`: lê cupons (canal oficial do ML + @cupombr via Telethon) e aplica o melhor cupom compatível na oferta.
- `shopee.py`: cliente da Open API de afiliados (GraphQL, assinatura SHA256). Repete em erro 10000/10030.
- `shopee_ofertas.py`: ofertas da Shopee por cima das do ML (limite próprio: `SHOPEE_MAX_DIA` 50, `SHOPEE_MAX_HORA` 4).
  Busca: 3 palavras-chave + 2 categorias infantis por rodada (`CATEGORIAS`, mais vendidos, páginas 1 a 3 em rodízio).
  A API não tem oferta relâmpago; `listType` 2 (top) e 0 trazem produtos gerais, não usamos.
  Regras: nota ≥ 4,7, vendas ≥ 500 (200 se veio do espelho), comissão ≥ 5%, só preço final; "de/por" só com queda vista pelo próprio bot.
  Links via `generateShortLink` com subId `telegram` / `whatsapp`.
- `whatsapp.py` + `wa/servico.mjs`: fila em `fila_wa/`; o serviço (Baileys) posta com aquecimento automático
  (4 → 10 → 14 → 20 posts/dia nos dias 0, 4, 8 e 14 desde a conexão), só das 7h às 23h, alterna ML/Shopee,
  posta primeiro o que tem mais `pontos` (`whatsapp.forca`: força do desconto; avisos = 9; `wa/comum.mjs: ordenarFila`), pausa 48 h se o WhatsApp sinalizar restrição, apaga links de não-admins.
- `resumos.py`: posts de resumo (fora do limite e da regra de repetição), chamados por `resumos.rodar` no fim da rodada:
  tabela de fraldas (`FRALDAS_ATIVO`, 10h): menor preço por fralda em cada tamanho, ML (`estado.fraldas_ml`, guardado a cada
  rodada, só com link oficial) + Shopee (busca na hora, preço único); mostra "ontem era R$ X" quando baixou 2%+.
  As 5 melhores do dia (`TOP5_ATIVO`, 21h): ofertas de `estado.posts_dia` (gravado por `resumos.registrar` a cada post),
  até 3 por loja e 1 por tipo, com o preço conferido de novo (subiu ou acabou → sai).
- `grafico.py`: gráfico de preço em Pillow (1080x1080; `formato="4x5"` para carrossel) pela `estado.serie_diaria`.
  `grafico.enviar_oferta` posta a oferta; com selo e `GRAFICO_ATIVO=1`, manda álbum (foto + gráfico) no Telegram.
  Os três aprovados e ligados em 15/11. WhatsApp não recebe o gráfico (só o texto com a prévia do link).
- `numeros.py`: página escondida `docs/numeros-bcfc6fce.html` (membros, ofertas, cupons, WhatsApp).
- `comandos.py`: comandos do admin no Telegram e resumo diário (inclui WhatsApp). `bloquear/desbloquear/bloqueados` (palavras em
  `estado.bloqueados`, aplicadas por `filtros.definir_bloqueios` no início de cada rodada); `fila`, `tirar N`, `limpar fila` (fila do WhatsApp);
  `avisar_se_parado`: 1 aviso por dia se passar 3 h sem post no horário ativo.
  `alertar_oferta_forte` (chamado a cada post, ML e Shopee): avisa o admin quando o preço está 20% abaixo do típico (7+ dias de
  histórico) ou 10% abaixo com selo de menor preço; até `ALERTA_MAX_DIA` (5) por dia.
- `tiktok.py`: renderizador dos carrosséis 1080x1350 (capa, produto, CTA).
- `instagram.py`: cliente da API do Instagram (login unificado; segredos `INSTAGRAM_TOKEN`/`INSTAGRAM_USER_ID`, token sem validade).
  `metricas()` tenta tudo junto e, se falhar, uma a uma; o que não vier fica em `ausentes`.
- `insights_ig.py`: chamado pelo ciclo a cada rodada. 1x/dia grava `data/instagram/AAAA-MM-DD.json` (conta só no dia anterior,
  janela de Brasília + retrato acumulado dos posts dos últimos 30 dias); a cada rodada atualiza `data/instagram/stories.json`.
  Base do relatório semanal (feito pelo Claude, não pelo bot). `follows_and_unfollows` só vem com 100+ seguidores.
- `instagram_pub.py`: publicação com aprovação. `conteudo` chama `oferecer()` em carrossel e post de produto (pacote, "carrossel <tema>",
  "insta <link>"): JPEGs em `docs/ig-tmp/<id>/` + pergunta com botões (callback `ig:ok:<id>` / `ig:nao:<id>`, tratados em
  `comandos.processar`). `main` (modo normal) chama `publicar_pendentes()`: só aprovados, no horário do roteiro;
  peça com mais de 2 h confere preço na vitrine (subiu ou saiu → barra e avisa). Pendentes expiram na virada do dia;
  imagens apagadas 2 dias depois. Reel e stories seguem manuais (API sem música da biblioteca e sem adesivo de link).

## Ferramentas (tools/, rodar pelo workflow inspecao)
- `testar_shopee`: prévia de busca da Shopee só para o admin.
- `exemplos_shopee`: 3 posts de exemplo da Shopee só para o admin.
- `produto_shopee <itemId>`: dados e foto de um produto da Shopee (foto vai para `saida/`).
- `testar_instagram` / `coletar_instagram`: confere o token / roda a coleta uma vez em `saida/instagram`.
- `publicar_carrossel <pasta>`: publica `docs/ig-tmp/<pasta>/` no Instagram (só com aprovação do Leonardo).
- `previa_resumos "fraldas top5 grafico"`: manda só para o admin a prévia da tabela de fraldas, das 5 melhores do dia e do gráfico.
- `conferir_precos`: posts do dia x preço de agora nas lojas (saida/conferir_precos.json). `sondar_precos_ml`: o que a API dá de preço
  (não dá o preço no Pix: /items é 403). `ver_pagina_ml <links>`: o que a página de destino mostra (diagnóstico pontual).
- `sondar_shopee`: mostra categorias (productCatIds) e tipos de lista que a API da Shopee devolve (só leitura).
- `achar_canais_tg "termo; termo"`: procura canais públicos de ofertas de bebê no Telegram e mede links/posts infantis (saida/canais_tg.md).
- `baixar nome=url ...`: baixa arquivos para `saida/` (o container não alcança mlstatic/Shopee/Canva).

## Regras que o código precisa respeitar
- NBCAL: nunca mamadeira, bico, chupeta, fórmula/leite infantil.
- Links de afiliado oficiais e sem alteração; Shopee só pela API oficial (nada de raspar o site); cupons só oficiais.
- Segredos só em GitHub Secrets; nunca imprimir tokens em log.
