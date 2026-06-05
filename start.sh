#!/bin/bash
# 2c2a 启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

case "${1:-web}" in
    web)
        echo "启动 Web 服务器..."
        exec python run.py web --host 0.0.0.0 --port 8000 "${@:2}"
        ;;
    worker)
        echo "启动 Huey Worker..."
        exec python run.py worker
        ;;
    beat)
        echo "启动 Huey Beat..."
        exec python run.py beat
        ;;
    migrate)
        echo "运行数据库迁移..."
        exec python run.py migrate
        ;;
    dev)
        echo "启动开发服务器（热重载）..."
        exec python run.py web --reload --port 8000
        ;;
    *)
        echo "用法: $0 {web|worker|beat|migrate|dev}"
        exit 1
        ;;
esac
