# 项目进度

## 当前任务
- 优化历史 K 线补齐吞吐：提高每轮补齐量，增量采集为历史补齐让路，减少任务空转刷新。

## 实施计划
- [x] 新增历史补齐任务模型和持久化表。
- [x] 新增 Binance range K 线拉取函数。
- [x] 新增限速历史补齐 scheduler。
- [x] 调整增量采集为每次只拉少量最新 K 线。
- [x] 将 1H 保留窗口调整为 90 天。
- [x] 策略扫描在历史补齐或增量采集中跳过。
- [x] 运行后端测试和前端构建验证。
- [x] 移除 K 线写入时的同步旧数据删除。
- [x] 新增每天一次的 K 线清理 scheduler。
- [x] 清理任务按批次删除旧 K 线，避免单次大删除。
- [x] 清理任务与采集、补齐、策略扫描互斥。
- [x] 新增市场雷达实现计划文档。
- [x] 新增市场雷达后端模型和 `GET /api/market/radar` 接口。
- [x] 基于数据库已有 1H K 线计算市场环境评分和推荐交易对。
- [x] 新增前端市场雷达页面、导航入口和刷新/加入观察操作。
- [x] 运行后端测试和前端构建验证。
- [x] 调整历史补齐任务排序，优先补齐主流币、观察池交易对和已有信号交易对。
- [x] 已存在的 pending/running 补齐任务无需重建，下一次 scheduler tick 自动按新优先级排序。
- [x] 将历史补齐单页数量从 500 提高到 1000。
- [x] 将每轮历史补齐任务数从 3 提高到 8。
- [x] 增量采集在存在未完成历史补齐任务时跳过，避免长期抢占补齐执行窗口。
- [x] 历史补齐不再每轮刷新全部任务，只刷新即将处理的一小批候选任务。

## 修改记录
- 已新增 `MarketKlineBackfillTask`，用于持久化每个交易对和周期的历史补齐进度。
- 已新增 `market_kline_backfill_tasks` 通用实体表，并实现任务读取、更新、K 线时间范围查询。
- 已新增 Binance range K 线拉取逻辑，历史补齐按 `startTime/endTime/limit` 分页拉取。
- 已新增历史补齐 scheduler：默认每 30 秒检查，每次最多处理 3 个交易对/周期组合，每组默认只拉 1 页，每页 500 根，避免首次补齐请求过大。
- 已调整增量采集 scheduler：只拉最新 5 根闭合 K 线，用于日常补最新数据。
- 已把 K 线保留窗口调整为：5M/15M 保留 30 天；1H/4H/1D 保留 90 天。
- 已让策略扫描在增量采集或历史补齐正在写入时跳过本次 tick，避免扫描读到半更新的数据。
- 已让历史补齐任务在数据库已覆盖保留窗口起点时从最新 K 线后继续；如果 completed 任务遇到新的周期边界，会自动恢复为 running 继续补缺口。
- 已在 FastAPI 生命周期中启动和停止历史补齐 scheduler。
- 已移除 `upsert_market_candles()` 中的同步旧 K 线清理，写入 K 线时不再触发全局 `DELETE`。
- 已新增 `delete_old_market_klines()`，按保留窗口和批次清理过期 K 线。
- 已新增 K 线清理 scheduler，默认每小时检查一次，当天未清理过时执行一次，因此实际每天最多运行一次。
- 已将 K 线清理与增量采集、历史补齐、策略扫描互斥，避免清理期间读写冲突。
- 已新增 `docs/superpowers/plans/2026-06-10-market-radar.md`，记录市场雷达实现计划。
- 已新增市场雷达 Pydantic 响应模型，包括市场环境、指标、机会分布和推荐交易对。
- 已新增 `store.market_radar()`，只读取数据库中已有 1H K 线，不实时请求 Binance。
- 已新增 `GET /api/market/radar`，前端可直接获取市场雷达结果。
- 已新增 `MarketRadar` 页面，展示市场评分、市场结论、推荐交易对、机会分布和重点观察卡片。
- 已在侧边栏新增“市场雷达”入口，推荐交易对可一键加入观察。
- 已新增补齐优先级排序：`BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT`、观察池和已有信号相关交易对优先。
- 已新增补齐优先级测试，覆盖主流币优先和信号币优先。
- 已提高历史补齐吞吐：每页 1000 根，每轮最多 8 个任务。
- 已让增量采集在未完成历史补齐存在时跳过，优先把历史补齐推进完。
- 已优化任务刷新逻辑，避免每次 tick 刷新全部 2655 个任务造成空转。

## 验证结果
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_kline_backfill" -q`，结果：3 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "kline_collection_scheduler_tick or market_kline_backfill_scheduler or market_kline_backfill_starts or market_kline_backfill_reopens or kline_retention_cutoffs or backfill_is_running" -q`，结果：6 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：62 passed。
- 已执行：`npm.cmd run build`，结果：通过。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "cleanup_scheduler or upsert_market_candles_does_not_prune or jobs_skip_while_cleanup" -q`，结果：5 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：66 passed。
- 已执行：`npm.cmd run build`，结果：通过。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_radar" -q`，结果：1 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：67 passed。
- 已执行：`npm.cmd run build`，结果：通过。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "backfill_prioritizes" -q`，结果：2 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_kline_backfill" -q`，结果：5 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：69 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_kline_backfill or kline_collection_scheduler_tick or backfill_tasks_are_unfinished" -q`，结果：7 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：70 passed。

## 下一步任务清单
- 观察正式环境首次补齐期间 Binance 请求频率和错误日志，必要时再调小每 tick 处理数量或页大小。
- 重启后端服务，让新的 K 线清理 scheduler 生效。
- 观察明天首次清理后的删除数量和执行耗时，必要时调整批次大小。
- 后续可增加 K 线采集状态页面，展示历史补齐进度、当前补齐交易对、失败任务和最近错误。
- 后续可增加失败任务的管理入口，例如手动重试某个交易对/周期。
- 后续可给市场雷达增加 K 线侧边详情，点击推荐交易对后直接查看多周期 K 线。
- 后续可接入 AI 总结，在确定性评分基础上生成更像人工复盘的市场解读。
- 后续可增加补齐状态页面，展示高优先级队列、剩余任务数和预计完成时间。
- 重启后端服务，让新的补齐吞吐和增量让路策略生效。

## 风险点
- 历史补齐会覆盖所有 Binance USDT 永续合约，需要限速，避免触发 Binance 限流。
- 策略扫描需要等待 K 线写入任务空闲，避免读写冲突。
- 当前没有新增后台管理 UI，历史补齐进度主要依赖数据库任务表和日志观察。
- K 线清理改为每天一次后，盘中不会频繁删除旧数据；如果历史旧数据很多，第一次独立清理仍可能需要多个批次才能完全清完。
- 市场雷达第一版基于 1H K 线确定性评分，不构成交易建议；短周期 5M/15M 联动和 AI 解读还未接入。
- 历史补齐加速后 Binance 请求量会提高，需要观察是否出现 429/418 或网络超时；如出现限流，再调低每轮任务数。

## 2026-06-11 历史 K 线补齐提速

### 当前任务
- 已按确认方案提高历史 K 线补齐吞吐，不引入并发 worker，不修改数据库结构，不修改路由。

### 实施计划
- [x] 新增补齐加速默认参数测试，先确认旧参数下失败。
- [x] 将历史补齐单页数量从 1000 提高到 1500。
- [x] 将每轮历史补齐任务数从 8 提高到 20。
- [x] 将每个任务每轮页数从 1 提高到 2。
- [x] 将补齐请求间隔从 0.2 秒降为 0。
- [x] 将历史补齐 scheduler 默认检查间隔从 30 秒降为 10 秒。
- [x] 运行针对性测试和完整后端测试。

### 修改记录
- 修改 `backend/app/store.py`：调整 `BACKFILL_PAGE_LIMIT`、`BACKFILL_MAX_PAIRS_PER_TICK`、`BACKFILL_MAX_PAGES_PER_PAIR`、`BACKFILL_REQUEST_SLEEP_SECONDS` 和 `start_market_kline_backfill_scheduler()` 默认间隔。
- 修改 `backend/tests/test_api.py`：新增 `test_market_kline_backfill_uses_accelerated_defaults()`，锁定正式加速参数，避免后续误改回保守值。

### 验证结果
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "accelerated_defaults" -q`，旧代码下按预期失败：`BACKFILL_PAGE_LIMIT` 仍为 1000。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "accelerated_defaults or market_kline_backfill_scheduler_advances_limited_tasks" -q`，结果：2 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_kline_backfill or kline_collection_scheduler_tick or backfill_tasks_are_unfinished" -q`，结果：8 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：71 passed。

### 下一步任务清单
- 重启后端服务，让新的补齐吞吐参数生效。
- 观察补齐任务表中的 completed 数量、pagesFetched、storedCandles 是否明显加速。
- 观察后端日志是否出现 Binance 429/418、网络超时或 MySQL 写入变慢。
- 如果 MySQL 压力可控但补齐仍不够快，再评估并发 worker 池；该方案属于后台任务逻辑升级，需要单独确认。

### 风险点
- 请求量会明显提高，即使 Binance 不限流，MySQL upsert、连接池和磁盘写入也可能成为瓶颈。
- 补齐期间策略扫描仍会等待 K 线写入窗口，补齐变快后单轮运行时间也可能变长，需要观察扫描延迟。
- 新参数需要后端重启后才会在常驻 scheduler 中生效。

## 2026-06-11 增量采集按补齐任务粒度接管

### 当前任务
- 已将 K 线增量采集从“全局等待所有历史补齐完成”调整为“按交易对/周期判断是否可采集”。

### 实施计划
- [x] 新增测试覆盖已完成补齐组合可被增量采集、未完成组合继续跳过。
- [x] 移除增量采集中的全局 `backfill_pending` 跳过逻辑。
- [x] 为增量采集构建 `symbol + period` 补齐状态映射。
- [x] 增量采集只跳过 `pending`、`running`、`failed` 的交易对/周期；`completed` 或无任务记录的组合允许采集。
- [x] 保留清理中和正在补齐中的互斥保护，避免同一时间写入冲突。
- [x] 补全测试夹具中的采集边界状态重置，避免测试顺序污染。

### 修改记录
- 修改 `backend/app/store.py`：`run_market_kline_collection_scheduler_tick()` 改为按交易对/周期跳过未完成补齐组合，并返回 `skippedPairs`。
- 修改 `backend/tests/test_api.py`：新增/调整增量采集测试，验证已完成补齐组合可以继续追最新 K 线；重置 `lastCollectedBoundaries` 测试状态。

### 验证结果
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "collection_collects_completed_pairs" -q`，旧代码下按预期失败，修改后通过：1 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_kline_backfill or kline_collection_scheduler_tick or collection_collects_completed_pairs or jobs_skip_while_cleanup" -q`，结果：9 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：71 passed。

### 下一步任务清单
- 重启后端服务，让新的增量采集接管策略生效。
- 观察日志和任务表，确认已 completed 的交易对/周期能持续更新最新 K 线。
- 观察 `skippedPairs` 数量是否随历史补齐完成而下降。
- 后续可增加 K 线采集状态页面，直接展示 completed、running、pending、skippedPairs 和最新更新时间。

### 风险点
- 增量采集会随着 completed 组合增多逐步恢复请求量，需要观察 Binance 请求频率和 MySQL 写入压力。
- 若某个组合处于 failed 状态，当前仍由历史补齐任务负责重试/恢复，增量采集不会绕过 failed 直接追新。
- 新逻辑需要后端重启后才会在常驻 scheduler 中生效。

## 2026-06-11 数据采集状态页面

### 当前任务
- 已实现“数据采集”页面，把 K 线历史补齐、增量更新、数据清理表现为三个后台任务卡，并展示进度、覆盖范围、当前运行任务、最近记录和风险提示。

### 实施计划
- [x] 新增后端 K 线采集状态响应模型。
- [x] 新增 `GET /api/market/kline-status` 只读接口。
- [x] 聚合历史补齐任务总览、各周期进度、运行中任务、最近任务记录、K 线覆盖范围、增量采集状态和清理状态。
- [x] 增量采集 scheduler 状态新增最近一轮 `skippedPairs`，用于页面展示。
- [x] 新增前端 `数据采集` 页面，包含三张任务卡、覆盖表、补齐进度表、当前任务表、最近记录和异常风险。
- [x] 接入侧边栏入口、API 类型、自动刷新开关和手动刷新。
- [x] 运行后端测试和前端构建验证。

### 修改记录
- 修改 `backend/app/models.py`：新增数据采集状态相关 Pydantic 模型。
- 修改 `backend/app/store.py`：新增 `market_kline_status()` 聚合方法和相关辅助函数；记录增量采集最近跳过组合数。
- 修改 `backend/app/routers/market.py`：新增 `/api/market/kline-status` 接口。
- 修改 `backend/tests/test_api.py`：新增接口聚合测试，并补充采集状态重置。
- 修改 `frontend/src/types.ts`、`frontend/src/api.ts`：新增数据采集状态类型和 API 方法。
- 修改 `frontend/src/App.tsx`、`frontend/src/components/AppShell.tsx`：接入页面、导航入口、自动刷新和手动刷新。
- 新增 `frontend/src/pages/MarketDataStatus.tsx`：实现页面主体。
- 修改 `frontend/src/styles.css`：新增数据采集页面样式。

### 验证结果
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "kline_status_summarizes" -q`，结果：1 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "kline_status_summarizes or market_kline_backfill or kline_collection_scheduler_tick or collection_collects_completed_pairs" -q`，结果：9 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：72 passed。
- 已执行：`npm.cmd run build`，结果：通过。
- 未启动额外后端做浏览器实测：该页面依赖真实登录态和实时后端 API，为避免误连/操作真实环境，本次以自动化测试和生产构建验证为准。

### 下一步任务清单
- 重启后端和前端服务后，在侧边栏进入“数据采集”查看真实状态。
- 观察任务卡中历史补齐进度、增量更新跳过数量、清理任务日期是否符合预期。
- 后续可增加失败任务筛选和手动重试入口；该操作会涉及后台任务控制，需要单独确认。

### 风险点
- 页面会每 10 秒自动刷新一次，访问人数多时会增加后端只读查询压力；必要时可默认关闭自动刷新。
- 当前接口是只读观测，不提供暂停、恢复、重试等控制能力。
- 历史补齐任务非常多，页面只展示当前运行和最近记录，详细全量任务列表后续可按需分页增加。
## 2026-06-11 首页初始化卡住修复
### 当前任务
- 已定位首页一直显示“正在加载数据...”的原因：全局首页初始化中加入了市场雷达和数据采集状态接口，其中 `/api/market/kline-status` 会聚合 K 线大表，接口变慢时会阻塞整个首页首屏。
### 实施计划
- [x] 增加前端回归测试，锁定首页初始化不能请求重型市场页面接口。
- [x] 从 `loadInitialData()` 中移除 `api.marketRadar()` 和 `api.marketKlineStatus()`。
- [x] 改为进入“市场雷达”页面时懒加载市场雷达数据。
- [x] 改为进入“数据采集”页面时懒加载数据采集状态，并保留该页面内自动刷新。
- [x] 运行前端回归测试和生产构建验证。
### 修改记录
- 新增 `frontend/src/app-initial-load.test.mjs`：防止重型市场接口再次进入首页初始化链路。
- 修改 `frontend/src/App.tsx`：首页首屏只加载 dashboard、策略、信号、新币和观察池；市场雷达与数据采集状态按页面懒加载。
### 验证结果
- 已执行：`node --test src/app-initial-load.test.mjs`，旧逻辑下失败，修复后通过：1 passed。
- 已执行：`npm.cmd run build`，结果：通过。
### 下一步任务清单
- 重载前端页面，确认首页不再停留在“正在加载数据...”。
- 进入“数据采集”页面后观察 `/api/market/kline-status` 耗时；如果仍明显慢，再优化后端聚合 SQL 或做状态快照缓存。
### 风险点
- 本次修复只解决首页被重型接口阻塞的问题；数据采集页面自身如果接口聚合慢，仍可能加载较久。
- 市场雷达和数据采集状态改为懒加载后，首次进入对应页面才会请求数据，这是预期行为。
## 2026-06-11 K线数据当前数量查询
### 当前任务
- 已按周期只读查询 `market_klines` 当前数据量。
### 查询结果
- 5M：1,743,822 行，531 个交易对，时间范围 2026-05-12T00:30:00+00:00 至 2026-06-11T03:55:00+00:00。
- 15M：643,493 行，531 个交易对，时间范围 2026-05-12T01:15:00+00:00 至 2026-06-11T03:45:00+00:00。
- 1H：537,092 行，531 个交易对，时间范围 2026-03-13T02:00:00+00:00 至 2026-06-11T03:00:00+00:00。
- 4H：165,615 行，531 个交易对，时间范围 2026-03-13T04:00:00+00:00 至 2026-06-11T00:00:00+00:00。
- 1D：18,051 行，531 个交易对，时间范围 2026-03-14T00:00:00+00:00 至 2026-06-10T00:00:00+00:00。
### 验证结果
- 已执行只读 SQL 聚合查询，耗时约 24.5 秒。
### 风险点
- 当前聚合查询需要扫描 K 线大表，已经能明显感知慢查询，应后续改为状态快照或缓存。
## 2026-06-11 K线存储改为5M基础数据与派生缓存
### 当前任务
- 已按确认方案将 K 线采集调整为“5M 原生基础数据 + 15M/1H/4H 派生缓存 + 1D 原生长期数据”。
### 实施计划
- [x] 增加测试，锁定补齐任务只创建 5M 和 1D 原生周期。
- [x] 增加测试，锁定增量采集只请求 Binance 的 5M 和 1D。
- [x] 增加测试，验证 5M 写入后自动生成 15M、1H、4H 派生缓存。
- [x] 调整 K 线保留窗口：5M/15M/1H/4H 保留 30 天，1D 保留 365 天。
- [x] 保持前端 K 线接口不变，策略扫描继续按周期读取缓存。
### 修改记录
- 修改 `backend/app/store.py`：新增 `MARKET_KLINE_NATIVE_PERIODS` 和 `MARKET_KLINE_DERIVED_PERIODS`，保留展示周期 `MARKET_KLINE_COLLECTION_PERIODS`。
- 修改 `backend/app/store.py`：`upsert_market_candles()` 在写入 5M 后刷新受影响时间窗口内的 15M、1H、4H 聚合缓存。
- 修改 `backend/app/store.py`：历史补齐和增量采集改为只处理 5M、1D 原生周期，不再直接请求 Binance 的 15M、1H、4H。
- 修改 `backend/app/store.py`：新增 `_floor_datetime_to_period()` 和 `_aggregate_market_candles()`，按完整 5M 桶生成派生 K 线。
- 修改 `backend/tests/test_api.py`：更新 K 线补齐、增量、清理和派生缓存相关测试。
### 验证结果
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "kline_collection_scheduler_tick_fetches_native or upserting_5m_candles_refreshes or retention_uses_short or backfill_scheduler_advances_limited or backfill_prioritizes" -q`，结果：6 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_kline_backfill or kline_collection_scheduler_tick or collection_collects_completed_pairs or cleanup_scheduler or kline_status_summarizes or market_klines_endpoint or market_radar" -q`，结果：14 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，首次出现异步扫描历史等待抖动，单独重跑通过；再次完整重跑结果：74 passed。
- 已执行：`npm.cmd run build`，结果：通过。
### 下一步任务清单
- 重启后端服务，让新的采集周期和派生缓存逻辑生效。
- 观察后端日志，确认增量采集只请求 5M 和 1D，15M/1H/4H 由 5M 写入后生成。
- 后续如需降低 `/api/market/kline-status` 耗时，继续做状态快照或缓存，而不是每次全表聚合。
### 风险点
- 旧数据库里已有 15M/1H/4H 历史数据不会立即删除，会由每天清理任务按 30 天窗口逐步清理。
- 派生缓存只生成完整桶；当前未闭合的 15M/1H/4H K 线不会提前写入，这是为了避免策略扫描读到半根 K 线。
- 4H 派生缓存依赖对应 4 小时窗口内完整 48 根 5M 数据；补齐初期如果 5M 缺口未补齐，4H 会暂时少于预期。

## 2026-06-11 数据采集页面适配原生与派生周期
### 当前任务
- 已按新的 K 线存储方案调整前端“数据采集”页面展示，让页面明确区分 5M/1D 原生采集和 15M/1H/4H 派生缓存。
### 实施计划
- [x] 分析数据采集页面现有布局，保持原有任务卡、覆盖表、补齐表和风险面板结构不变。
- [x] 在 K 线覆盖表增加周期来源展示。
- [x] 在历史补齐进度表中标明派生周期不属于独立补齐任务。
- [x] 增加页面说明和风险提示，说明派生周期由 5M 完整桶生成。
- [x] 运行前端生产构建验证。
### 修改记录
- 修改 `frontend/src/pages/MarketDataStatus.tsx`：增加原生/派生周期判断，覆盖表新增“来源”列，补齐表对派生周期显示“随 5M 生成”，并补充固定风险说明。
- 修改 `frontend/src/styles.css`：新增数据说明条、来源徽标和派生进度文本样式。
### 验证结果
- 已执行：`npm.cmd run build`，结果：通过。
### 下一步任务清单
- 重载前端后进入“数据采集”页面，确认 5M/1D 显示为“原生采集”，15M/1H/4H 显示为“派生缓存”。
- 观察真实接口返回中派生周期覆盖行数是否随 5M 写入继续刷新。
- 如果 `/api/market/kline-status` 仍加载较慢，下一步应做后端状态快照或缓存，避免每次全表聚合。
### 风险点
- 本次只调整前端展示语义，不改变接口性能；数据采集页面如果接口慢，加载时间仍取决于后端聚合查询。
- 派生周期展示依赖前端固定周期规则；如果后续后端新增新的原生周期，需要同步更新前端周期来源判断。

## 2026-06-11 K线状态接口改为持久化快照
### 当前任务
- 已定位 `/api/market/kline-status` 慢的根因是覆盖统计实时扫描 `market_klines` 大表；已改为读取持久化覆盖快照，避免页面请求阻塞。
### 实施计划
- [x] 增加失败测试，锁定状态接口必须读取快照，不能依赖实时全表聚合。
- [x] 增加失败测试，锁定 K 线写入后会维护覆盖快照。
- [x] 新增 K 线覆盖快照持久化表。
- [x] K 线写入时轻量增量更新快照；清理删除旧数据后按周期校准快照。
- [x] 新增低频后台快照刷新任务，每次只刷新一个缺失周期，用于现有历史数据首次生成快照。
- [x] 状态接口只读快照；缺失周期显示“暂无快照”，不再同步扫描大表。
- [x] 修正覆盖窗口文案：5M/15M/1H/4H 为 30 天，1D 为 365 天。
### 修改记录
- 修改 `backend/app/store.py`：新增 `market_kline_coverage_snapshots` 表、快照读写方法、周期级刷新方法和覆盖快照后台 scheduler。
- 修改 `backend/app/store.py`：`upsert_market_candles()` 写入后按新增 K 线数量、交易对数量和时间范围轻量维护快照。
- 修改 `backend/app/store.py`：`delete_old_market_klines()` 在删除旧数据后刷新受影响周期快照。
- 修改 `backend/app/store.py`：`_market_kline_coverage()` 改为读取快照，不再执行 `GROUP BY period` 全表聚合。
- 修改 `backend/app/main.py`：FastAPI 生命周期中启动和停止 K 线覆盖快照后台任务。
- 修改 `backend/tests/test_api.py`：新增覆盖快照、写入维护快照、后台刷新缺失快照测试。
### 验证结果
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "coverage_snapshot or refreshes_coverage_snapshot" -q`，结果：3 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "kline_status_summarizes or market_kline_backfill or kline_collection_scheduler_tick or collection_collects_completed_pairs or cleanup_scheduler or coverage_snapshot" -q`，结果：15 passed。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：77 passed。
### 下一步任务清单
- 重启后端服务，让新表、索引和覆盖快照后台任务生效。
- 首次启动会创建 `market_kline_coverage_snapshots` 表和 K 线周期索引；如果现有 K 线表很大，创建索引可能需要一段时间。
- 进入“数据采集”页面后，初始可能有周期显示“暂无快照”；后台任务会每次补一个缺失周期，后续页面刷新会逐步显示真实覆盖数据。
- 观察 `/api/market/kline-status` 响应耗时，应从全表聚合级别降为读取快照级别。
### 风险点
- 首次创建 `period/open_time`、`period/symbol` 索引会对大表产生一次性数据库压力，建议在低峰期重启或执行。
- 快照是观测数据，不影响策略扫描和 K 线读取；如果快照缺失，只影响状态页展示，不影响真实 K 线数据。
- 写入时快照按新增 id 增量维护；如果外部绕过应用直接修改 `market_klines`，需要等待后台刷新或清理校准后快照才会一致。
