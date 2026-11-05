# 🪇 Chocalho de Ofertas

Bot que acompanha preços de produtos de bebê e criança no Mercado Livre e posta as
ofertas no canal do Telegram com o seu link de afiliado. Roda sozinho, de hora em
hora, pelo GitHub Actions (grátis).

**O que ele faz em cada rodada:**
1. Lê os produtos do arquivo `produtos.csv`.
2. Consulta o preço atual de cada um no Mercado Livre.
3. Considera oferta quando o desconto é de **15% ou mais**, quando o preço fica 15% abaixo do
   preço de referência que você anotou, ou quando é o **menor preço já visto**.
4. Posta **1 oferta por hora**, entre **8h e 22h**, no máximo **12 por dia**, sem repetir o mesmo
   produto por 3 dias (a não ser que o preço caia mais).
5. Te manda no privado a mesma oferta já formatada para **WhatsApp** e para o **X**, para copiar e colar.

**O que ele nunca posta:** mamadeira, bico, chupeta, protetor de mamilo, fórmulas e leites
infantis (NBCAL, Lei 11.265/2006), remédios e suplementos. O filtro é automático.

---

## Passo 1: Secrets do Telegram

No GitHub, abra o repositório → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Crie:

| Nome | O que colocar |
|---|---|
| `TELEGRAM_BOT_TOKEN` | o token que o @BotFather te deu |
| `TELEGRAM_CANAL` | o @ do canal, ex.: `@chocalhodeofertas` |

## Passo 2: Descobrir o seu chat ID

1. No Telegram, abra uma conversa com o **seu bot** e mande um "oi".
2. No GitHub, vá em **Actions** → **Chocalho de Ofertas** → **Run workflow** → modo
   **diagnostico** → **Run workflow**.
3. Abra a execução e clique em **Rodar o bot**. Vai aparecer uma linha "chat ID = 123456789".
4. Crie o secret `TELEGRAM_ADMIN_CHAT_ID` com esse número.

## Passo 3: Adicionar produtos

Abra o arquivo `produtos.csv` aqui no GitHub e clique no lápis (✏️) para editar. Cada linha
tem quatro informações, separadas por vírgula:

```
link_produto,link_afiliado,categoria,preco_referencia
https://www.mercadolivre.com.br/fralda-.../p/MLB12345678,https://meli.la/abc123,fralda,89.90
```

- **link_produto:** o endereço do produto, copiado da barra do navegador.
- **link_afiliado:** o link que o painel de afiliados gera para esse produto.
- **categoria:** fralda, higiene, roupa, brinquedo, jogo, quarto, passeio, alimentacao,
  gestante ou outros (muda o emoji do post).
- **preco_referencia** (opcional): o preço "normal" do produto.

Clique em **Commit changes** para salvar.

## Passo 4: Testar

Rode o workflow no modo **teste**. Tudo chega só no seu privado, com a marca [TESTE], e nada
vai para o canal. Se não houver nenhuma oferta, ele manda um exemplo para você ver o formato.

Se aparecer "Mercado Livre recusou o acesso", vá para o passo 5. Se não, pode pular.

## Passo 5: Token do Mercado Livre (se for necessário)

1. Em **developers.mercadolivre.com.br**, crie um aplicativo. Em **Redirect URI**, use
   `https://github.com/lgabanella/bot-ofertas`.
2. Crie os secrets `ML_CLIENT_ID` e `ML_CLIENT_SECRET` com os valores do app.
3. Crie um token do GitHub para o bot conseguir renovar o token do ML sozinho:
   GitHub → foto → **Settings** → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**. Em **Repository access**, escolha só o
   `bot-ofertas`. Em **Permissions**, coloque **Secrets: Read and write**. Salve como o secret `GH_PAT`.
4. Abra no navegador (troque SEU_CLIENT_ID):
   `https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=SEU_CLIENT_ID&redirect_uri=https://github.com/lgabanella/bot-ofertas`
5. Autorize. O navegador vai abrir o GitHub com `?code=...` no endereço. Copie o endereço inteiro.
6. Em **Actions** → **Configurar token do Mercado Livre** → **Run workflow**, cole o endereço
   e rode. **Faça isso logo**, porque o código vale só alguns minutos.
7. Rode o **diagnostico** de novo.

## Passo 6: Ligar

Depois do teste, o bot já roda sozinho de hora em hora. Para ajustar o comportamento, use
**Settings** → **Secrets and variables** → **Actions** → aba **Variables**:

| Variável | Padrão | O que muda |
|---|---|---|
| `MIN_DESCONTO` | 15 | desconto mínimo (%) para postar |
| `MAX_POSTS_POR_RODADA` | 1 | quantas ofertas por hora |
| `MAX_POSTS_POR_DIA` | 12 | limite diário |
| `HORA_INICIO` / `HORA_FIM` | 8 / 22 | horário de postagem |

Para pausar: **Actions** → **Chocalho de Ofertas** → **⋯** → **Disable workflow**.

---

Arquivos: `bot/` tem o código, `produtos.csv` a sua lista, `data/estado.json` o histórico de
preços (o bot atualiza sozinho) e `tests/` os testes (`python -m pytest`).
