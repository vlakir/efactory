#!/usr/bin/env bash
# Гейты перед push: лёгкие локально, полный набор — на srv (создан из шаблона репозитория CI srv).
#
# Использование:
#   scripts/gates.sh --light   # ruff check, ruff format --check, mypy — перед каждым push
#   scripts/gates.sh           # полный набор: то же + pytest с порогом покрытия ≥80%
#   scripts/gates.sh --full    # то же, что без флага
#
# Перед push локально — только `--light`; полный набор гоняет srv (`scripts/srv_gates.py`,
# workflow `gates` вызывает этот скрипт без флага), и слияние — только после зелёного
# прогона там. Полный локальный режим — для работы без VPN и отладки. Аргументы полного
# режима уходят в pytest (`scripts/gates.sh -x -k feed`).
#
# Выход — по первой упавшей проверке (`set -e`), с её кодом. Никакого пайпа после
# (`| tail`): код вернёт `tail`, а не гейт.
set -euo pipefail

cd "$(dirname "$0")/.."

mode=full
case "${1:-}" in
  --light) mode=light; shift ;;
  --full) shift ;;
esac
if [[ $mode == light && $# -gt 0 ]]; then
  echo "✖ --light аргументов не принимает (они уходят в pytest полного режима)." >&2
  exit 2
fi

uv run ruff check .
uv run ruff format --check .
uv run mypy src tests

if [[ $mode == light ]]; then
  echo ">>> [gates] Лёгкие проверки зелёные. Полный прогон — на srv: uv run python scripts/srv_gates.py"
  exit 0
fi

# Мьютекс тяжёлых прогонов шаблона dreamteam (если он есть) — несколько рабочих копий
# на одной машине не запускают pytest одновременно.
pytest_cmd=(uv run pytest)
if [[ -x scripts/pytest-guard.sh ]]; then
  pytest_cmd=(scripts/pytest-guard.sh)
fi
"${pytest_cmd[@]}" --cov=src --cov-report=term-missing --cov-fail-under=80 "$@"
echo ">>> [gates] Все четыре проверки зелёные."
