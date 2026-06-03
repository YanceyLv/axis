# Axis 后端打包部署文档

本文档用于将 Axis / TrendAI 的后端作为独立 FastAPI 服务打包并部署。后端部署后提供 `/api/*` 接口，前端只需要配置为访问该后端地址。

## 1. 后端目录结构

后端位于：

```text
D:\Axis\backend
```

核心文件：

```text
backend/
  app/                 # FastAPI 应用代码
  requirements.txt     # Python 依赖
  .env.example         # 环境变量示例
```

不要打包这些目录或文件：

```text
backend/.venv/
backend/.pytest_cache/
backend/.uv-cache/
backend/data/
backend/*.log
```

## 2. 本地打包

在 Windows PowerShell 中进入项目根目录：

```powershell
cd D:\Axis
```

创建部署包目录：

```powershell
New-Item -ItemType Directory -Force .\release\axis-backend | Out-Null
Copy-Item -Recurse .\backend\app .\release\axis-backend\app
Copy-Item .\backend\requirements.txt .\release\axis-backend\requirements.txt
Copy-Item .\backend\.env.example .\release\axis-backend\.env.example
```

压缩为 zip：

```powershell
Compress-Archive -Path .\release\axis-backend\* -DestinationPath .\release\axis-backend.zip -Force
```

生成的部署包：

```text
D:\Axis\release\axis-backend.zip
```

## 3. 服务器准备

服务器需要：

```text
Python 3.10+
MySQL 8.x
```

如果是 Windows 服务器，解压到例如：

```text
D:\axis-backend
```

如果是 Linux 服务器，解压到例如：

```bash
/opt/axis-backend
```

## 4. 安装依赖

### Windows

```powershell
cd D:\axis-backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### Linux

```bash
cd /opt/axis-backend
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

## 5. 配置环境变量

复制 `.env.example` 为 `.env`。

### Windows

```powershell
Copy-Item .env.example .env
```

### Linux

```bash
cp .env.example .env
```

编辑 `.env`：

```env
SIGNAL_DB_DRIVER=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=axis
```

说明：

```text
MYSQL_HOST      MySQL 地址
MYSQL_PORT      MySQL 端口，默认 3306
MYSQL_USER      MySQL 用户
MYSQL_PASSWORD  MySQL 密码
MYSQL_DATABASE  数据库名，当前项目使用 axis
```

后端启动时会自动创建缺失的数据表。

## 6. 启动后端

### Windows

```powershell
cd D:\axis-backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Linux

```bash
cd /opt/axis-backend
./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问健康检查：

```text
http://服务器IP:8000/api/health
```

正常返回：

```json
{"status":"ok"}
```

## 7. 后台运行

### Windows 后台运行

```powershell
$cmd = "cd /d D:\axis-backend && .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k",$cmd -WindowStyle Hidden
```

生产环境建议使用 NSSM 或 Windows 服务托管。

### Linux systemd

创建服务文件：

```bash
sudo nano /etc/systemd/system/axis-backend.service
```

写入：

```ini
[Unit]
Description=Axis Backend API
After=network.target

[Service]
WorkingDirectory=/opt/axis-backend
ExecStart=/opt/axis-backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable axis-backend
sudo systemctl start axis-backend
sudo systemctl status axis-backend
```

查看日志：

```bash
journalctl -u axis-backend -f
```

## 8. 前端对接后端

如果前端和后端不在同一个地址，需要确认两件事：

1. 前端请求的 API 地址指向部署后的后端。
2. 后端 CORS 允许前端域名。

后端 CORS 配置在：

```text
backend/app/main.py
```

找到：

```python
allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
```

加入你的前端地址，例如：

```python
allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://your-frontend-domain.com",
]
```

修改后需要重新打包并重启后端。

## 9. 防火墙与端口

后端默认端口：

```text
8000
```

如果需要公网访问，需要开放服务器防火墙的 8000 端口，或通过 Nginx 反向代理到 8000。

示例 Nginx：

```nginx
server {
    listen 80;
    server_name api.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 10. 常见问题

### 10.1 `/api/health` 打不开

检查后端是否启动：

```powershell
netstat -ano | findstr :8000
```

或 Linux：

```bash
ss -lntp | grep 8000
```

### 10.2 数据库连接失败

检查 `.env`：

```env
MYSQL_HOST
MYSQL_PORT
MYSQL_USER
MYSQL_PASSWORD
MYSQL_DATABASE
```

确认服务器能连接 MySQL：

```bash
mysql -h 127.0.0.1 -P 3306 -u your_mysql_user -p
```

### 10.3 前端提示 401

说明接口需要登录 token。重新登录即可。

如果刚换数据库，原用户可能不存在，需要重新注册或迁移 `users` 表。

### 10.4 前端提示跨域

把前端域名加入 `backend/app/main.py` 的 `allow_origins`，然后重启后端。

### 10.5 不要在 MySQL 正式库执行 reset

当前代码已经默认禁止 MySQL 下执行 `store.reset()`。只有明确设置：

```env
ALLOW_MYSQL_RESET=1
```

才允许清空 MySQL 数据。正式部署不要设置这个变量。

## 11. 快速检查清单

部署完成后逐项确认：

```text
[ ] .env 已配置 MySQL
[ ] Python 依赖安装完成
[ ] 后端 8000 端口已启动
[ ] /api/health 返回 {"status":"ok"}
[ ] 前端域名已加入 CORS
[ ] MySQL 中 axis 数据库可访问
[ ] 可以注册/登录
[ ] 可以查看策略中心
[ ] 可以运行策略扫描
```
