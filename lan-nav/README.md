# lan-nav

个人局域网导航页：视觉偏 Linear / Raycast，数据存本地 YAML，无需数据库。适合家庭/实验室内网；可用 Docker Compose、或 Debian 上的 systemd（可选 Nginx 反向代理）。

## 功能概览

- 分类与链接的增删改、排序、折叠
- 置顶区、实时搜索（`/` 聚焦，`Esc` 清空）
- 深浅色主题、响应式布局、卡片大中小切换
- 右键 / 长按菜单管理分类与链接
- 页脚导入 / 导出 `navigation.yml` 配置文件
- YAML 原子写入 + `.bak` 备份 + 损坏自动恢复

## 安全说明

这是**个人/家庭局域网**工具，应用内**无账号、无 Token**；能访问站点即可读写数据。

- **内网使用**：建议仅绑定局域网或本机，配合防火墙限制访问来源。
- **经 Nginx 部署**：`.env` 中 `HOST=127.0.0.1`、`DEBUG=false`，由 Nginx 对外提供服务。
- **外网暴露**：请在 Nginx 层做访问控制，例如：
  - 16 位随机 secret path（见 `deploy/nginx.conf.example`，访问时需带末尾 `/`）
  - HTTPS
  - VPN 或 Nginx Basic Auth

## 技术栈

- Python 3.11+
- FastAPI + Uvicorn
- 服务端 HTML 模板 + 原生 JS/CSS
- PyYAML；Lucide 图标本地打包（无运行时 CDN）

## 项目结构

```text
lan-nav/
├── app/                 # FastAPI 应用、模板与静态资源
├── data/                # navigation.yml.example（正式数据运行时生成）
├── deploy/              # systemd 与 Nginx 示例
├── docker/              # 容器入口脚本
├── scripts/             # 开发与 Debian 安装脚本
├── tests/
├── Dockerfile
├── compose.yml
├── .env.example
├── requirements.txt
└── run.py
```

## macOS 本地开发

需要 **Python 3.11+**（macOS 自带的 3.9 不可用）。若已安装 `python3.11`：

```bash
cd lan-nav
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

或（脚本会自动选择 3.11+）：

```bash
bash scripts/dev.sh
```

默认地址：<http://127.0.0.1:8090>

- `.env` 中 `DEBUG=true` 时启用 Uvicorn 热重载
- 局域网访问可将 `HOST` 设为 `0.0.0.0`

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

## Docker 部署（推荐）

Debian 安装 Docker 与 Compose 插件后，在项目目录执行：

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
# 重新登录后使 docker 组生效
cd /opt/lan-nav   # 或你放置项目的目录
docker compose up -d --build
```

- 本机：<http://127.0.0.1:8090>
- 局域网：`http://<Debian内网IP>:8090`
- 数据文件：项目目录下 `data/navigation.yml`（容器重启不丢失）

常用命令：

```bash
docker compose logs -f
docker compose restart
docker compose down
```

## Debian 12 部署

1. 安装依赖：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

2. 将项目放到 `/opt/lan-nav`（或运行 `sudo bash scripts/install-debian.sh`）。

3. 虚拟环境与配置：

```bash
cd /opt/lan-nav
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

4. 编辑 `.env`：

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

6. systemd：

```bash
sudo cp deploy/lan-nav.service /etc/systemd/system/lan-nav.service
sudo systemctl daemon-reload
sudo systemctl enable --now lan-nav
sudo systemctl status lan-nav
```

7. Nginx（内网示例见 `deploy/nginx.conf.example`；外网建议启用 secret path）：

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/lan-nav
sudo ln -s /etc/nginx/sites-available/lan-nav /etc/nginx/sites-enabled/lan-nav
sudo nginx -t
sudo systemctl reload nginx
```

## 数据文件

- 正式数据：`data/navigation.yml`（首次启动由示例/演示数据生成）
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

## 许可证

自用项目；Lucide 图标遵循其 ISC 许可。
