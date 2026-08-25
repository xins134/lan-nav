# lan-nav

个人局域网导航页：视觉偏 Linear / Raycast，数据存本地 YAML，无需数据库与 Docker。适合家庭/实验室内网，经系统 Nginx 反向代理部署在 Debian。

## 功能概览

- 分类与链接的增删改、排序、折叠
- 置顶区、实时搜索（`/` 聚焦，`Esc` 清空）
- 深浅色主题、响应式布局
- YAML 原子写入 + `.bak` 备份 + 损坏自动恢复
- `ADMIN_TOKEN` 保护写入；未设置时页面会明确提示风险

## 安全说明

这是**个人/家庭局域网**工具，默认无多用户账户。

- 未设置 `ADMIN_TOKEN`：任何人可编辑，**仅建议可信局域网**。
- 设置 `ADMIN_TOKEN` 后：进入编辑模式需输入 Token；Token 仅存浏览器 `sessionStorage`。
- 所有写入 API 校验 `X-Admin-Token`；读取无需认证。
- **若暴露公网**，必须额外采用 VPN、Nginx Basic Auth 或其他访问控制，不要只依赖本应用的 Token。

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
├── scripts/             # 开发与 Debian 安装脚本
├── tests/
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
- 默认绑定 `127.0.0.1`，不会暴露到局域网

测试：

```bash
pytest -q
```

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `ADMIN_TOKEN` | 写入保护 Token，留空则不启用 | 空 |
| `HOST` | 监听地址 | `127.0.0.1` |
| `PORT` | 端口 | `8090` |
| `DEBUG` | 热重载 | `false`（示例为 `true`） |
| `TZ` | 时区 | `Asia/Shanghai` |
| `DATA_FILE` | 数据文件路径 | `data/navigation.yml` |

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
ADMIN_TOKEN=请替换为高强度随机密码
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

7. Nginx：

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/lan-nav
sudo ln -s /etc/nginx/sites-available/lan-nav /etc/nginx/sites-enabled/lan-nav
sudo nginx -t
sudo systemctl reload nginx
```

在客户端 `/etc/hosts` 或局域网 DNS 添加：

```text
<Debian内网IP>  nav.lan
```

然后访问 <http://nav.lan>。

## 数据文件

- 正式数据：`data/navigation.yml`（首次启动由示例/演示数据生成）
- 备份：`data/navigation.yml.bak`
- 示例：`data/navigation.yml.example`

可用文本编辑器直接改 YAML；应用写入前会校验结构并原子替换。

## API 摘要

统一响应：`{ "success": true, "data": {} }`

| 方法 | 路径 | 认证 |
|------|------|------|
| GET | `/api/health` | 否 |
| GET | `/api/auth/verify` | 写入保护开启时需要 |
| GET | `/api/navigation` | 否 |
| POST/PUT/DELETE | `/api/categories...` | 是 |
| POST/PUT/DELETE | `/api/links...` | 是 |

## 许可证

自用项目；Lucide 图标遵循其 ISC 许可。
