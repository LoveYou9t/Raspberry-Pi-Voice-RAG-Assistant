# Linux 快速部署文档（Git 版）

本文档用于在 Linux 服务器或树莓派 Linux 系统上，快速部署当前语音 RAG MVP 服务。

## 1. 环境要求

1. 操作系统：Ubuntu 22.04+ 或 Debian 12+（其他主流 Linux 发行版也可）。
2. 已安装 Docker 与 Docker Compose 插件。
3. 建议内存：8GB 及以上。
4. 需要可访问外网以拉取镜像与模型。
5. 已安装 Git（用于拉取与更新代码）。

## 2. 安装基础依赖（Ubuntu/Debian）

1. 更新系统：
   sudo apt update && sudo apt upgrade -y
2. 安装 Docker + Compose + Git：
   sudo apt install -y git docker.io docker-compose-plugin
3. 启动并设置开机自启：
   sudo systemctl enable docker --now
4. 验证安装：
   docker --version
   docker compose version

## 3. 通过 Git 获取项目代码

1. 创建部署目录并进入：
   mkdir -p ~/apps && cd ~/apps
2. 克隆仓库（替换为你的仓库地址）：
   git clone <你的Git仓库地址> edge-voice-rag
3. 进入项目目录：
   cd ~/apps/edge-voice-rag
4. （可选）切换到指定分支：
   git checkout main
5. 确认目录中存在以下关键文件：
   docker-compose.yml、.env、backend、frontend、knowledge_base

## 4. 启动服务

1. 在项目根目录执行：
   docker compose up -d --build
2. 查看容器状态：
   docker compose ps
3. 首次启动会自动预热 `llama3.2:3b`、`faster-whisper tiny`，并自动下载/校验 Piper 模型，耗时会更长。
4. 启动成功时，关键容器状态一般为：
   edge_ollama、edge_fastapi、edge_frontend 为 Up；
   edge_ollama_init、edge_stt_init、edge_piper_init 为 Exited (0)。

## 5. 模型预热检查（自动）

1. 查看 Ollama 模型列表：
   docker exec edge_ollama ollama list
2. 查看 Piper 预热日志：
   docker compose logs -f piper_init
3. 查看后端健康检查（确认 STT/LLM/TTS 配置）：
   curl <http://127.0.0.1:8000/healthz>
4. 在健康检查结果中确认以下字段：
   `tts_mode=real`、`piper_bin_found=true`、`piper_model_exists=true`

## 6. 验证服务

1. 后端健康检查：
   curl <http://127.0.0.1:8000/healthz>
2. 前端访问（本机）：
   <http://127.0.0.1:8080>
3. 局域网访问（其他设备）：
   <http://Linux主机IP:8080>

## 7. 启用 UART 有线模式（实验版，可选）

如果你需要走树莓派串口与 MCU/ESP32 有线通讯，请按以下步骤启用。

1. 编辑 `.env` 并增加参数：
   UART_ENABLED=1
   UART_PORT=/dev/ttyAMA0
   UART_BAUDRATE=115200
   UART_AUDIO_CODEC=ulaw8k
   UART_DEVICE_SAMPLE_RATE=8000
2. 在 `docker-compose.yml` 中，取消 `fastapi_backend` 的 `devices` 注释，使串口设备映射到容器。
3. 重新启动服务：
   docker compose up -d --build
4. 查看健康检查：
   curl <http://127.0.0.1:8000/healthz>
5. 在返回结果的 `uart` 字段中确认：
   `running=true`、`connected=true`。

提示：115200 带宽有限，建议保持 `UART_AUDIO_CODEC=ulaw8k`。若改为原始 PCM，易出现卡顿或丢帧。

## 8. 常用运维命令

1. 查看全部日志：
   docker compose logs -f
2. 查看后端日志：
   docker compose logs -f fastapi_backend
3. 重启服务：
   docker compose restart
4. 停止服务：
   docker compose down

## 9. Git 更新发布（后续升级）

当仓库代码更新后，按以下步骤升级：

1. 进入项目目录：
   cd ~/apps/edge-voice-rag
2. 拉取最新代码：
   git fetch --all
   git pull --rebase origin main
3. 重新构建并启动：
   docker compose up -d --build
4. 验证状态：
   docker compose ps

## 10. 快速排障

1. Ollama 未就绪：
   docker compose logs -f ollama_server
2. 后端报连接模型失败：
   检查 .env 中 OLLAMA_HOST 是否为 `http://ollama_server:11434`
3. 前端可打开但无语音：
   检查浏览器麦克风权限，并查看后端 WebSocket 日志。
4. 内存不足或系统卡顿：
   建议降低模型规格，或减少并发使用。
5. `https://registry-1.docker.io/` 返回 404：
   这是正常现象，根路径不是镜像拉取 API。请用以下方式判断是否可用：
   curl -I <https://registry-1.docker.io/v2/>
   能返回 `401 Unauthorized`（或带 `Docker-Distribution-Api-Version` 响应头）通常表示服务正常。
6. 拉取镜像超时或连接失败：
   可配置 Docker Hub 镜像加速（示例）：
   sudo mkdir -p /etc/docker
   sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
   {
     "registry-mirrors": [
       "https://docker.m.daocloud.io",
       "https://mirror.ccs.tencentyun.com",
       "https://hub-mirror.c.163.com"
     ]
   }
   EOF
   sudo systemctl daemon-reload
   sudo systemctl restart docker
   docker pull nginx:alpine
7. 出现 `bind: address already in use`（11434 端口占用）：
   当前项目默认已不再对宿主机发布 Ollama 11434 端口，更新代码后重新执行：
   git pull --rebase
   docker compose up -d --build
   如果你本地改过 `docker-compose.yml` 并恢复了 `11434:11434` 映射，请改回仅容器内通信，或先停止宿主机 Ollama：
   sudo systemctl stop ollama
8. 出现 `Your kernel does not support memory limit capabilities`：
   这是宿主机 cgroup memory 未启用导致，当前仅表示内存限制未生效，不影响容器启动。
   如需启用限制，请在系统层开启 cgroup memory（不同发行版配置方式不同）。
9. 出现 `dependency failed to start: container edge_ollama is unhealthy`：
   先更新到最新 compose 配置并清理旧容器状态后重启：
   git pull --rebase
   docker compose rm -sf ollama_server
   docker compose up -d --build
   如仍异常，查看 Ollama 日志：
   docker compose logs -f ollama_server
10. 首次启动时间较长、误以为卡住：
   这是模型预热过程导致的正常现象，可用以下命令观察进度：
   docker compose logs -f ollama_init
   docker compose logs -f stt_init
11. 出现 `service "ollama_init" didn't complete successfully: exit 1`：
   请先更新代码后重建（新版已增加重试并避免预热失败阻断启动）：
   git pull --rebase
   docker compose down --remove-orphans
   docker compose up -d --build
   之后可单独检查预热日志：
   docker compose logs -f ollama_init
12. 出现 `service "stt_init" didn't complete successfully: exit 1`：
   请先更新代码后重建（新版已将 stt_init 改为非阻断兜底执行）：
   git pull --rebase
   docker compose down --remove-orphans
   docker compose up -d --build
   如需查看具体原因：
   docker compose logs -f stt_init
13. 出现 `service "piper_init" didn't complete successfully: exit 1`：
   先检查模型下载与二进制日志：
   docker compose logs -f piper_init
   如果是网络问题，可在 `.env` 中替换 `PIPER_MODEL_URL` 与 `PIPER_MODEL_CONFIG_URL` 到可访问镜像地址后重试：
   docker compose up -d --build
14. `healthz` 返回 `tts_mode=unavailable` 或 `status=degraded`：
   说明 Piper 二进制或模型不可用。请依次检查：
   docker compose logs -f piper_init
   docker compose logs -f fastapi_backend
   确认容器内存在模型文件路径（默认 `/app/piper_cache/zh_CN-huayan-medium.onnx`）。
15. 构建阶段出现 `pip ... ProtocolError: Broken pipe`：
   这通常是网络抖动导致。新版镜像构建已内置双索引重试（`PIP_INDEX_URL` + `PIP_FALLBACK_INDEX_URL`），并复用 `fastapi_backend` 镜像给 `stt_init/piper_init`。
   请执行：
   docker compose down --remove-orphans
   docker compose build --no-cache fastapi_backend
   docker compose up -d
   若仍失败，请在 `.env` 明确配置：
   `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`
   `PIP_FALLBACK_INDEX_URL=https://pypi.org/simple`
   然后重试构建。
16. `uart.connected=false` 或日志提示 `failed to open serial port`：
   先确认宿主机设备存在：
   ls -l /dev/ttyAMA0
   再确认 compose 已打开 `devices` 映射且 `UART_PORT` 与映射后的容器路径一致。
17. `crc_errors` 持续增长：
   说明串口链路噪声或帧配置不匹配。请优先检查：
   波特率是否一致（两端都 115200）、地线是否共地、帧格式是否一致（协议头/CRC）。

## 11. 开机自动恢复（可选）

当前 compose 已配置 restart: always，系统重启后 Docker 服务拉起时会自动恢复容器。
如果未自动恢复，请手动执行：

1. sudo systemctl start docker
2. cd ~/apps/edge-voice-rag
3. docker compose up -d
