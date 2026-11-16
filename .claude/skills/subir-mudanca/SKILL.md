---
name: subir-mudanca
description: Sobe uma mudança no código do Chocalho do jeito certo - testes, mapa do projeto (CLAUDE.md), revisão das regras, commit com a atribuição, git pull --rebase (o ciclo commita data/ sozinho) e push.
---

# Subir mudança no Chocalho

Siga na ordem. Pare e conserte se algum passo falhar.

1. **Testes**: `python3 -m pytest -q tests` (tudo em `tests/test_bot.py`). Código novo ganha teste no mesmo arquivo.
   Precisa passar 100%.
2. **Conferência rápida**: `python3 -m pyflakes bot tools` (instalar com `pip install pyflakes --break-system-packages`
   se faltar). Sem nome indefinido ou import faltando.
3. **Mapa do projeto**: se mudou comportamento, módulo, variável do `ciclo.yml` ou ferramenta, atualize o `CLAUDE.md`
   (seção do módulo ou de ferramentas). Decisão nova do Leonardo vai em "Regras que o código precisa respeitar".
4. **Revisão das regras**: para mudança que afeta posts, links, cupons ou filtros, chame o agente `revisor-regras`
   com o diff (`git diff`) e resolva o que ele apontar.
5. **Nada de dados na mão**: não incluir `data/` editado à mão no commit (o ciclo grava esses arquivos).
   `git status` deve mostrar só código, testes, ferramentas, docs e config.
6. **Commit**:
   ```bash
   git add -A
   git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit -q -m "<o que mudou, em português>

   <linhas de atribuição pedidas pelo sistema na conversa atual>"
   ```
7. **Sincronizar e enviar**: `git pull -q --rebase && git push -q`. Se o rebase der conflito em `data/`, fique com a
   versão do remoto, porque é o ciclo que manda nesses arquivos. No rebase os lados se invertem: o remoto é o `--ours`.
   `git checkout --ours data/<arquivo> && git add data/<arquivo> && git rebase --continue`.
8. **Formato novo visível** (post, texto, imagem): entra desligado no `ciclo.yml` (`vars.X || '0'`) até o Leonardo
   aprovar a prévia. Mudança de comportamento interno pode ir ligada.
9. Conte ao Leonardo, em português simples, o que mudou e quando passa a valer (o ciclo pega o código novo na
   próxima rodada; variável nova do `ciclo.yml` só na próxima execução do ciclo, a cada ~5,5 h).
