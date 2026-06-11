# Axis / TrendAI 后端 Linux 部署文档

本文档面向“前端不部署在这台服务器，只在 Linux 服务器部署后端 API + RDS MySQL”的方式。

推荐结构：

- 后端 FastAPI 放在 `/opt/axis/backend`
- 后端只监听 `127.0.0.1:8000`
- Nginx 对外提供 API 域名，并把 `/api/` 代理到后端
- 数据库使用 RDS MySQL，库名为 `axis`
- 前端部署在其他位置，通过 `VITE_API_BASE_URL` 指向后端 API 域名

仓库内已准备的部署模板：

```text
deploy/linux/init-server.sh
deploy/linux/init-rds.sql
deploy/linux/axis-backend.service
deploy/linux/nginx-axis.conf
```

## 1. 服务器要求

当前后端对服务器要求不高，轻量云服务器可以运行。

建议起步配置：

- 系统：Ubuntu 22.04 或 Ubuntu 24.04
- CPU：2 vCPU
- 内存：2 GB
- 系统盘：40 GB
- 数据库：RDS MySQL 8.x
- 公网端口：开放 80 / 443
- 出站网络：允许访问 Binance、大模型 API、Pushover

RDS 建议和云服务器在同一个 VPC / 内网环境。扫描策略较多时，瓶颈通常先出现在网络请求和扫描耗时，而不是页面访问。

## 2. RDS MySQL 准备

### 2.1 创建 RDS

在云厂商控制台创建 MySQL RDS。

建议配置：

- 版本：MySQL 8.x
- 字符集：`utf8mb4`
- 网络：与云服务器在同一个 VPC 或同一个内网环境
- 安全组：只允许云服务器内网 IP 或云服务器安全组访问 `3306`
- 不建议把 RDS 的 `3306` 开放给 `0.0.0.0/0`

### 2.2 初始化数据库和应用账号

先修改 `deploy/linux/init-rds.sql` 里的密码：

```sql
CREATE DATABASE IF NOT EXISTS axis
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'axis_app'@'%' IDENTIFIED BY 'CHANGE_ME_STRONG_PASSWORD';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
ON axis.*
TO 'axis_app'@'%';

FLUSH PRIVILEGES;
```

然后使用 RDS 管理账号执行：

```bash
mysql -h <RDS_HOST> -P 3306 -u <RDS_ADMIN_USER> -p < deploy/linux/init-rds.sql
```

说明：

- 后端启动时会自动创建缺失的数据表，所以应用账号需要 `CREATE / INDEX / ALTER`。
- 如果后续想收紧权限，可以先用高权限账号完成首次初始化，再把线上账号收紧为常规读写权限。
- 正式环境不要使用 RDS root 账号作为应用账号。

### 2.3 验证 RDS 连接

在云服务器上测试：

```bash
mysql -h <RDS_HOST> -P 3306 -u axis_app -p axis -e "SELECT 1;"
```

能正常返回结果，说明服务器到 RDS 的网络和账号权限没问题。

## 3. 初始化 Linux 服务器

先把项目代码上传到服务器，例如 `/tmp/axis-release`。

执行初始化脚本：

```bash
cd /tmp/axis-release
sudo bash deploy/linux/init-server.sh
```

脚本会安装：

- `nginx`
- `mysql-client`
- `python3`
- `python3-venv`
- `python3-pip`
- `curl`
- `unzip`

脚本会创建：

```text
/opt/axis/backend
axis 系统用户
```

## 4. 部署后端

### 4.1 上传后端文件

把本地 `backend` 目录同步到服务器：

```bash
sudo rsync -a --delete backend/ /opt/axis/backend/
sudo chown -R axis:axis /opt/axis/backend
```

目录应类似：

```text
/opt/axis/backend
  app/
  requirements.txt
  .env
```

不要上传：

```text
.venv/
.pytest_cache/
data/
*.log
```

### 4.2 配置后端环境变量

创建 `/opt/axis/backend/.env`：

```bash
sudo nano /opt/axis/backend/.env
```

示例：

```env
MYSQL_HOST=<RDS_HOST>
MYSQL_PORT=3306
MYSQL_USER=axis_app
MYSQL_PASSWORD=<RDS_PASSWORD>
MYSQL_DATABASE=axis

# 前端不在同一台服务器时，需要允许前端访问后端 API。
# 多个来源用英文逗号分隔，不要带路径。
CORS_ALLOW_ORIGINS=https://your-frontend-domain.com,http://localhost:5173
```

权限建议：

```bash
sudo chown axis:axis /opt/axis/backend/.env
sudo chmod 600 /opt/axis/backend/.env
```

正式环境不要配置：

```env
ALLOW_MYSQL_RESET=1
```

### 4.3 安装 Python 依赖

```bash
cd /opt/axis/backend
sudo -u axis python3 -m venv .venv
sudo -u axis ./.venv/bin/python -m pip install --upgrade pip
sudo -u axis ./.venv/bin/pip install -r requirements.txt
```

### 4.4 安装 systemd 服务

复制服务模板：

```bash
sudo cp /tmp/axis-release/deploy/linux/axis-backend.service /etc/systemd/system/axis-backend.service
sudo systemctl daemon-reload
sudo systemctl enable axis-backend
sudo systemctl start axis-backend
```

查看状态：

```bash
sudo systemctl status axis-backend
```

查看日志：

```bash
sudo journalctl -u axis-backend -f
```

本机健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

正常返回：

```json
{"status":"ok"}
```

## 5. 配置 API Nginx

服务器不部署前端，但建议仍然用 Nginx 对外暴露 API，并让 Python 服务只监听本机。

复制 Nginx 模板：

```bash
sudo cp /tmp/axis-release/deploy/linux/nginx-axis.conf /etc/nginx/sites-available/axis-api
```

编辑域名：

```bash
sudo nano /etc/nginx/sites-available/axis-api
```

把：

```nginx
server_name api.your-domain.com;
```

改成你的 API 域名或服务器公网 IP：

```nginx
server_name api.example.com;
```

启用配置：

```bash
sudo ln -sf /etc/nginx/sites-available/axis-api /etc/nginx/sites-enabled/axis-api
sudo nginx -t
sudo systemctl reload nginx
```

外部健康检查：

```bash
curl http://api.example.com/api/health
```

如果要直接用公网 IP，也可以：

```bash
curl http://<SERVER_PUBLIC_IP>/api/health
```

## 6. HTTPS

建议给 API 域名配置 HTTPS，否则浏览器里如果前端是 HTTPS，调用 HTTP API 会被拦截。

使用 Certbot：

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.example.com
```

验证：

```bash
curl https://api.example.com/api/health
```

## 7. 前端怎么连接这个后端

前端不部署在该服务器时，构建前需要设置后端地址。

本地或前端部署环境创建：

```text
frontend/.env.production
```

内容示例：

```env
VITE_API_BASE_URL=https://api.example.com
```

然后构建前端：

```bash
cd frontend
npm install
npm run build
```

说明：

- `VITE_API_BASE_URL` 只写域名，不要写 `/api`。
- 前端代码会自动请求 `https://api.example.com/api/...`。
- 如果前端本地开发，`VITE_API_BASE_URL` 可以不配置，Vite 会通过 `vite.config.ts` 把 `/api` 代理到本地后端。
- 如果前端部署在静态平台，必须配置 `VITE_API_BASE_URL`，否则浏览器会请求静态平台自己的 `/api`。

后端也要同步允许前端来源：

```env
CORS_ALLOW_ORIGINS=https://your-frontend-domain.com
```

修改 `.env` 后重启后端：

```bash
sudo systemctl restart axis-backend
```

## 8. 首次启动后的初始化

后端首次启动会自动创建缺失的数据表，包括：

- `users`
- `settings`
- `strategies`
- `signals`
- `watch_items`
- `knowledge_cases`
- `strategy_generation_cache`
- `strategy_scan_history`
- `market_klines`

打开前端后：

1. 注册第一个用户。
2. 进入“设置”，配置大模型 API。
3. 如需信号提醒，配置 Pushover。
4. 创建 AI 策略或粘贴代码生成策略。
5. 暂停状态下编辑策略，确认无误后启用。
6. 开启定时任务开关，或手动点击立即运行。

## 9. 定时任务和扫描

后端启动后会随 FastAPI 进程启动策略调度器。

运行逻辑：

- 只有启用中的策略会被定时扫描。
- 运行间隔跟策略周期绑定，例如 `1H` 策略按 1 小时间隔运行。
- 手动“立即运行”会扫描启用中的策略。
- 扫描是全市场扫描，不依赖观察池。
- 每个策略的币种黑名单会在扫描时跳过对应币种。

查看后台日志：

```bash
sudo journalctl -u axis-backend -f
```

## 10. Pushover 信号提醒

在“设置”里配置：

- 启用 Pushover
- User Key
- Application Token

扫描发现信号后会发送通知。推送失败不会影响信号入库，也不会中断扫描。

通知示例：

```text
TrendAI 信号：ALLUSDT 1H

币种：ALLUSDT
周期：1H
策略：箱体蓄势放量突破策略
价格：0.2563
评分：88
```

## 11. K 线缓存

策略扫描拉取 K 线后，会写入 `market_klines` 表。

信号详情页会优先从数据库读取 K 线，用于展示信号触发时附近的走势和信号点。

可以检查缓存是否写入：

```bash
mysql -h <RDS_HOST> -P 3306 -u axis_app -p axis -e "SELECT COUNT(*) FROM market_klines;"
```

说明：

- 老信号如果是在 K 线缓存上线前生成的，可能没有完整走势。
- 新扫描生成的信号会更稳定地显示 K 线走势。

## 12. 更新后端

```bash
sudo systemctl stop axis-backend
sudo rsync -a --delete backend/ /opt/axis/backend/
sudo chown -R axis:axis /opt/axis/backend
cd /opt/axis/backend
sudo -u axis ./.venv/bin/pip install -r requirements.txt
sudo systemctl start axis-backend
sudo journalctl -u axis-backend -f
```

前端独立部署时，只需要在前端平台重新构建和发布即可。确保它的 `VITE_API_BASE_URL` 指向当前 API 域名。

## 13. 备份建议

RDS 建议开启：

- 自动备份，至少保留 7 天
- 重要更新前手动快照
- 误删保护，如云厂商支持

上线更新前建议先备份：

```bash
mysqldump -h <RDS_HOST> -P 3306 -u <RDS_ADMIN_USER> -p axis > axis_backup_$(date +%F_%H%M%S).sql
```

## 14. 常用运维命令

重启后端：

```bash
sudo systemctl restart axis-backend
```

查看后端状态：

```bash
sudo systemctl status axis-backend
```

查看后端日志：

```bash
sudo journalctl -u axis-backend -f
```

查看 Nginx 配置：

```bash
sudo nginx -t
```

查看 Nginx 日志：

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

查看端口：

```bash
ss -lntp | grep -E ':80|:443|:8000'
```

验证 API：

```bash
curl http://127.0.0.1:8000/api/health
curl https://api.example.com/api/health
```

## 15. 安全建议

- 服务器安全组只开放 `80` 和 `443`。
- 后端只监听 `127.0.0.1:8000`，不要直接暴露公网。
- RDS 只允许云服务器内网访问，不要开放公网全网访问。
- `.env` 不要提交到代码仓库。
- RDS 应用账号只授权 `axis.*`。
- 正式环境不要设置 `ALLOW_MYSQL_RESET=1`。
- 大模型 API Key、Pushover Token 都只放在设置或 `.env` 中，不要写入代码。
- `CORS_ALLOW_ORIGINS` 只配置真实前端域名，不要在正式环境里配置 `*`。

## 16. 常见问题

### 16.1 前端请求 API 404

检查前端构建时是否配置：

```env
VITE_API_BASE_URL=https://api.example.com
```

注意不要写成：

```env
VITE_API_BASE_URL=https://api.example.com/api
```

前端会自动拼接 `/api/...`。

### 16.2 浏览器提示跨域错误

检查后端 `.env`：

```env
CORS_ALLOW_ORIGINS=https://your-frontend-domain.com
```

修改后重启：

```bash
sudo systemctl restart axis-backend
```

### 16.3 登录提示账号密码错误，但数据库有用户

优先检查后端实际连接的是不是目标 RDS：

```bash
sudo systemctl show axis-backend --property=EnvironmentFiles
sudo cat /opt/axis/backend/.env
```

再检查：

```bash
mysql -h <RDS_HOST> -P 3306 -u axis_app -p axis -e "SELECT id,email,created_at FROM users ORDER BY created_at DESC LIMIT 5;"
```

如果本地能登录、服务器不能登录，通常是服务器 `.env` 指向了另一个库。

### 16.4 API 502

检查后端是否启动：

```bash
curl http://127.0.0.1:8000/api/health
sudo journalctl -u axis-backend -f
```

如果本机 API 正常，但域名访问失败，检查 Nginx 的 `/api/` 代理配置。

### 16.5 策略没有定时运行

检查：

- 策略是否启用。
- 定时任务开关是否开启。
- systemd 后端服务是否持续运行。
- 后端日志是否有扫描任务异常。

```bash
sudo journalctl -u axis-backend -f
```

### 16.6 扫描没有信号

可能原因：

- 策略条件确实不满足。
- 币种在该策略黑名单里。
- Binance K 线获取失败。
- 币种 K 线数量不足。
- 策略代码运行返回 `False`。

可以先手动运行一次，观察策略中心的扫描进度、跳过详情和错误详情。

### 16.7 Pushover 没有推送

检查：

- 设置页是否启用 Pushover。
- User Key 和 Application Token 是否正确。
- 服务器是否能访问 `https://api.pushover.net`。
- 后端日志是否出现 `Pushover推送失败`。

## 17. 上线检查清单

```text
[ ] RDS MySQL 已创建
[ ] RDS 安全组只允许云服务器访问 3306
[ ] axis 数据库已创建
[ ] axis_app 用户已创建并授权
[ ] 云服务器可以连接 RDS
[ ] /opt/axis/backend/.env 已配置 RDS
[ ] CORS_ALLOW_ORIGINS 已配置前端域名
[ ] Python 依赖已安装
[ ] axis-backend systemd 已启动
[ ] 127.0.0.1:8000/api/health 正常
[ ] Nginx 已配置 API 反代并 reload
[ ] https://api.example.com/api/health 正常
[ ] 前端 VITE_API_BASE_URL 指向 API 域名
[ ] 可以注册和登录
[ ] 设置页已配置大模型 API
[ ] 如需提醒，Pushover 已配置
[ ] 可以创建或保存策略
[ ] 手动扫描可以正常运行
[ ] 定时任务开关已开启
[ ] RDS 自动备份已开启
```
