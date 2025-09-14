#!/bin/bash


# -e: 如果任何指令失敗，腳本會立即退出。
# -u: 如果使用未定義的變數，腳本會報錯並退出。
# -o pipefail: 如果 pipeline 中的任何一個指令失敗，整個 pipeline 都會被視為失敗。
set -euo pipefail

echo "Starting supervisor..."
exec /usr/bin/supervisord -c /app/supervisord.conf
