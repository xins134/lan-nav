# lan-nav

个人局域网导航页：视觉偏 Linear / Raycast，数据存本地 YAML，无需数据库。适合家庭 / 实验室内网，可在网页上增删改分类与链接，数据自动持久化到本地文件。

> 预构建镜像：`ghcr.io/xins134/lan-nav`（默认分支自动发布 `latest`，详见下方「Docker 部署」）。

## 特性

- 分类与链接的新增、编辑、删除、排序、折叠
- 置顶区、实时搜索（`/` 聚焦，`Esc` 清空）
- 深浅色主题、响应式布局、卡片大中小切换
- 右键 / 长按菜单管理分类与链接
- 页脚导入 / 导出 `navigation.yml` 配置文件
- YAML 原子写入 + `.bak` 备份 + 损坏自动恢复
- 图标本地打包（Lucide），无运行时 CDN 依赖

## 技术栈

- Python 3.11+
- FastAPI + Uvicorn
- 服务端 HTML 模板 + 原生 JS/CSS
- PyYAML

## 项目结构

```text
.
├── app/                 # FastAPI 应用、模板与静态资源
├── data/                # navigation.yml.example（正式数据运行时生成）
├── deploy/              # systemd 与 Nginx 示例
├── docker/              # 容器入口脚本
├── scripts/             # 开发与 Debian 安装脚本
├── tests/
├── Dockerfile
├── compose.yml
├── .env.example
├── requirements.txt      # 运行时依赖
├── requirements-dev.txt  # 开发/测试依赖
└── run.py
```

## 快速开始

### Docker 部署（推荐）

```bash
git clone https://github.com/xins134/lan-nav.git
cd lan-nav
docker compose up -d --build
```

或直接使用预构建镜像：

```bash
docker pull ghcr.io/xins134/lan-nav:latest
```

- 本机访问：<http://127.0.0.1:8090>
- 局域网访问：`http://<内网IP>:8090`
- 数据文件：项目目录下 `data/navigation.yml`（挂载到容器后重启不丢失）

常用命令：

```bash
docker compose logs -f
docker compose restart
docker compose down
```

### macOS 本地开发

需要 **Python 3.11+**（macOS 自带的 3.9 不可用）：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # 仅运行用 requirements.txt
cp .env.example .env
python run.py
```

或使用脚本（自动选择 3.11+）：

```bash
bash scripts/dev.sh
```

默认地址：<http://127.0.0.1:8090>

测试：

```bash
pytest -q
```

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `HOST` | 监听地址 | `127.0.0.1` |
| `PORT` | 端口 | `8090` |
| `DEBUG` | 热重载 | `false`（示例为 `true`） |
| `TZ` | 时区 | `Asia/Shanghai` |
| `DATA_FILE` | 数据文件路径 | `data/navigation.yml` |
| `EXAMPLE_FILE` | 首次初始化用的示例 YAML | `data/navigation.yml.example` |
| `ACCESS_LOG` | 是否输出逐请求访问日志 | `false` |
| `UVICORN_LOOP` | 事件循环：`asyncio` / `uvloop`（需自行安装） | `asyncio` |
| `UVICORN_HTTP` | HTTP 实现：`h11` / `httptools`（需自行安装） | `h11` |
| `KEEPALIVE_TIMEOUT` | 长连接保活秒数 | `5` |
| `LIMIT_CONCURRENCY` | 最大并发连接数（空为不限制） | 空 |
| `FORWARDED_ALLOW_IPS` | 信任的反代来源 IP | `127.0.0.1` |

## Debian 12 部署

1. 安装依赖：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

2. 将项目放到 `/opt/lan-nav`（或运行 `sudo bash scripts/install-debian.sh`）。

3. 创建虚拟环境并配置：

```bash
cd /opt/lan-nav
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

4. 编辑 `.env`（生产环境 `DEBUG=false`，`HOST=127.0.0.1` 由 Nginx 对外提供服务）：

```env
HOST=127.0.0.1
PORT=8090
DEBUG=false
TZ=Asia/Shanghai
```

5. 创建专用用户并授权 `data/` 可写：

```bash
sudo useradd --system --home /opt/lan-nav --shell /usr/sbin/nologin lan-nav
sudo chown -R lan-nav:lan-nav /opt/lan-nav
```

6. 安装 systemd 服务：

```bash
sudo cp deploy/lan-nav.service /etc/systemd/system/lan-nav.service
sudo systemctl daemon-reload
sudo systemctl enable --now lan-nav
sudo systemctl status lan-nav
```

7. 配置 Nginx（内网示例见 `deploy/nginx.conf.example`；外网建议启用 secret path）：

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/lan-nav
sudo ln -s /etc/nginx/sites-available/lan-nav /etc/nginx/sites-enabled/lan-nav
sudo nginx -t
sudo systemctl reload nginx
```

## 资源占用优化

个人导航页对吞吐要求极低，默认按「省内存 / 省 CPU」取向配置：

- **运行时依赖精简**：镜像只安装 `requirements.txt`（不含 `pytest` 等开发依赖），
  且使用纯 `uvicorn`（不装 `uvicorn[standard]`），避免载入 uvloop / httptools /
  websockets / watchfiles。
- **单进程 + 精简协议栈**：`run.py` 固定单 worker、`loop=asyncio`、`http=h11`、
  关闭 WebSocket，并关闭访问日志与 `server` / `date` 响应头。
- **存储层内存缓存**：`app/storage.py` 以文件 `mtime + 大小 + inode` 为键缓存已解析
  的导航数据，命中时不再重复读取 / 解析 YAML 与模型校验
  （约 `3.7ms → 2.7µs` / 次）。
- **容器资源上限**：`compose.yml` 默认限制 `0.50` CPU、`128M` 内存，并限制日志体积。

如需更高吞吐，可自行 `pip install uvloop httptools` 并设置
`UVICORN_LOOP=uvloop`、`UVICORN_HTTP=httptools`。

## 数据文件

- 正式数据：`data/navigation.yml`（首次启动由示例 / 演示数据生成）
- 备份：`data/navigation.yml.bak`
- 示例：`data/navigation.yml.example`

## API 摘要

统一响应：`{ "success": true, "data": {} }`

| 方法 | 路径 |
|------|------|
| GET | `/api/health` |
| GET | `/api/navigation` |
| GET | `/api/export` |
| POST | `/api/import` |
| POST/PUT/DELETE | `/api/categories...` |
| POST/PUT/DELETE | `/api/links...` |

## 安全说明

这是**个人 / 家庭局域网**工具，应用内**无账号、无 Token**；能访问站点即可读写数据。

- **内网使用**：建议仅绑定局域网或本机，配合防火墙限制访问来源。
- **经 Nginx 部署**：`.env` 中 `HOST=127.0.0.1`、`DEBUG=false`，由 Nginx 对外提供服务。
- **外网暴露**：请在 Nginx 层做访问控制，例如：
  - 16 位随机 secret path（见 `deploy/nginx.conf.example`，访问时需带末尾 `/`）
  - HTTPS
  - VPN 或 Nginx Basic Auth

## 许可证

自用项目；Lucide 图标遵循其 ISC 许可。
