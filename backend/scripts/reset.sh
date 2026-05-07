#!/bin/bash

echo "========================================"
echo "  Agentrust 系统初始化脚本"
echo "========================================"
echo ""

cd "$(dirname "$0")/.."

echo "[1/2] 删除旧数据库..."
if [ -f "../data/agentrust.db" ]; then
    rm -f ../data/agentrust.db
    echo "  已删除 data/agentrust.db"
else
    echo "  数据库文件不存在，跳过"
fi

echo ""
echo "[2/2] 初始化数据库和CA根密钥..."
python scripts/init_db.py

echo ""
echo "========================================"
echo "  初始化完成，可以运行 demo.py 了"
echo "========================================"