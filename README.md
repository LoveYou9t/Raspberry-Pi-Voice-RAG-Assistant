# 树莓派语音 RAG 助手（MVP）

基于 FastAPI + WebSocket + Faster-Whisper + LanceDB + Ollama + Piper 的单用户低延迟语音链路实现。

## 功能范围（当前）

- WebSocket 全双工音频传输（上行麦克风 / 下行 PCM）
- UART 有线半双工语音链路（实验版，支持上行语音与下行 TTS 回传）
- STT（Faster-Whisper，缺失时自动降级）
- RAG 检索（LanceDB 检索，缺失时回退文件检索）
- LLM 流式生成（Ollama）
- TTS 流式合成（默认真实 Piper，启动时自动下载模型并校验）
- Docker Compose 一键启动

## 快速开始

1. 编辑 `.env` 调整模型与阈值（默认 `LLM_MODEL=llama3.2:3b`、`STT_MODEL=tiny`、`PIPER_USE_MOCK_ON_MISSING=0`）。
   若网络不稳定，建议同时确认 Python 包索引：`PIP_INDEX_URL` 与 `PIP_FALLBACK_INDEX_URL`。
2. 准备知识库文件到 `knowledge_base/`。
3. 启动：

```bash
docker compose up -d --build
```

首次启动会自动预热 llama3.2:3b、faster-whisper tiny，并下载/校验 Piper 模型，耗时会明显长于后续启动。
若 piper_init 失败，服务会继续启动，但 TTS 可能降级或不可用；请查看 piper_init 日志定位原因。
默认采用非阻断预热策略（`STT_PREWARM_STRICT=0`、`PIPER_PREWARM_STRICT=0`），可避免 init 退出码反复阻断服务。

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

`/healthz` 会返回 `tts_mode`、`piper_bin_found`、`piper_model_exists`，以及 `prewarm.stt` / `prewarm.piper` 状态字段。

## UART 有线模式（实验版）

后端已支持可选 UART 模式，默认关闭，不影响现有 WebSocket 使用。

1. 在 `.env` 配置 UART 参数（示例）：

```bash
UART_ENABLED=1
UART_PORT=/dev/ttyAMA0
UART_BAUDRATE=115200
UART_AUDIO_CODEC=ulaw8k
UART_DEVICE_SAMPLE_RATE=8000
```

1. 在树莓派主机上开启容器设备透传（取消 [docker-compose.yml](docker-compose.yml) 中 `fastapi_backend` 的 `devices` 注释）。
1. 重启服务：

```bash
docker compose up -d --build
```

1. 查看健康状态：

```bash
curl http://localhost:8000/healthz
```

`healthz` 中的 `uart` 字段会返回 `running`、`connected`、`rx_frames`、`tx_frames`、`crc_errors` 等运行指标。

说明：115200 带宽下不适合直接传 16k PCM，当前默认使用 `ulaw8k`，用于降低串口占用并提升稳定性。

## 目录结构

- `backend/` 后端服务与异步管线
- `frontend/` 浏览器端采集与播放
- `knowledge_base/` 挂载知识库目录
- `lancedb_data/` 向量库持久化目录
- `ollama_data/` Ollama 模型持久化目录
- `piper_cache/` Piper 模型持久化目录
