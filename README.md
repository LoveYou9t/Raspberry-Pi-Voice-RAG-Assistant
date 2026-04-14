# 树莓派语音 RAG 助手（MVP）

基于 FastAPI + WebSocket + Faster-Whisper + LanceDB + Ollama + Piper 的单用户低延迟语音链路实现。

## 功能范围（当前）

- WebSocket 全双工音频传输（上行麦克风 / 下行 PCM）
- STT（Faster-Whisper，缺失时自动降级）
- RAG 检索（LanceDB 检索，缺失时回退文件检索）
- LLM 流式生成（Ollama）
- TTS 流式合成（Piper 常驻进程，缺失时可降级为模拟音频）
- Docker Compose 一键启动

## 快速开始

1. 编辑 `.env` 调整模型与阈值（默认 `LLM_MODEL=llama3.2:3b`、`STT_MODEL=tiny`）。
2. 准备知识库文件到 `knowledge_base/`。
3. 启动：

```bash
docker compose up -d --build
```

首次启动会自动预热 llama3.2:3b 与 faster-whisper tiny，耗时会明显长于后续启动。
如果网络临时不可用，预热会重试并记录告警，服务仍可继续启动。

可选预热脚本：

```bash
sh bootstrap.sh
```

访问：

- 前端: <http://localhost:8080>
- 后端健康检查: <http://localhost:8000/healthz>

可选验证：

```bash
docker exec edge_ollama ollama list
curl http://localhost:8000/healthz
```

## 目录结构

- `backend/` 后端服务与异步管线
- `frontend/` 浏览器端采集与播放
- `knowledge_base/` 挂载知识库目录
- `lancedb_data/` 向量库持久化目录
- `ollama_data/` Ollama 模型持久化目录
