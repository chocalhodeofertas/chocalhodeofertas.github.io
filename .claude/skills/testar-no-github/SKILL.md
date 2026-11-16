---
name: testar-no-github
description: Roda uma ferramenta de tools/ do Chocalho no workflow inspecao do GitHub, espera terminar e traz o log e os arquivos de saida/. Use para sondar APIs, prévias para o admin e diagnósticos que precisam dos segredos do bot.
---

# Testar no GitHub (workflow inspecao)

O container não tem os segredos do bot nem alcança o Mercado Livre/Shopee/Telegram direto, então
ferramentas que precisam disso rodam no GitHub Actions pelo workflow `inspecao.yml`.

## Como usar

Da raiz do repositório:

```bash
.claude/skills/testar-no-github/rodar.sh <script> "<args>"
```

- `<script>` é o nome do arquivo em `tools/` sem `.py` (ex.: `sondar_shopee`, `previa_busca`, `conferir_precos`).
- O script dispara, espera a execução nova, mostra só a parte do log da ferramenta e clona o branch `tmp-saida`
  em `/tmp/saida` (o que a ferramenta gravou em `saida/`).
- Log grande: `LINHAS=400 .claude/skills/testar-no-github/rodar.sh ...`.

## Regras

- **Nunca** passar link de afiliado do Leonardo (meli.la, s.shopee.com.br, shope.ee) nos argumentos, nem criar
  ferramenta que abra/siga esses links: ele não aceita (conta como clique). O script e a trava do repositório bloqueiam.
- Ferramenta nova: criar em `tools/`, rodar `python3 -m pytest -q tests`, commitar e dar push ANTES de disparar
  (o workflow roda o código que está no `main`). Ver a skill `subir-mudanca`.
- Prévia de formato novo vai só para o admin (`TELEGRAM_ADMIN_CHAT_ID`), nunca para o canal ou o grupo:
  nada é publicado sem a aprovação do Leonardo.
- Ferramenta só de diagnóstico que não serve mais: apagar de `tools/` e do CLAUDE.md.
