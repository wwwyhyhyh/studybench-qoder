#!/usr/bin/env bash
# 在 WSL(ext4) 内执行：把仓库的 qoder/ 同步到 ext4 副本，再跑 studybench。
# 由 qoder/scripts/sb.sh（Windows Git Bash 侧）调用，也可直接在 WSL 里执行。
set -euo pipefail

REPO_WSL="/mnt/e/CodeX/PowerContext-2026"
SRC="$REPO_WSL/qoder"
DEST="$HOME/sb-run/qoder"
VERTIN_HOME="$HOME"

mkdir -p "$HOME/sb-run/.runtime"
# records/ 与 verification/ 是「产物」，直接留在 Windows 侧仓库里，被同步链路排除并软链回去，
# 避免 rsync --delete 把刚生成的证据清掉。
rsync -a --delete \
  --exclude '.runtime' --exclude '__pycache__' --exclude '.pytest_cache' \
  --exclude 'node_modules' --exclude 'records' --exclude 'verification' \
  "$SRC/" "$DEST/"
rm -rf "$DEST/records" "$DEST/verification"
ln -sfn "$SRC/records" "$DEST/records"
ln -sfn "$SRC/verification" "$DEST/verification"

cd "$DEST"
export PYTHONPATH="$DEST/studybench:$REPO_WSL"
export SB_DB="${SB_DB:-$VERTIN_HOME/sb-run/.runtime/sb.db}"
export SB_PC_DB="${SB_PC_DB:-$VERTIN_HOME/sb-run/.runtime/powercontext.db}"

cmd="${1:-help}"
case "$cmd" in
  selftest)
    shift
    exec "$VERTIN_HOME/sb-venv/bin/python" -m pytest "$DEST/studybench/tests" -q "$@"
    ;;
  py)
    shift
    exec "$VERTIN_HOME/sb-venv/bin/python" "$@"
    ;;
  *)
    exec "$VERTIN_HOME/sb-venv/bin/python" -m studybench "$@"
    ;;
esac
