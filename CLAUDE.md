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

## Automações do Claude Code (`.claude/`, instaladas em 16/11 a pedido do Leonardo)
- Travas (`.claude/hooks/proteger.py`, PreToolUse): bloqueiam abrir link de afiliado do Leonardo (meli.la,
  s.shopee.com.br, shope.ee) por WebFetch, curl/requests ou disparando ferramenta no GitHub, e bloqueiam editar
  `data/*.json` na mão (o ciclo grava; mudança de dados vai por migração em `bot/estado.py`).
- Conferência do Python (`.claude/hooks/checar_python.py`, PostToolUse): pyflakes no `.py` editado
  (`pip install pyflakes --break-system-packages`). O repositório está limpo: manter assim.
- Skills: `testar-no-github` (`.claude/skills/testar-no-github/rodar.sh <script> "<args>"`: dispara o inspecao,
  espera, mostra o log e clona `tmp-saida` em /tmp/saida) e `subir-mudanca` (testes, mapa, revisão, commit, rebase, push).
- Agente `revisor-regras` (`.claude/agents/`): revisa o diff contra NBCAL, links, aprovação, segredos e decisões do Leonardo.
- MCP `context7` (`.mcp.json`): documentação atual das bibliotecas (Baileys, Telethon, Pillow, Telegram Bot API).
- Skill `find-skills` (de `vercel-labs/skills`, instalada com `npx skills add`; versão travada em `skills-lock.json`):
  procura skills prontas. No container da nuvem o site skills.sh é bloqueado e `npx skills find` devolve
  "No skills found" mesmo existindo: aí a busca é pelos repositórios de origem no GitHub (obra/superpowers,
  coreyhaines31/marketingskills, trailofbits/skills, anthropics/skills). Skill de terceiro: ler antes de instalar.
- Skills de terceiros instaladas em 16/11 (revisadas antes; versões em `skills-lock.json`, atualizar com `npx skills update`):
  `systematic-debugging` e `verification-before-completion` (obra/superpowers): achar a causa antes de consertar e
  só dizer "pronto" com a prova rodada na hora. `ads`, `ad-creative` e `social` (coreyhaines31/marketingskills):
  anúncios na Meta e conteúdo orgânico; são em inglês e pensadas para software, adaptar ao Chocalho.
  As regras do Leonardo valem por cima delas: nada de gerar imagem/vídeo com serviço pago sem autorização, textos em
  português, sem porcentagem em artes. Elas procuram um `.claude/product-marketing.md`: NÃO criar aqui (o repositório
  é público e a estratégia é privada); o contexto vem do briefing do projeto.

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
  Rodízio de categorias (17/11, `ofertas.equilibrar_categorias`, ML e Shopee, por cima do de tipos): conta o dia em
  `estado.posts_dia` (`categoria_efetiva`: categoria da descoberta ou, se "outros", `categoria_do_titulo`); brinquedo acima de
  30% do dia (a partir de 6 posts) vai para o fim; alimentação, passeio, roupa e quarto com menos de 2 posts vão na frente.
  Só muda a ordem entre ofertas aprovadas.
- `espelho.py`: lê canais de ofertas do Telegram (`FONTES_OFERTAS_TG`, padrão no ciclo.yml) pela sessão Telethon;
  links do ML/Shopee viram candidatos por 48 h (`estado.espelho`). ML: catálogo direto; anúncio avulso → busca o catálogo pelo título.
  Passam pelos mesmos filtros (regra "infantil", NBCAL, repetição); desconto mínimo 10% e +20% na pontuação.
  Origem visível para o admin: `espelho.fonte` → linha "🔁 Copiada do canal @x" na cópia do ML, aviso no post da Shopee
  e lista no resumo diário (`posts_dia[].fonte`). Shopee: `shopee_ofertas.do_espelho` confere por itemId.
- `filtros.py`: bloqueios (NBCAL, remédio, +14 anos, réplica, fralda geriátrica/incontinência) e `fora_da_faixa` (casa/adulto, exige sinal infantil;
  17/11: escritório/igreja sem sinal infantil e protetor/adesivo de seios de silicone, "fita up").
- Frete no post (ML): `mercadolivre.entrega` lê `shipping.free_shipping` e `logistic_type == "fulfillment"` de cada anúncio
  (`InfoProduto.envio`); `lote.conferir_anuncio` guarda o do anúncio que o link abre (`info.frete`) e `main._com_frete` põe na oferta;
  `mensagens._linhas_preco` mostra "🚚 Frete grátis · ⚡ Full (entrega rápida)" só quando é verdade. Sem anúncio conhecido, não mostra.
- `mensagens.py`: `preco_por_unidade` (fralda descartável: por fralda; lenço umedecido: a cada 100; só com quantidade clara no título). Textos do Telegram/WhatsApp, frases de abertura por produto, linha de cupom, Shopee ("A partir de", nota e vendas).
- `lote.py`: lote do Linkbuilder (não existe API oficial do ML para gerar link; é manual). Cada link oficial abre UM anúncio
  (o vencedor quando o lote foi montado): `estado.links_item` guarda qual (lotes antigos vieram de `data/links_item_inicial.json`).
  `lote.conferir_anuncio` (na rodada e antes de postar): anúncio fora da lista de ativos do catálogo (pausado/sem estoque) →
  link descartado e o produto volta ao lote; ativo → o post usa o preço DESSE anúncio. Catálogo com mais de 20 anúncios:
  `ml.procurar_anuncio` olha as páginas seguintes antes de descartar. O histórico segue com o menor preço do catálogo. Prioriza candidatos do espelho (valem 48 h)
  e rebaixa o que é parecido com algo postado na semana.
  Reputação (17/11, `lote.anuncio_bom`): vendedor 🔴/🟠 (`REPUTACAO_RUIM`, via `ml.reputacao` = users/{id} level_id, cache de 3 dias
  em `estado.reputacao`) não entra no lote: troca pelo anúncio de outro vendedor do catálogo até 5% mais caro
  (`InfoProduto.vendedores`); sem alternativa, fica de fora. Amarelo, verde e "sem cor" entram. Falha na consulta não barra.
  Sonda: `tools/sondar_reputacao` (cor do vendedor de cada item do lote pendente, só API).
- `cupons_ml.py` + `cupom_oferta.py`: lê cupons (canal oficial do ML + @cupombr via Telethon) e aplica o melhor cupom compatível na oferta.
  O "cupom do anúncio" (`cupom_oferta.cupom_da_pagina`) lia a página abrindo o meli.la do Leonardo a cada post: DESLIGADO em 16/11
  (regra dele: o bot não abre links de afiliado). Só volta com `CUPOM_DA_PAGINA=1`, se ele pedir. Ainda abrem o link, só quando
  ele manda um meli.la avulso ao bot: `comandos.resolver_meli` (postar link / `insta <link>`); pendente de decisão dele.
- `shopee.py`: cliente da Open API de afiliados (GraphQL, assinatura SHA256). Repete em erro 10000/10030.
- `shopee_ofertas.py`: ofertas da Shopee por cima das do ML (limite próprio: `SHOPEE_MAX_DIA` 50, `SHOPEE_MAX_HORA` 4).
  Busca: 3 palavras-chave + 2 categorias infantis por rodada (`CATEGORIAS`, mais vendidos, páginas 1 a 3 em rodízio).
  A API não tem oferta relâmpago; `listType` 2 (top) e 0 trazem produtos gerais, não usamos.
  Regras: nota ≥ 4,7, vendas ≥ 500 (200 se veio do espelho), comissão ≥ 3% (era 5%; fralda quase sempre paga 3%), só preço final; "de/por" só com queda vista pelo próprio bot.
  Links via `generateShortLink` com subId `telegram` / `whatsapp`.
- `whatsapp.py` + `wa/servico.mjs`: fila em `fila_wa/`; o serviço (Baileys) posta com aquecimento automático
  (4 → 10 → 14 → 20 posts/dia nos dias 0, 4, 8 e 14 desde a conexão), só das 7h às 23h, alterna ML/Shopee,
  intervalo sorteado de 4 a 13 min (`WA_INTERVALO_MIN/MAX`) e o limite do dia espalhado pelas horas (`comum.mjs: cotaAteAgora`;
  às 12h só pode ter saído 4/16 do limite); avisa quando cai por mais de 10 min, quando volta e quando a pausa de segurança acaba;
  Radar (`comum.mjs: anotarRadar`): `wa_estado.json: radar[dia][hora] = [entradas, saídas, mensagens]`, 45 dias, só contagens;
  `whatsapp.conferir_fila` (a cada rodada, ~20 min): reconfere pela API o preço do que espera no grupo; subiu > 2% ou acabou → sai da fila
  (`estado.wa_conferidos`, aparece na página da fila); baixou → fica.
  posta primeiro o que tem mais `pontos` (`whatsapp.forca`: força do desconto; avisos = 9; `wa/comum.mjs: ordenarFila`), alterna a loja e
  evita repetir a categoria da anterior (`categoria` no item, `wa_estado.ultima_categoria`; espelhado em `fila_pagina.ordem_de_saida`),
  pausa 48 h se o WhatsApp sinalizar restrição, apaga links de não-admins.
  Prévia do link (é a prévia do próprio link, `linkPreview`, não imagem anexa): com `PREVIA_MARCA=1` (aprovado e ligado em 17/11)
  a imagem da prévia é o cartão com a marca (`arte.cartao_previa`: foto do produto num cartão branco, fundo lavanda, logo embaixo,
  sem preço), gerado em `whatsapp.cartao_da_oferta` e salvo na fila; foto que não baixa → foto do anúncio.
  Título da prévia = nome do produto, sem emoji (decisão dele). Imagem anexa só se a prévia falhar.
  Prévia só para o admin: `tools/previa_cartao_wa`.
  Menção oculta (`mencionar` no item → `mentions` com todos os participantes, sem "@" no texto): SÓ pelo comando `marcar <texto|meli.la>`
  do Leonardo (`comandos.marcar`, até 2/dia); nunca automático (decisão de 17/11).
- `resumos.py`: posts de resumo (fora do limite e da regra de repetição), chamados por `resumos.rodar` no fim da rodada:
  tabela de fraldas (`FRALDAS_ATIVO`, 10h): menor preço por fralda em cada tamanho, ML (`estado.fraldas_ml`, guardado a cada
  rodada, só com link oficial) + Shopee (busca na hora, preço único); mostra "ontem era R$ X" quando baixou 2%+.
  As 5 melhores do dia (`TOP5_ATIVO`, 21h): ofertas de `estado.posts_dia` (gravado por `resumos.registrar` a cada post),
  até 3 por loja e 1 por tipo, com o preço conferido de novo (subiu ou acabou → sai).
- `grafico.py`: gráfico de preço em Pillow (1080x1080; `formato="4x5"` para carrossel) pela `estado.serie_diaria`.
  `grafico.enviar_oferta` posta a oferta; com selo e `GRAFICO_ATIVO=1`, manda álbum (foto + gráfico) no Telegram.
  Os três aprovados e ligados em 15/11. WhatsApp não recebe o gráfico (só o texto com a prévia do link).
  Carrossel do Instagram: `conteudo.cartao_grafico` põe um cartão 4x5 do gráfico do produto que mais caiu (antes do slide final),
  só quando o gráfico existe (14+ dias de histórico). Tema sob pedido `carrossel blackfriday` (`conteudo.TEMA_BLACK_FRIDAY`):
  só produtos com queda real ≥ 10% sobre o preço típico (`conteudo.queda_real`), do que mais caiu para o que menos caiu.
- `busca_publica.py`: busca sob pedido. `procurar(termo)` = ML (só produtos com link oficial, preço conferido na hora e
  `lote.conferir_anuncio`) + Shopee ao vivo (API, regras de `aprovado`, link com subId `busca`); mesmos filtros dos posts (NBCAL).
  Admin testa com `achar <produto>`; quem escreve no privado do bot só recebe resposta com `BUSCA_PUBLICA=1` (`atender`).
  Limite de 5 buscas/hora por pessoa com código embaralhado (repo público: não guarda chat id); `buscas_termos` conta os termos
  mais procurados (aparece no resumo diário).
- Cupons da Shopee: a API não lista cupons. `comandos.postar_cupom_shopee` (`cupom shopee <texto>`) posta no canal e na fila do
  grupo com `SHOPEE_CUPONS_LINK` (link oficial do Leonardo para a página de cupons; NUNCA abrir/expandir links de afiliado dele).
  `resumos.talvez_cupons_shopee`: post diário às 9h com esse link (`CUPONS_SHOPEE_ATIVO`, ligado: aprovado em 16/11).
- `paginas.py`: moldura comum das duas páginas escondidas (marca do site: Schibsted Grotesk de `docs/fonts`, roxo/uva/rosa,
  modo escuro; abas Números/Fila; topo = frase grande com os números do dia; `fatos` = números de apoio).
- `numeros.py`: página escondida `docs/numeros-bcfc6fce.html` (membros, ofertas do dia = ML + Shopee, cupons, WhatsApp) e o
  radar do grupo (`radar_horas`: entradas/saídas/mensagens por hora somadas em 7 dias, frase + barras para cima e para baixo).
- `fila_pagina.py`: página escondida `docs/fila-4e7a91c3.html`, reescrita a cada rodada (`publicar` no fim da rodada normal):
  o que saiu hoje no canal (`estado.posts_dia`, com hora, origem do espelho, selo, cupom) e o que aconteceu com cada oferta no
  grupo do WhatsApp (`wa_estado.json: historico`, gravado por `wa/comum.mjs: anotarHistorico`: enviado / venceu / limite / pausa /
  erro); o que espera no grupo, na ordem e com previsão de saída (`prever`, mesma regra de `ordenarFila`); e os produtos que
  esperam link oficial (`estado.fila_link`, de `lote.resumo_fila`). Sem links na página. O comando `fila` aponta para ela.
- `comandos.py`: comandos do admin no Telegram e resumo diário (inclui WhatsApp). `bloquear/desbloquear/bloqueados` (palavras em
  `estado.bloqueados`, aplicadas por `filtros.definir_bloqueios` no início de cada rodada); `fila`, `tirar N`, `limpar fila` (fila do WhatsApp);
  `avisar_se_parado`: 1 aviso por dia se passar 3 h sem post no horário ativo. `recarga [dd/mm|plano]` grava a última recarga do
  chip do WhatsApp (`estado.chip_recarga`); `lembrar_recarga` avisa com 75 e 85 dias (pré-pago perde o número com 90).
  `alertar_oferta_forte` (chamado a cada post, ML e Shopee): avisa o admin quando o preço está 20% abaixo do típico (7+ dias de
  histórico) ou 10% abaixo com selo de menor preço; até `ALERTA_MAX_DIA` (5) por dia.
  Quando o post sai sem selo, o aviso explica (`nota_sem_selo`: histórico menor que 14 dias ou regra do selo não batida).
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
- `conferir_precos`: posts do dia x preço de agora nas lojas, só pela API (saida/conferir_precos.json). `sondar_precos_ml`: o que a
  API dá de preço (não dá o preço no Pix: /items é 403). `sondar_extras "MLB.. MLB..; termo|termo"`: frete grátis/Full por
  anúncio (a API dá `shipping.free_shipping` e `logistic_type == "fulfillment"`; Pix e cupom não), se a página pública do produto
  abre do GitHub (não: cai em account-verification) e por que a Shopee recusou cada produto de uma busca.
  Nenhuma ferramenta abre link de afiliado (a antiga `ver_pagina_ml` foi apagada em 16/11).
- `previa_busca "fralda g; mochila infantil"`: manda só para o admin as respostas da busca sob pedido e a prévia dos cupons da Shopee.
- `sondar_shopee`: mostra categorias (productCatIds) e tipos de lista que a API da Shopee devolve (só leitura).
- `achar_canais_tg "termo; termo"`: procura canais públicos de ofertas de bebê no Telegram e mede links/posts infantis (saida/canais_tg.md).
- `previa_cartao_wa`: manda só para o admin o cartão da prévia do WhatsApp das 3 últimas ofertas do dia.
- `baixar nome=url ...`: baixa arquivos para `saida/` (o container não alcança mlstatic/Shopee/Canva).

## Regras que o código precisa respeitar
- NBCAL: nunca mamadeira, bico, chupeta, fórmula/leite infantil.
- Links de afiliado oficiais e sem alteração; Shopee só pela API oficial (nada de raspar o site); cupons só oficiais.
- Segredos só em GitHub Secrets; nunca imprimir tokens em log.
- Decisões do Leonardo (16/11): o bot nunca abre/clica links de afiliado dele (nem páginas ligadas à conta dele); sem filtro por
  reputação do vendedor (mudou em 17/11: vermelho/laranja fora do lote, com troca; ver `lote.anuncio_bom`); sem prioridade por comissão; sem limite de variação de preço na Shopee.
