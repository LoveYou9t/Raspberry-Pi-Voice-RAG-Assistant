#!/usr/bin/env sh
set -eu

LLM_MODEL="${LLM_MODEL:-llama3.2:1b}"

echo "[1/4] 启动 Ollama 服务..."
docker compose up -d ollama_server

echo "[2/4] 等待 Ollama 就绪..."
until docker exec edge_ollama ollama list >/dev/null 2>&1; do
  sleep 2
done

echo "[3/4] 预拉取模型: ${LLM_MODEL}"
docker exec edge_ollama ollama pull "${LLM_MODEL}"

echo "[4/4] 启动后端与前端..."
docker compose up -d --build fastapi_backend frontend_client

echo "完成。前端: http://localhost:8080  后端: http://localhost:8000"
