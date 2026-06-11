# Axis Project Map

## 1. 项目功能简介

Axis / TrendAI 是一个加密货币量化信号发现系统。它提供用户注册登录、行情信号看板、AI 策略生成、Python 策略代码导入与校验、策略扫描运行、信号详情、观察列表、新币上市发现、知识案例和系统设置等功能。

核心业务围绕以下流程展开：

- 用户登录后进入仪表盘查看今日信号、启用策略、观察标的和最近策略运行情况。
- 在策略中心通过条件或 Python 代码生成策略，保存后可启用、暂停、编辑、删除和手动扫描。
- 后端扫描币种 K 线，执行策略代码，命中后生成信号并可推送通知。
- 新币模块定时抓取 Binance 公告，识别新上市或即将上市币种，并可通过 Pushover 推送。
- 设置模块保存 LLM 接口配置和 Pushover 通知配置，但 API 响应不会回传密钥明文。

## 2. 技术栈

### 前端

- React 19
- TypeScript 5
- Vite 6
- lucide-react 图标库
- 原生 CSS：`frontend/src/styles.css`
- Node 内置测试：`node --test`

### 后端

- Python 3.10+
- FastAPI
- Uvicorn
- Pydantic v2
- MySQL 存储
- httpx 调用 LLM 兼容接口
- pandas 支持 DataFrame 风格策略代码
- pytest + FastAPI TestClient 测试 API

### 部署

- Linux systemd 服务模板
- Nginx 反向代理模板
- MySQL 初始化 SQL
- 后端打包部署文档

## 3. 前后端结构

```text
D:\Axis
  backend/
    app/
      main.py              # FastAPI 应用入口、CORS、认证中间件、路由挂载、调度器生命周期
      models.py            # Pydantic 数据模型
      store.py             # 存储、行情、策略生成、策略执行、调度、通知、新币扫描等核心逻辑
      errors.py            # API 错误封装
      routers/
        auth.py            # 注册、登录
        dashboard.py       # 仪表盘摘要
        strategies.py      # 策略生成、保存、更新、运行、调度状态
        signals.py         # 信号列表与详情
        watchlist.py       # 观察列表
        new_coins.py       # 新币发现与扫描
        settings.py        # LLM 与 Pushover 设置
        knowledge.py       # 知识案例详情
    tests/
      test_api.py          # 后端 API 和 store 行为测试
    requirements.txt       # Python 依赖
    .env.example           # 后端环境变量示例

  frontend/
    src/
      main.tsx             # React 挂载入口
      App.tsx              # 顶层状态、视图切换、数据加载、业务动作编排
      api.ts               # 前端 API client 和 token 注入
      types.ts             # 前端 TypeScript 类型
      data-format.ts       # 日期、价格、百分比格式化
      code-editor.ts       # 策略代码编辑器辅助逻辑
      components/
        AppShell.tsx       # 应用框架和导航
        Charts.tsx         # Sparkline、K 线图
        Modal.tsx          # 弹窗
        StrengthGrade.tsx  # 信号强度展示
      pages/
        AuthPage.tsx       # 登录注册
        Dashboard.tsx      # 仪表盘
        Strategies.tsx     # 策略中心、策略编辑、策略生成、运行进度
        Signals.tsx        # 信号列表和筛选
        SignalDetail.tsx   # 信号详情
        Watchlist.tsx      # 观察列表
        WatchDetail.tsx    # 观察详情
        NewCoins.tsx       # 新币发现
        Settings.tsx       # 系统设置
        KnowledgeCase.tsx  # 知识案例
    package.json           # 前端脚本和依赖
    vite.config.ts         # Vite 配置和 /api 代理

  deploy/
    linux/
      init-server.sh       # Linux 服务器初始化
      axis-backend.service # systemd 服务模板
      nginx-axis.conf      # Nginx API 反向代理模板
      init-rds.sql         # 数据库初始化 SQL

  docs/
    backend-deployment.md  # 后端部署说明
    linux-deployment.md    # Linux 部署说明
    superpowers/           # 设计文档和实施计划
```

## 4. 核心模块说明

### 后端入口：`backend/app/main.py`

- 创建 FastAPI 应用。
- 启动和停止策略调度器、新币调度器。
- 配置 CORS，默认允许 `localhost` / `127.0.0.1` 的 5173、5174 端口。
- 注册全局 API 错误处理。
- 对 `/api/*` 接口做 Bearer token 校验；`/api/health` 和 `/api/auth/*` 不需要认证。
- 挂载 dashboard、auth、settings、new-coins、strategies、signals、watchlist、knowledge 路由。

### 数据模型：`backend/app/models.py`

定义所有请求和响应模型，包括：

- 策略：`Strategy`、`GeneratedStrategy`、`StrategyRuntime`、`StrategySchedule`
- 策略运行：`StrategyRunProgress`、`StrategyRunResult`、`StrategyScanHistory`
- 行情信号：`Candle`、`Signal`、`MarketKline`
- 新币发现：`NewCoinListing`、`NewCoinScanResult`
- 认证与设置：`AuthUser`、`AuthResponse`、`AppSettingsResponse`
- 观察列表和知识案例：`WatchItem`、`KnowledgeCase`

### 核心存储和业务：`backend/app/store.py`

这是后端最大、最核心的模块，职责包括：

- `MySQLStore`：MySQL 存储实现。
- 用户注册、密码哈希、登录 token 校验。
- 策略生成缓存、LLM 调用、fallback 策略生成。
- Python 策略代码校验和执行，支持普通 list/dict candle 和 pandas DataFrame 风格。
- Binance K 线抓取、移动均线计算、市场数据入库和保留策略。
- 策略手动运行、异步运行进度、取消、历史记录。
- 策略定时调度。
- Binance 新币公告抓取、解析、去重、状态归一化。
- Pushover 信号和新币通知。
- `.env` 文件加载，以及 MySQL store 创建。

### 后端路由：`backend/app/routers`

- `auth.py`：注册、登录，处理重复邮箱和无效凭据。
- `dashboard.py`：聚合今日信号、启用策略、观察列表、趋势数据等。
- `strategies.py`：策略列表、生成、代码导入、创建、更新、删除、运行、调度状态、启停。
- `signals.py`：信号列表和详情。
- `watchlist.py`：观察列表增查。
- `new_coins.py`：新币列表、手动扫描、调度状态。
- `settings.py`：读取和更新 LLM / Pushover 设置。
- `knowledge.py`：知识案例详情。

### 前端应用：`frontend/src/App.tsx`

- 管理登录状态，并把 token 存入 `localStorage` 的 `trendai.auth`。
- 登录后并行加载 dashboard、strategies、signals、newCoins、watchlist。
- 维护当前视图状态，项目没有使用 react-router。
- 统一处理策略生成、保存、更新、删除、扫描、新币扫描、观察列表创建等动作。

### 前端 API：`frontend/src/api.ts`

- 对所有 API 请求注入 Bearer token。
- 支持 `VITE_API_BASE_URL` 配置后端地址。
- 开发环境也可依赖 Vite `/api` proxy。
- 对策略返回值做 runtime、schedule、conditions、symbolBlacklist 的兼容归一化。

### 前端策略中心：`frontend/src/pages/Strategies.tsx`

功能密度最高的前端页面，包括：

- 策略列表、筛选、启停、定时开关。
- 条件模式生成策略。
- 粘贴 Python 代码生成策略说明。
- 策略详情编辑器。
- 策略运行进度面板和最近扫描历史。
- 代码编辑器错误行定位。
- 从结构化条件生成 Python 策略代码。

### 测试：`backend/tests/test_api.py`

覆盖范围包括：

- 健康检查、认证、授权保护。
- 设置保存且不泄露密钥。
- 新币扫描、去重和 Pushover 推送。
- 策略生成、缓存、代码导入。
- MySQL 持久化。
- MySQL reset 保护。
- 策略运行、进度、历史、取消。
- 策略编辑、删除、启停。
- 策略代码校验。
- 信号详情、观察列表、知识案例。

前端还有 `frontend/src/code-editor.test.mjs`，用于测试代码编辑器辅助函数。

## 5. 如何启动项目

### 启动后端

```powershell
cd D:\Axis\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```text
http://127.0.0.1:8000/api/health
```

后端使用 MySQL，可在 `backend/.env` 配置：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=axis
```

### 启动前端

```powershell
cd D:\Axis\frontend
npm install
npm run dev
```

默认访问：

```text
http://127.0.0.1:5173
```

开发环境下，`vite.config.ts` 会把 `/api` 代理到：

```text
http://127.0.0.1:8000
```

也可以通过 `frontend/.env` 设置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### 构建前端

```powershell
cd D:\Axis\frontend
npm run build
```

### 运行测试

后端：

```powershell
cd D:\Axis\backend
.\.venv\Scripts\python.exe -m pytest
```

前端代码编辑器测试：

```powershell
cd D:\Axis\frontend
npm run test:code-editor
```

## 6. 当前可能存在的问题

1. 多个源码和文档文件中的中文内容在当前读取环境里显示为乱码，例如 `models.py`、`App.tsx`、`test_api.py`、`docs/backend-deployment.md`。这可能是文件编码、终端解码或历史保存编码不一致导致，需要确认实际文件编码和浏览器显示是否正常。

2. `backend/app/store.py` 职责过重，单文件同时承担数据库、外部行情、LLM、策略执行、调度、通知和工具函数，后续维护和测试成本会越来越高。

3. 策略代码执行使用动态 Python 代码执行机制。虽然已有校验测试，但生产环境仍需重点关注隔离、超时、可访问内置对象、资源消耗和恶意代码风险。

4. Bearer token 持久保存在数据库中，前端保存在 `localStorage`。目前看不到 token 过期、刷新、撤销或多会话管理机制。

5. 前端没有使用正式路由库，所有视图切换依赖 `App.tsx` 内部状态。当前规模可行，但深链接、浏览器前进后退、页面刷新恢复具体详情页会受限。

6. 项目根目录和 `frontend/`、`backend/` 下存在较多运行日志、截图、缓存、虚拟环境、构建产物和 profile 目录。它们可能增加仓库噪音，需要确认 `.gitignore` 是否完整覆盖。

7. 部署文档部分内容同样出现乱码，可能影响交接和生产部署操作。

8. 后端启动时会自动启动策略调度器和新币调度器。如果多进程或多实例部署，可能出现重复扫描、重复写入或重复通知，需要生产部署时设计单实例调度或分布式锁。

9. `git status` 在当前环境因 dubious ownership 安全检查无法执行，需要配置 safe.directory 后才能正常查看工作区状态。

10. 前端和后端的部分类型字段存在手动镜像关系，例如 `frontend/src/types.ts` 与 `backend/app/models.py`。如果后端模型变更，前端类型需要同步维护。
