#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "未找到 $PYTHON_BIN，请先在项目根目录创建 .venv 并安装依赖。"
    exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/scripts/launch_app.py" "$@"
