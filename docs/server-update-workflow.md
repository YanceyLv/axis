# Axis / TrendAI 服务器更新与重新部署流程

本文档专门说明一个高频场景：

- 你已经在本地修改了 `D:\Axis` 项目代码
- 服务器上已经部署并运行了 Axis / TrendAI
- 现在需要把本地最新代码更新到服务器，并重新部署服务

本文档默认场景：

- 后端部署在 Linux 服务器
- 后端目录为 `/opt/axis/backend`
- 服务名为 `axis-backend`
- 使用 `systemd` 托管
- 使用 MySQL，可能是服务器本机 MySQL，也可能是云上 RDS

如果你的实际目录不同，请把命令中的路径替换成真实路径。

## 1. 什么时候需要执行这份流程

本地修改后，只要涉及下面任一项，就应该按本文档更新服务器：

- `backend/app/` 下的 Python 业务代码
- `backend/requirements.txt`
- `frontend/` 下的前端页面或交互代码
- `deploy/` 下的部署模板
- Nginx、systemd、环境变量依赖的部署行为

如果只是本地测试、没有打算上线服务器，则不需要执行。

## 2. 更新前原则

每次服务器更新前，先遵守这几个原则：

1. 先在本地确认修改是可运行的，不要把未验证的代码直接推服务器。
2. 不要把 `.env`、密钥或本地缓存文件上传到仓库或发布包。
3. 更新前先备份服务器当前版本，至少保留一份可回滚副本。
4. 如果本次修改涉及数据库行为、定时任务或部署方式变化，先单独确认风险再上线。

## 3. 推荐更新策略

推荐默认使用“发布型更新”：

```text
本地修改
-> 本地验证
-> 本地打包
-> 上传服务器
-> 服务器解压
-> 替换正式目录
-> 安装依赖（如有需要）
-> 重启服务
-> 健康检查
```

这套流程更适合正式环境，原因是：

- 发布物清晰，可追溯
- 不容易把本地无关文件带上服务器
- 更容易做备份和回滚
- 更符合长期运维习惯

`rsync` 目录同步方式仍然保留，但只作为“快速更新补充方案”，不作为本文档主流程。

## 4. 更新前本地检查清单

在本地项目根目录 `D:\Axis` 先做检查：

```powershell
cd D:\Axis
```

建议最少确认：

```powershell
git diff --stat
```

如果本次改了后端，建议先跑相关测试，例如：

```powershell
cd D:\Axis\backend
D:\Axis\backend\.venv\Scripts\python.exe -m pytest tests\test_api.py -q
```

如果本次改了前端，建议至少执行：

```powershell
cd D:\Axis\frontend
npm run build
```

只有本地验证通过，再继续更新服务器。

## 5. 服务器更新前备份

登录服务器后，先备份当前后端目录。

```bash
ssh <server-user>@<server-host>
```

创建备份目录：

```bash
sudo mkdir -p /opt/axis/backups
```

按时间复制当前后端：

```bash
sudo cp -a /opt/axis/backend /opt/axis/backups/backend_$(date +%F_%H%M%S)
```

如果本次更新风险较大，建议顺手备份数据库：

### 本机 MySQL

```bash
mysqldump -u <MYSQL_USER> -p <MYSQL_DATABASE> > /opt/axis/backups/axis_$(date +%F_%H%M%S).sql
```

### RDS MySQL

```bash
mysqldump -h <MYSQL_HOST> -P 3306 -u <MYSQL_USER> -p <MYSQL_DATABASE> > /opt/axis/backups/axis_$(date +%F_%H%M%S).sql
```

## 6. 后端更新主流程

### 6.1 在本地打包后端发布包

在本地项目根目录执行：

```powershell
cd D:\Axis
Remove-Item -Recurse -Force .\release\axis-backend -ErrorAction SilentlyContinue
Remove-Item -Force .\release\axis-backend.zip -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force .\release\axis-backend | Out-Null
Copy-Item -Recurse .\backend\app .\release\axis-backend\app
Copy-Item .\backend\requirements.txt .\release\axis-backend\requirements.txt
Copy-Item .\backend\.env.example .\release\axis-backend\.env.example
Compress-Archive -Path .\release\axis-backend\* -DestinationPath .\release\axis-backend.zip -Force
```

生成的发布包：

```text
D:\Axis\release\axis-backend.zip
```

### 6.2 发布包中应该包含什么

建议后端发布包只包含：

```text
app/
requirements.txt
.env.example
```

不要打包这些内容：

```text
.env
.venv/
.pytest_cache/
__pycache__/
*.pyc
*.log
```

### 6.3 上传发布包到服务器

在本地执行：

```powershell
scp .\release\axis-backend.zip <server-user>@<server-host>:/tmp/axis-backend.zip
```

### 6.4 在服务器解压发布包

登录服务器：

```bash
ssh <server-user>@<server-host>
```

创建临时解压目录：

```bash
rm -rf /tmp/axis-backend-release
mkdir -p /tmp/axis-backend-release
unzip -o /tmp/axis-backend.zip -d /tmp/axis-backend-release
```

### 6.5 用发布包替换正式目录

把解压内容覆盖到正式目录：

```bash
sudo rsync -a --delete /tmp/axis-backend-release/ /opt/axis/backend/
sudo chown -R axis:axis /opt/axis/backend
```

注意：

- 正式环境的 `/opt/axis/backend/.env` 一般是服务器本地维护的
- 如果发布包里没有 `.env`，覆盖后不会影响现有 `.env`
- 不要把本地 `.env` 打进发布包

### 6.6 如有依赖变化，重新安装依赖

如果你改了 `backend/requirements.txt`，或者新增了后端依赖，执行：

```bash
cd /opt/axis/backend
sudo -u axis ./.venv/bin/pip install -r requirements.txt
```

如果本次没有改依赖，这一步可以跳过。

### 6.7 重启后端服务

```bash
sudo systemctl restart axis-backend
```

查看状态：

```bash
sudo systemctl status axis-backend
```

查看实时日志：

```bash
sudo journalctl -u axis-backend -f
```

### 6.8 验证后端是否正常

先做本机健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

应返回：

```json
{"status":"ok"}
```

如果服务器前面挂了 Nginx，再验证外部入口：

```bash
curl https://api.example.com/api/health
```

## 7. 前端更新流程

如果本次修改涉及前端页面，需要重新构建前端。

### 7.1 本地构建前端

```powershell
cd D:\Axis\frontend
npm run build
```

### 7.2 同步构建产物到前端部署位置

这一步取决于你的前端部署方式。

#### 方式 A：前端也在这台 Linux 服务器

例如前端静态目录是 `/var/www/axis-frontend`：

```bash
rsync -av --delete dist/ <server-user>@<server-host>:/tmp/axis-frontend-dist/
```

登录服务器：

```bash
sudo rsync -a --delete /tmp/axis-frontend-dist/ /var/www/axis-frontend/
```

#### 方式 B：前端部署在第三方平台

例如 Vercel、Netlify、静态对象存储：

- 重新上传构建产物
- 或重新触发该平台的构建发布

重点确认：

- `VITE_API_BASE_URL` 指向当前后端 API 域名
- 前端已拿到本次最新构建产物

## 8. 配置文件什么时候需要重载

如果你只改了业务代码，一般只需要：

```bash
sudo systemctl restart axis-backend
```

如果你改了下面这些内容，需要额外处理：

### 8.1 改了 `.env`

更新服务器上的 `/opt/axis/backend/.env` 后，必须重启后端：

```bash
sudo systemctl restart axis-backend
```

### 8.2 改了 `systemd` 服务文件

例如改了 `deploy/linux/axis-backend.service`，则需要：

```bash
sudo cp /tmp/axis-release/deploy/linux/axis-backend.service /etc/systemd/system/axis-backend.service
sudo systemctl daemon-reload
sudo systemctl restart axis-backend
```

### 8.3 改了 Nginx 配置

例如改了反向代理、域名、证书配置，则需要：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 9. 建议使用的标准更新顺序

这是最推荐的上线顺序：

1. 本地完成修改
2. 本地运行测试 / 构建
3. 服务器备份当前版本
4. 本地打包发布包
5. 上传发布包到服务器
6. 服务器备份当前版本
7. 服务器解压并替换正式目录
8. 如有需要，安装后端依赖
9. 重启后端服务
10. 健康检查和日志检查
11. 如有前端修改，再发布前端
12. 打开页面做人工验收

## 10. 人工验收建议

后端更新完成后，至少做以下检查：

- `/api/health` 正常
- 可以登录
- 关键页面能打开
- 市场雷达能加载
- K 线弹窗能打开
- 后台日志没有持续报错

如果本次改的是 K 线、信号、调度逻辑，额外检查：

- 数据采集状态页是否正常
- 补齐任务是否仍在推进
- 没有出现大量失败任务

## 11. 回滚流程

如果更新后发现问题，按下面方式回滚。

### 11.1 回滚代码目录

先停止后端：

```bash
sudo systemctl stop axis-backend
```

把最近一次备份恢复回来：

```bash
sudo rm -rf /opt/axis/backend
sudo cp -a /opt/axis/backups/<backup-dir-name> /opt/axis/backend
sudo chown -R axis:axis /opt/axis/backend
```

然后启动：

```bash
sudo systemctl start axis-backend
sudo systemctl status axis-backend
```

### 11.2 回滚数据库

如果本次更新影响了数据库行为，且需要回滚数据，再恢复备份：

```bash
mysql -u <MYSQL_USER> -p <MYSQL_DATABASE> < /opt/axis/backups/<backup-file>.sql
```

注意：

- 数据库回滚风险高
- 非必要不要直接覆盖生产数据
- 先确认影响范围再执行

## 12. 最小化停机建议

如果你希望停机时间更短，建议这样做：

- 先把文件同步到 `/tmp/axis-release`
- 依赖先准备好
- 真正切换时再执行一次 `rsync` 到正式目录
- 最后再 `restart`

这样可以把实际服务中断时间压到最短。

## 12.1 快速更新补充方案

如果你是自己频繁调试服务器，而不是正式发布，也可以使用目录同步方式快速更新：

```bash
rsync -av --delete \
  --exclude ".venv" \
  --exclude ".pytest_cache" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude ".env" \
  backend/ <server-user>@<server-host>:/tmp/axis-release/backend/
```

服务器端再执行：

```bash
sudo rsync -a --delete /tmp/axis-release/backend/ /opt/axis/backend/
sudo chown -R axis:axis /opt/axis/backend
sudo systemctl restart axis-backend
```

但这个方式只建议用于：

- 临时调试
- 个人测试环境
- 高频小改动快速验证

正式环境默认仍建议优先使用“本地打包 -> 上传发布包 -> 服务器解压部署”。

## 13. 常见问题

### 13.1 更新后服务启动失败

先看日志：

```bash
sudo journalctl -u axis-backend -n 200 --no-pager
```

常见原因：

- `.env` 配错
- Python 依赖没安装
- 新代码有语法错误
- MySQL 连接失败

### 13.2 页面白屏或接口 502

先判断是后端挂了，还是 Nginx 配置问题：

```bash
curl http://127.0.0.1:8000/api/health
sudo nginx -t
sudo journalctl -u axis-backend -f
```

### 13.3 前端改了但页面没变化

通常是下面几个原因：

- 没重新构建前端
- 构建产物没同步到服务器
- 浏览器缓存还在
- 部署平台没重新发布

### 13.4 改了依赖但服务器还是旧行为

确认是否执行过：

```bash
sudo -u axis ./.venv/bin/pip install -r requirements.txt
sudo systemctl restart axis-backend
```

## 14. 推荐长期做法

为了让以后每次更新更稳，建议固定形成下面这套习惯：

- 每次更新前先在本地跑最小验证
- 每次上线前先备份后端目录
- 高风险更新前额外备份数据库
- 后端上线后先看 `health` 和日志
- 每次上线都记一条更新记录，写清楚时间、内容、验证结果、风险和回滚点

如果后续频率更高，再考虑补一份：

- `docs/server-update-log.md`

专门记录每次服务器实际更新历史。
