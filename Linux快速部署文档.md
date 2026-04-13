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
3. 看到以下容器为 Up 即表示启动成功：
   edge_ollama、edge_fastapi、edge_frontend

## 5. 首次模型预热（可选但推荐）

1. 拉取默认模型：
   docker exec edge_ollama ollama pull llama3.2:3b
2. 查看模型列表：
   docker exec edge_ollama ollama list

## 6. 验证服务

1. 后端健康检查：
   curl <http://127.0.0.1:8000/healthz>
2. 前端访问（本机）：
   <http://127.0.0.1:8080>
3. 局域网访问（其他设备）：
   <http://Linux主机IP:8080>

## 7. 常用运维命令

1. 查看全部日志：
   docker compose logs -f
2. 查看后端日志：
   docker compose logs -f fastapi_backend
3. 重启服务：
   docker compose restart
4. 停止服务：
   docker compose down

## 8. Git 更新发布（后续升级）

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

## 9. 快速排障

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

## 10. 开机自动恢复（可选）

当前 compose 已配置 restart: always，系统重启后 Docker 服务拉起时会自动恢复容器。
如果未自动恢复，请手动执行：

1. sudo systemctl start docker
2. cd ~/apps/edge-voice-rag
3. docker compose up -d
