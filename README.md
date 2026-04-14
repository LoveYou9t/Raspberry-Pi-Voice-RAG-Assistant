# 树莓派语音 RAG 助手（MVP）

基于 FastAPI + WebSocket + Faster-Whisper + LanceDB + Ollama + Piper 的单用户低延迟语音链路实现。

## 功能范围（当前）

- WebSocket 全双工音频传输（上行麦克风 / 下行 PCM）
- STT（Faster-Whisper，缺失时自动降级）
- RAG 检索（LanceDB 检索，缺失时回退文件检索）
- LLM 流式生成（Ollama）
- TTS 流式合成（默认真实 Piper，启动时自动下载模型并校验）
- Docker Compose 一键启动

## 快速开始

1. 编辑 `.env` 调整模型与阈值（默认 `LLM_MODEL=llama3.2:3b`、`STT_MODEL=tiny`、`PIPER_USE_MOCK_ON_MISSING=0`）。
2. 准备知识库文件到 `knowledge_base/`。
3. 启动：

```bash
docker compose up -d --build
```

首次启动会自动预热 llama3.2:3b、faster-whisper tiny，并下载/校验 Piper 模型，耗时会明显长于后续启动。
若 piper_init 失败，fastapi_backend 不会启动，请先查看 piper_init 日志定位原因。

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
docker compose logs piper_init
curl http://localhost:8000/healthz
```

`/healthz` 会返回 `tts_mode`、`piper_bin_found`、`piper_model_exists` 等字段。

## 目录结构

- `backend/` 后端服务与异步管线
- `frontend/` 浏览器端采集与播放
- `knowledge_base/` 挂载知识库目录
- `lancedb_data/` 向量库持久化目录
- `ollama_data/` Ollama 模型持久化目录
- `piper_cache/` Piper 模型持久化目录
