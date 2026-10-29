#!/usr/bin/env bash
# Windows Git Bash 侧包装：bash qoder/scripts/sb.sh <studybench 参数>
# 例：bash qoder/scripts/sb.sh ingest --src corpus_demo
#     bash qoder/scripts/sb.sh search "完全二叉树 叶子结点" --top 3
#     bash qoder/scripts/sb.sh selftest
set -euo pipefail
export MSYS2_ARG_CONV_EXCL="*"
export MSYS_NO_PATHCONV=1
exec wsl -e /bin/bash /mnt/e/CodeX/PowerContext-2026/qoder/scripts/run_in_wsl.sh "$@"
