#!/usr/bin/env bash
# Roda uma ferramenta de tools/ no workflow inspecao, espera terminar e mostra o resultado.
# Uso: .claude/skills/testar-no-github/rodar.sh <script> ["<args>"]
#   ex.: .claude/skills/testar-no-github/rodar.sh sondar_shopee
#        .claude/skills/testar-no-github/rodar.sh previa_busca "fralda g; lego"
# O que a ferramenta gravar em saida/ fica em /tmp/saida (clone do branch tmp-saida).
set -euo pipefail
R=chocalhodeofertas/chocalhodeofertas.github.io
SCRIPT="${1:?informe o script (nome do arquivo em tools/, sem .py)}"
ARGS="${2:-}"
if printf '%s' "$ARGS" | grep -Eiq '(meli\.la|s\.shopee\.com\.br|shope\.ee)/'; then
  echo "Bloqueado: os argumentos têm link de afiliado do Leonardo (ele não aceita abrir os links dele)." >&2
  exit 2
fi
[ -f "tools/${SCRIPT}.py" ] || { echo "tools/${SCRIPT}.py não existe (rode da raiz do repositório)." >&2; exit 1; }

ANTES=$(gh run list -R "$R" --workflow inspecao.yml -L 1 --json databaseId -q '.[0].databaseId' 2>/dev/null || echo 0)
gh api -X POST "repos/$R/actions/workflows/inspecao.yml/dispatches" -f ref=main \
  -f "inputs[script]=$SCRIPT" -f "inputs[args]=$ARGS" >/dev/null
echo "Disparado: $SCRIPT ${ARGS:+($ARGS)}"

ID=""
for _ in $(seq 1 30); do  # espera a execução nova aparecer (até ~1 min)
  sleep 2
  ID=$(gh run list -R "$R" --workflow inspecao.yml -L 1 --json databaseId -q '.[0].databaseId')
  [ "$ID" != "$ANTES" ] && break
done
[ -n "$ID" ] && [ "$ID" != "$ANTES" ] || { echo "A execução não apareceu; confira no GitHub." >&2; exit 1; }
echo "Execução $ID: https://github.com/$R/actions/runs/$ID"
gh run watch "$ID" -R "$R" --interval 10 --exit-status >/dev/null 2>&1 || true
ESTADO=$(gh run view "$ID" -R "$R" --json conclusion -q .conclusion)
echo "Terminou: $ESTADO"

# Só a parte do script (sem o preparo do ambiente); limita o tamanho para não lotar a conversa
gh run view "$ID" -R "$R" --log 2>/dev/null \
  | sed 's/^[^\t]*\t[^\t]*\t[0-9TZ:.-]* //' \
  | sed -n "/python -m tools\.${SCRIPT}/,/git init\|Post job cleanup/p" \
  | grep -v '^\[36;1m\|^shell:\|^env:\|^  [A-Z_]*:' \
  | cut -c1-400 | head -n "${LINHAS:-150}"

rm -rf /tmp/saida
if git clone -q --depth 1 -b tmp-saida "https://github.com/$R" /tmp/saida 2>/dev/null; then
  echo "--- arquivos em saida/ (copiados para /tmp/saida):"
  ls -la /tmp/saida | grep -v '^\(total\|d\)' || true
fi
