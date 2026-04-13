#!/usr/bin/env sh
set -eu

LLM_MODEL="${LLM_MODEL:-llama3.2:3b}"
STT_MODEL="${STT_MODEL:-tiny}"

echo "[1/3] 设置默认模型参数..."
export LLM_MODEL
export STT_MODEL

echo "[2/3] 一键构建并启动全部服务（含模型预热）..."
docker compose up -d --build

echo "[3/3] 当前容器状态："
docker compose ps

echo "完成。前端: http://localhost:8080 后端: http://localhost:8000"
