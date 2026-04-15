# 树莓派语音 RAG 助手（MVP）

基于 FastAPI + WebSocket + Whisper.cpp/Faster-Whisper + LanceDB + Ollama + Piper 的单用户低延迟语音链路实现。

## 功能范围（当前）

- WebSocket 全双工音频传输（上行麦克风 / 下行 PCM）
- UART 有线半双工语音链路（实验版，支持上行语音与下行 TTS 回传）
- STT（优先 Whisper.cpp q5_0，失败时自动回退到 Faster-Whisper）
- RAG 检索（LanceDB 检索，缺失时回退文件检索）
- LLM 流式生成（Ollama）
- TTS 流式合成（默认真实 Piper，启动时自动下载模型并校验）
- Docker Compose 一键启动

## 快速开始

1. 编辑 `.env` 调整模型与阈值（默认 `LLM_MODEL=llama3.2:3b`、`STT_PROVIDER=whisper_cpp`、`STT_CPP_QUANT=q5_0`、`PIPER_USE_MOCK_ON_MISSING=0`）。
   若网络不稳定，建议同时确认 Python 包索引：`PIP_INDEX_URL` 与 `PIP_FALLBACK_INDEX_URL`。
2. 准备知识库文件到 `knowledge_base/`。
3. 启动：

```bash
docker compose up -d --build
```

首次启动会自动预热 llama3.2:3b、STT（按 `STT_PROVIDER` 选择 whisper.cpp 或 faster-whisper），并下载/校验 Piper 模型，耗时会明显长于后续启动。
若 piper_init 失败，服务会继续启动，但 TTS 可能降级或不可用；请查看 piper_init 日志定位原因。
默认采用非阻断预热策略（`STT_PREWARM_STRICT=0`、`PIPER_PREWARM_STRICT=0`），可避免 init 退出码反复阻断服务。
`*_init` 容器是一次性任务，看到 Exited 不代表主服务未启动，请以 `edge_fastapi`/`edge_frontend` 的 Up 状态和 `/healthz` 结果为准。
若日志出现 `No module named 'requests'`，需要重新构建后端镜像以拉取新增依赖：`docker compose build --no-cache fastapi_backend`。
若 Piper 下载报 `Errno 99` 或 `Address family for hostname not supported`，可使用 `.env` 中的 `PIPER_MODEL_FALLBACK_URLS`、`PIPER_MODEL_CONFIG_FALLBACK_URLS`，并保持 `PIPER_DOWNLOAD_TRUST_ENV=1`、`PIPER_DOWNLOAD_LOCAL_ADDRESS=`（留空自动选择）。
排障命令请使用 `docker compose logs -f fastapi_backend`（不是 `fastapi`）以及 `curl -s http://127.0.0.1:8000/healthz`（不是 `crul`）。

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

`/healthz` 会返回 `stt_provider`、`stt_backend`、`stt` 详情，以及 `prewarm.stt` / `prewarm.piper` 状态字段。

## Whisper.cpp q5_0 手动模型放置

默认 STT 路由为 whisper.cpp，量化等级为 q5_0。请确保模型文件已放到容器挂载目录中：

- 主机路径：`whisper_cache/models/whisper-small-q5_0.gguf`
- 容器路径：`/app/model_cache/models/whisper-small-q5_0.gguf`

关键环境变量（`.env`）：

```bash
STT_PROVIDER=whisper_cpp
STT_CPP_MODEL_PATH=/app/model_cache/models/whisper-small-q5_0.gguf
STT_CPP_QUANT=q5_0
STT_CPP_BIN=/app/whisper.cpp/whisper-cli
STT_CPP_FALLBACK_TO_FASTER=1
```

如果你临时要切回 Faster-Whisper，可设置：

```bash
STT_PROVIDER=faster_whisper
```

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

## 离线模型打包（上传 Git）

如果你希望完全不依赖目标机器外网，可先在一台可联网机器执行离线打包，再把模型缓存一起提交。
Windows 预下载脚本现在只拉取 Whisper 和 Piper；Ollama 的 llama3.2:3b 直接使用树莓派上已有的本地模型，不再在 Windows 上额外下载。

1. 安装 Git LFS（只需一次）：

```bash
git lfs install
```

1. 运行一键预下载脚本：

```bash
sh prefetch_models_for_git.sh
```

Windows PowerShell 可执行：

```powershell
./prefetch_models_for_git.ps1
```

如需切换 Whisper / Piper 模型来源仓库，可在执行前覆盖这些变量（可选）：

```bash
export STT_GIT_REPO=https://huggingface.co/Systran/faster-whisper-tiny
export PIPER_GIT_REPO=https://huggingface.co/rhasspy/piper-voices
export PIPER_GIT_MODEL_REL_PATH=zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx
```

PowerShell：

```powershell
$env:STT_GIT_REPO = "https://huggingface.co/Systran/faster-whisper-tiny"
$env:PIPER_GIT_REPO = "https://huggingface.co/rhasspy/piper-voices"
$env:PIPER_GIT_MODEL_REL_PATH = "zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
```

1. 提交模型缓存目录：

```bash
git add .gitattributes piper_cache whisper_cache
git commit -m "chore: add offline whisper and piper models"
git push
```

注意：模型体积很大，普通 Git 可能触发平台文件大小限制，建议始终使用 Git LFS。

## 目录结构

- `backend/` 后端服务与异步管线
- `frontend/` 浏览器端采集与播放
- `knowledge_base/` 挂载知识库目录
- `lancedb_data/` 向量库持久化目录
- `ollama_data/` Ollama 模型持久化目录
- `ollama_models/` 离线 GGUF 模型目录（用于本地创建 Ollama 模型）
- `piper_cache/` Piper 模型持久化目录
- `whisper_cache/` Faster-Whisper 模型缓存目录
