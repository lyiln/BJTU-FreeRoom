# BJTU Room Finder Current State

## Scope
- 当前文档覆盖：代码库功能边界、前后端入口、搜索/同步数据流、数据库读写、外部依赖、2026-09-08 修复的错误教学周同步问题、2026-09-22 增加的定时退出和按成功日期自动同步行为，以及 2026-10-09 增加的按页面打开时间设置默认日期和节次。
- 本次运行时检查没有输出账号内容；已使用现有系统凭据执行线上同步，并通过 SQLite 聚合统计和搜索结果验证。

## Latest Confirmed Change (2026-10-09)
- `static/app.js:PERIOD_SCHEDULE` 定义普通楼栋的 1–7 节时间：08:00–09:50、10:10–12:00、12:10–14:00、14:10–16:00、16:20–18:10、19:00–20:50、21:00–21:50。时间来自用户提供的课表截图，不通过教务同步动态更新。
- `getDefaultSearchSelection(now)` 使用传入时间的本地日期和时分，选择当天尚未结束的第一节；到达下课时间即推进到下一节，21:50 起通过 `setDate()` 选择次日第一节，不跳过周末，不修改传入的时间对象。
- `init()` 只读取一次浏览器本机时间，并把日期和起止节次设置为计算结果；例如 2026-10-09 16:07 为当天第 5 节到第 5 节。打开或刷新页面仍只加载状态、楼栋和偏好，不自动搜索；初始化后没有时间驱动的默认值更新。
- 用户确认 YF 第二节实际为 10:30–12:20，本次统一使用普通楼栋时间，选择 YF 也不重新匹配；12:00–12:20 默认第三节，查询 YF 第二节需要手动选择。后端 API、数据库和同步流程未改动。
- `tests/test_frontend.py` 使用真实 Chromium 加载本地 HTML/JS，并拦截 API 为固定响应；覆盖全部 7 个下课边界的前一秒/准确时刻、课前/课中/课间、月末/年末/闰日、周末跨日、手动选择、日期快捷入口、刷新重新匹配及查询参数。浏览器时区固定为 Asia/Shanghai，时钟由测试控制。
- 2026-10-09 浏览器验收：35 项前端测试通过；16:07 查询请求使用 `date=2026-10-09&start_period=5&end_period=5`，21:50 刷新后选择次日第 1 节，手动值在时间推进后保留。此验收使用隔离的本地页面和固定 API 响应，未调用线上教务同步或验证当前运行服务的数据。
- 最终回归：`.venv/bin/pytest -q` 共 64 项测试通过，`git diff --check` 通过。此次只修改静态前端和测试/说明文档，无后端 Python 变更，无需因本次改动重启服务；已打开页面需要刷新以加载新默认逻辑。
- 前端回归测试需要先安装 Playwright Chromium（README 的启动步骤已包含 `uv run playwright install chromium`）；无需新增 Python 依赖。在 macOS 的受限执行沙箱中，Chromium 启动可能需要沙箱外执行权限。

## Previous Confirmed Change (2026-09-22)
- `bjtu-rooms` 默认在进程启动 30 分钟后请求 Uvicorn 优雅退出；`--shutdown-after-minutes` 可覆盖时长，值为 `0` 时禁用。自动退出只停止本地服务，不关闭浏览器标签。
- CLI 通过可控的 `uvicorn.Server` 实例和异步计时任务实现退出；服务提前停止时会取消计时任务，到期时设置 `server.should_exit`，由 Uvicorn 停止接收新请求并等待在途请求。
- `create_app(shutdown_at=...)` 把带时区的预计退出时间注入应用；`GET /api/status` 通过 `runtime.shutdown_at` 返回 ISO 8601 时间或 `null`，前端状态区将其格式化为本地时分。
- 启动生命周期只读取一次本机日期，并以 `sync_state.last_sync_date` 判断当天是否已经成功同步；后台启动同步任务会被保留引用，应用退出时等待其结束。
- 同步失败仍更新最近尝试时间、错误状态和消息，但不再清除已有的最近成功同步日期；没有任何成功记录时失败日期仍为 `null`。数据库 schema 未变化。
- 回归覆盖：`tests/test_cli.py` 覆盖参数与计时任务，`tests/test_app.py` 覆盖同步判断、生命周期等待和状态 API，`tests/test_storage.py` 覆盖失败时保留成功日期。
- 2026-09-22 最终运行验收：重启服务后 `GET /api/status` 返回当天成功同步状态、319 间教室和带 `+08:00` 偏移的 `runtime.shutdown_at`；因当天已有成功记录，本次启动没有重复同步。

## Previous Confirmed Change (2026-09-08)
- 观察到 `sync_state` 记录当天同步成功（319 间教室、120 条占用），但 `occupancies` 表为 0 条；设置中没有 `week_number` 或 `semester_start`。
- 根因：`bjtu_rooms/sync.py` 在缺少教学周配置时固定请求 `zc=18`，解析出的旧周占用随后被当前周/下周保留窗口全部清理，导致搜索把全部教室误判为空闲。
- 修复：没有显式或可推导教学周时，先请求教室页并从重定向 URL 解析服务器当前周，再以 `zc=<当前周>&perpage=500` 请求完整教室列表；有配置时仍保留原有显式周行为。
- 防护：`_validate_occupancy_week()` 在写库前验证所有非空占用数据均属于目标周；出现错周或混周时同步报错且不覆盖现有占用数据。
- 实测：第一次仅省略 `zc` 的方案被服务器重定向为当前周但丢失 `perpage=500`，只能读到 20 间；两步请求修复后在 2026-09-08 读到 319 间教室和 5714 条 2026-09-07 至 2026-09-13 的占用记录。
- 2026-09-11 最终运行验收：重启服务后自动同步读到 319 间教室和 5893 条当周占用记录；`GET /api/search?date=2026-09-11&start_period=1&end_period=2` 返回 114 间空教室及逐节状态。
- 回归覆盖：`tests/test_sync.py` 覆盖服务器周次解析、完整列表 URL、由学期开始日推导周次、错周拒绝和目标周接受。

## Files Read
| File | Why Read | Key Evidence |
|---|---|---|
| `AGENTS.md` | 确认后续 AI 对话的任务前/任务后同步 hook | 任务前读取本文档；任务后如改变代码、测试、行为、API、数据流、数据库逻辑、依赖、命令或运维假设，需要更新本文档。 |
| `README.md` | 理解项目目标、启动方式、同步说明 | 项目是本地 BJTU 空教室查询工具；默认访问 `http://127.0.0.1:8000`；开发命令包含 `uv run pytest` 和 `uv run uvicorn bjtu_rooms.app:create_app --factory --reload`。 |
| `pyproject.toml` | 确认技术栈、入口脚本、测试配置 | 依赖 FastAPI、Playwright、BeautifulSoup、keyring、uvicorn；脚本 `bjtu-rooms = "bjtu_rooms.cli:main"`；pytest 读取 `tests`。 |
| `bjtu_rooms/cli.py` | 确认命令行启动路径 | `main()` 创建应用、`uvicorn.Server` 和可选退出计时任务，默认会打开浏览器并在 30 分钟后优雅退出。 |
| `bjtu_rooms/app.py` | 确认 HTTP API、静态文件、应用生命周期 | 定义 `/api/status`、`/api/buildings`、`/api/search`、`/api/preferences`、`/api/credentials`、`/api/sync`；启动时可能异步同步。 |
| `bjtu_rooms/models.py` | 确认核心数据类型 | 定义 `Room`、`Occupancy`、`Preference`、`PeriodStatus`、`SearchResult`、`SyncState`；`MAX_PERIOD = 7`。 |
| `bjtu_rooms/core.py` | 确认搜索、排序、节次状态逻辑 | `search_empty_rooms()` 过滤已占用教室并生成 `period_statuses`；按偏好分、连续空闲、楼栋和自然教室号排序。 |
| `bjtu_rooms/storage.py` | 确认 SQLite schema、读写路径、占用记录保留策略 | 数据库为 `data/rooms.sqlite3`；表包括 `rooms`、`occupancies`、`preferences`、`sync_state`；`occupancy_retention_window()` 只保留本周和下周；`upsert_rooms_and_occupancies()` 会按教室/日期/节次范围去重。 |
| `bjtu_rooms/sync.py` | 确认同步和 Playwright 抓取流程 | `sync_today()` 调用 `fetch_classroom_data()`，解析后写入数据库、清理保留窗口外占用记录，并保存同步状态。 |
| `tests/test_sync.py` | 确认同步周选择和错周保护 | 覆盖服务器周次解析、完整列表 URL、配置学期开始日时计算周次，以及占用日期周验证。 |
| `bjtu_rooms/parser.py` | 确认 HTML 解析策略 | 支持 JSON-like payload、BJTU 周视图表格、通用表格、文本兜底；白色背景视为空闲。 |
| `bjtu_rooms/credentials.py` | 确认账号密码存储 | 用户名写入 settings；密码通过 `keyring` 存取，service name 为 `bjtu-room-finder`。 |
| `static/index.html` | 确认页面结构、日期快捷入口和结果表列 | 日期输入旁有“今天”“明天”快捷按钮；同步按钮文案为“同步本周数据”；结果表当前列为教室、楼栋、今日状态、连续空闲、偏好。 |
| `static/app.js` | 确认前端状态、fetch、日期切换、渲染逻辑 | 初始化读取状态/楼栋/偏好；搜索调用 `/api/search`；状态区将 `runtime.shutdown_at` 转为本地时分；“今天”“明天”按钮分别设置本地今天/次日日期，已查询后会自动重查；`renderPeriodStatuses()` 渲染 1-7 节状态点。 |
| `tests/test_cli.py` | 确认 CLI 参数和自动退出计时任务 | 覆盖默认 30 分钟、自定义时长、`0` 禁用、负数拒绝、到期请求退出及提前停止时取消计时任务。 |
| `tests/test_app.py` | 确认启动同步和状态 API | 覆盖按最近成功日期判断同步、生命周期等待后台同步，以及 `runtime.shutdown_at` 有值/禁用两种响应。 |
| `tests/test_core.py` | 确认核心行为测试 | 覆盖搜索排序、占用排除、`period_statuses` 生成和 `asdict()` 序列化结构。 |
| `tests/test_storage.py` | 确认存储行为测试 | 覆盖占用记录入库去重、只保留本周和下周记录的清理窗口，以及同步失败时保留最近成功日期。 |

## Confirmed Facts
| Fact | Evidence | Source Type | Confidence |
|---|---|---|---|
| 项目是本地 BJTU 空教室查询工具。 | `README.md` 标题和说明。 | Project Docs | Confirmed |
| 项目级 AI hook 已在 `AGENTS.md` 中定义。 | `AGENTS.md` 要求任务前读取 `docs/architecture/current-state.md`，任务后按影响范围更新该文档。 | Project Docs | Confirmed |
| Web 服务由 FastAPI 提供，静态页面在 `static/`。 | `bjtu_rooms/app.py:create_app()` 挂载 `StaticFiles(directory=STATIC_DIR)` 并返回 `static/index.html`。 | Source Code | Confirmed |
| 默认 CLI 运行不会热重载 Python 代码。 | `bjtu_rooms/cli.py:main()` 创建 `uvicorn.Config(..., reload=False)` 和 `uvicorn.Server`。 | Source Code | Confirmed |
| 默认 CLI 会在启动 30 分钟后优雅退出。 | `bjtu_rooms/cli.py:DEFAULT_SHUTDOWN_AFTER_MINUTES`、`_request_shutdown_after()`、`_serve_with_shutdown()`；`tests/test_cli.py`。 | Source Code / Test Code | Confirmed |
| 自动退出可通过 CLI 覆盖或禁用。 | `--shutdown-after-minutes` 接受非负整数，`0` 不创建计时任务。 | Source Code / Test Code | Confirmed |
| 搜索接口是 `GET /api/search`，参数包括 `date`、`start_period`、`end_period`、可选 `building`。 | `bjtu_rooms/app.py:search()`。 | Source Code | Confirmed |
| 搜索结果后端包含 `period_statuses` 字段。 | `bjtu_rooms/models.py:SearchResult.period_statuses`；`bjtu_rooms/core.py:search_empty_rooms()` 填充该字段。 | Source Code | Confirmed |
| 前端当前不展示“可空到”列。 | `static/index.html` 的表头只有教室、楼栋、今日状态、连续空闲、偏好；`static/app.js:renderResults()` 不渲染 `free_until_period`。 | Source Code | Confirmed |
| 前端提供“今天”“明天”快捷日期入口。 | `static/index.html` 定义 `todayButton` / `tomorrowButton`；`static/app.js:setDateFromToday()` 设置日期并在已有搜索后自动重查。 | Source Code | Confirmed |
| 同步 UI 明确表达为同步本周数据。 | `static/index.html` 的同步按钮文本为“同步本周数据”；`static/app.js` 的同步 toast 为“开始同步本周教室数据...”。 | Source Code | Confirmed |
| 前端遇到缺失 `period_statuses` 会显示“暂无状态”，不会再直接 `.map` 崩溃。 | `static/app.js:renderPeriodStatuses()` 先检查 `Array.isArray(statuses)`。 | Source Code | Confirmed |
| SQLite 数据库路径是 `data/rooms.sqlite3`。 | `bjtu_rooms/storage.py:DB_PATH = DATA_DIR / "rooms.sqlite3"`。 | Source Code | Confirmed |
| 同步状态保存在 `sync_state` 表，偏好保存在 `preferences` 表。 | `bjtu_rooms/storage.py:init_db()` 建表 SQL。 | Database Schema | Confirmed |
| `last_sync_date` 表示最近成功同步日期，失败不会清空它。 | `storage.save_sync_state()` 使用 `coalesce` 保留成功日期；`tests/test_storage.py`。 | Source Code / Test Code | Confirmed |
| 占用记录会按本周一到下周日保留。 | `bjtu_rooms/storage.py:occupancy_retention_window()`；`tests/test_storage.py:test_prune_occupancies_keeps_current_and_next_week()`。 | Source Code / Test Code | Confirmed |
| 启动和同步成功后会清理保留窗口外的占用记录。 | `bjtu_rooms/app.py:lifespan()` 调用 `prune_occupancies_outside_retention_window()`；`bjtu_rooms/sync.py:sync_today()` 同步成功后调用同一函数。 | Source Code | Confirmed |
| 重复占用输入不会重复入库。 | `bjtu_rooms/storage.py:upsert_rooms_and_occupancies()` 使用 `inserted_keys` 跳过同一教室/日期/节次范围的重复项；`tests/test_storage.py:test_upsert_deduplicates_occupancies()`。 | Source Code / Test Code | Confirmed |
| 账号用户名存入 settings，密码存入系统 keyring。 | `bjtu_rooms/credentials.py:get_username()`、`save_username()`、`save_password()`。 | Source Code | Confirmed |
| 教务同步依赖 Playwright 打开 BJTU 教务系统并解析课堂占用 HTML。 | `bjtu_rooms/sync.py:fetch_classroom_data()` 使用 `async_playwright()`；`parse_classroom_html()` 处理 HTML。 | Source Code | Confirmed |
| 未配置 `week_number` / `semester_start` 时不再固定请求第 18 周。 | `fetch_classroom_data()` 先请求默认教室页，`_week_number_from_url()` 从重定向 URL 读取当前周，再由 `_room_view_url()` 生成含 `zc` 和 `perpage=500` 的 URL；`tests/test_sync.py`。 | Source Code / Test Code | Confirmed |
| 非空占用数据若包含目标周之外的日期，同步会在写库前失败。 | `bjtu_rooms/sync.py:_validate_occupancy_week()` 在 `upsert_rooms_and_occupancies()` 前调用；`tests/test_sync.py`。 | Source Code / Test Code | Confirmed |
| 最近日期快捷入口基线提交为 `74cf8c7 Add today and tomorrow date shortcuts`。 | `git log --oneline -n 3` 输出。 | Config | Confirmed |

## Entry Points
| Entry | File | Function / Component | Evidence |
|---|---|---|---|
| AI 任务同步 hook | `AGENTS.md` | Pre-Task Hook / Post-Task Hook | 任务前读取 `docs/architecture/current-state.md`；任务后按变更影响更新本文档。 |
| CLI 启动 | `bjtu_rooms/cli.py` | `main()` | 解析网络、浏览器和 `--shutdown-after-minutes` 参数后创建应用及 Uvicorn 服务。 |
| FastAPI 应用 | `bjtu_rooms/app.py` | `create_app()` / module-level `app` | 创建 FastAPI、挂载静态文件、注册 API。 |
| 首页 | `bjtu_rooms/app.py` + `static/index.html` | `GET /` / static HTML | `index()` 返回 `static/index.html`。 |
| 状态 API | `bjtu_rooms/app.py` | `GET /api/status` | 返回 `sync`、`runtime.shutdown_at`、`rooms_count`、`has_username`。 |
| 搜索 API | `bjtu_rooms/app.py` | `GET /api/search` | 读取数据库后调用 `search_empty_rooms()`。 |
| 同步 API | `bjtu_rooms/app.py` | `POST /api/sync` | 调用 `sync_today()`。 |
| 前端初始化 | `static/app.js` | `init()` / `getDefaultSearchSelection()` | 按打开时本机时间设置日期和单节范围、填充节次、加载状态/楼栋/偏好。 |
| 日期快捷入口 | `static/index.html` / `static/app.js` | `todayButton` / `tomorrowButton` / `setDateFromToday()` | 点击“今天”或“明天”设置日期；已有搜索结果时自动重新查询。 |

## Call Chain
```text
[confirmed] user opens CLI
  -> [confirmed] bjtu_rooms.cli:main()
  -> [confirmed] calculate optional shutdown_at from --shutdown-after-minutes
  -> [confirmed] bjtu_rooms.app:create_app(shutdown_at=...)
  -> [confirmed] uvicorn.Server runs while an optional shutdown timer waits
  -> [confirmed] static/index.html + static/app.js served

[confirmed] user searches rooms in browser
  -> [confirmed] static/app.js:runSearch()
  -> [confirmed] GET /api/search
  -> [confirmed] bjtu_rooms.app:search()
  -> [confirmed] storage.load_rooms()
  -> [confirmed] storage.load_occupancy_by_room()
  -> [confirmed] storage.get_preference()
  -> [confirmed] core.search_empty_rooms()
  -> [confirmed] dataclasses.asdict() response payload
  -> [confirmed] static.app.js:renderResults()
  -> [confirmed] static.app.js:renderPeriodStatuses()

[confirmed] user triggers sync
  -> [confirmed] static/app.js sync button click handler
  -> [confirmed] POST /api/sync
  -> [confirmed] bjtu_rooms.app:sync()
  -> [confirmed] bjtu_rooms.sync:sync_today()
  -> [confirmed] bjtu_rooms.sync:fetch_classroom_data()
  -> [confirmed] sync resolves the configured week or reads the server week from the default-page redirect
  -> [confirmed] sync._room_view_url() requests that week with perpage=500
  -> [confirmed] bjtu_rooms.parser:parse_classroom_html()
  -> [confirmed] sync._validate_occupancy_week()
  -> [confirmed] storage.upsert_rooms_and_occupancies()
  -> [confirmed] storage.prune_occupancies_outside_retention_window()
  -> [confirmed] storage.save_sync_state()
```

## Data Flow
| Data | From | To | Evidence |
|---|---|---|---|
| Search parameters | `static/app.js:runSearch()` | `/api/search` query string | Uses `URLSearchParams` with date/start/end/building. |
| Initial date and period | Browser local clock + `PERIOD_SCHEDULE` | `getDefaultSearchSelection()` -> date/start/end inputs | One snapshot at page initialization; first unfinished period, or next calendar day period 1 after 21:50. No initial search. |
| Date shortcut selection | `static/app.js:setDateFromToday()` | `dateInput.value` -> optional `runSearch()` | Offset 0 selects local today; offset 1 selects local tomorrow; if `hasSearched` is true, it reruns search. |
| Rooms | SQLite `rooms` table | `load_rooms()` -> `search_empty_rooms()` | `storage.load_rooms()` returns `list[Room]`. |
| Occupancies | SQLite `occupancies` table | `load_occupancy_by_room()` -> `search_empty_rooms()` | `storage.load_occupancy_by_room()` groups records by raw room name. |
| Preferences | SQLite `preferences` table | `get_preference()` -> `preference_score()` | `storage.get_preference()` returns `Preference`; `core.preference_score()` scores building/prefix. |
| Period statuses | `core.period_statuses()` | API `items[].period_statuses` -> UI status dots | `SearchResult.period_statuses`; frontend `renderPeriodStatuses()`. |
| Sync state | `sync_today()` | SQLite `sync_state` -> `/api/status` -> topbar text | `save_sync_state()` and `app.status()`. |
| Shutdown time | CLI local clock + timeout argument | `create_app()` -> `/api/status.runtime.shutdown_at` -> topbar text | `cli.main()` computes a timezone-aware datetime; frontend formats it in the browser locale. |
| Teaching week selection | settings + target date + default-page redirect | `_week_number_from_url()` / `_room_view_url()` -> BJTU room-view request | Explicit `week_number` wins; otherwise `semester_start` derives a week; with neither, the server-selected `zc` is read and reused with `perpage=500`. |
| Parsed occupancy dates | `parse_classroom_html()` | `_validate_occupancy_week()` -> database write or `SyncError` | Non-empty results containing any date outside the target week are rejected before upsert. |
| Occupancy retention | `occupancy_retention_window(reference_day)` | `prune_occupancies_outside_retention_window()` | Keeps records from current Monday through next Sunday, inclusive. |
| Credentials | Account modal | `/api/credentials` -> settings/keyring | `static/app.js` posts username/password; `credentials.save_credentials()` persists them. |

## State Transitions
| From | Event | To | Evidence |
|---|---|---|---|
| `sync_state.status = never` | `init_db()` creates first row | `never` with message `No sync has run yet.` | `storage.init_db()` insert-or-ignore SQL. |
| Any sync state | `sync_today()` succeeds | `ok` with synced date and message | `sync.py:sync_today()` calls `save_sync_state(..., status="ok")`. |
| Any sync state | `sync_today()` raises | `error` with exception message while retaining any prior successful date | `sync.py:sync_today()` calls `save_sync_state(..., synced_day=None, status="error")`; storage preserves the existing date. |
| Frontend `hasSearched = false` | Search succeeds | `hasSearched = true` | `static/app.js:runSearch()` sets it after rendering. |
| Account modal hidden | Account button click | Modal visible | `static/app.js` sets `accountModal.hidden = false`. |
| Account modal visible | Close/cancel/backdrop/save success | Modal hidden | `closeAccountModal()` sets `hidden = true`. |

## Database Operations
| Table / Entity | Operation | File | Evidence |
|---|---|---|---|
| `rooms` | Create table | `bjtu_rooms/storage.py` | `init_db()` SQL. |
| `rooms` | Insert/update room metadata | `bjtu_rooms/storage.py` | `upsert_rooms_and_occupancies()` uses `insert ... on conflict(raw_name) do update`. |
| `rooms` | Read all rooms | `bjtu_rooms/storage.py` | `load_rooms()` selects raw_name/building/room/campus. |
| `occupancies` | Create table and day/room index | `bjtu_rooms/storage.py` | `init_db()` SQL includes `idx_occupancies_day_room`. |
| `occupancies` | Replace affected days then insert occupancies | `bjtu_rooms/storage.py` | `upsert_rooms_and_occupancies()` deletes by day then inserts records. |
| `occupancies` | Skip duplicate occupancy input | `bjtu_rooms/storage.py` | `upsert_rooms_and_occupancies()` tracks `(raw_room_name, day, start_period, end_period)` while inserting. |
| `occupancies` | Delete records outside current-week/next-week retention window | `bjtu_rooms/storage.py` | `prune_occupancies_outside_retention_window()` deletes days before current Monday or after next Sunday. |
| `occupancies` | Read occupancies for selected day | `bjtu_rooms/storage.py` | `load_occupancy_by_room()` joins rooms and occupancies by room_id. |
| `preferences` | Create table and default row | `bjtu_rooms/storage.py` | Defaults are `["yf"]` and `["4", "5", "6"]`. |
| `preferences` | Read/write preference | `bjtu_rooms/storage.py` | `get_preference()` / `save_preference()`. |
| `sync_state` | Create table and default row | `bjtu_rooms/storage.py` | Default status `never`. |
| `sync_state` | Save sync result | `bjtu_rooms/storage.py` | `save_sync_state()`. |

## External Dependencies
| Dependency | Usage | Evidence | Risk |
|---|---|---|---|
| FastAPI | HTTP API and app factory | `pyproject.toml`; `bjtu_rooms/app.py` imports `FastAPI`, `HTTPException`, `Query` | API shape changes need frontend compatibility. |
| Uvicorn | Local server | `pyproject.toml`; `bjtu_rooms/cli.py` | CLI uses `reload=False`; code changes require service restart. |
| Playwright | BJTU login and classroom page fetch | `pyproject.toml`; `sync.py:fetch_classroom_data()` | Browser install, login structure, CAPTCHA, or network issues can break sync. |
| BeautifulSoup | HTML parsing | `pyproject.toml`; `parser.py:parse_classroom_html()` | BJTU page structure changes may require parser updates. |
| keyring | Password storage | `pyproject.toml`; `credentials.py` | Platform keychain availability affects saving/loading password. |
| SQLite stdlib | Local persistent store | `storage.py` imports `sqlite3` | Local `data/rooms.sqlite3` carries app state; not tracked by source. |

## Async Jobs
- CLI startup creates an optional shutdown timer; the default delay is 30 minutes, a zero delay setting disables it, and early server exit cancels the timer.
- App startup uses `lifespan()` in `bjtu_rooms/app.py`; it captures the local date once and schedules `_startup_sync()` only when `sync_state.last_sync_date` differs from that date.
- App startup also prunes `occupancies` outside the current-week/next-week retention window using that same captured date.
- `_startup_sync()` catches exceptions so failures do not prevent the app from serving; `sync_today()` records the error for `/api/status`. Lifespan shutdown awaits the background task so automatic exit does not cancel an in-progress startup sync.
- Manual sync is `POST /api/sync`; it awaits `sync_today()`, writes current BJTU week data, prunes occupancy records outside the retention window, and returns either `{"ok": true, "message": ...}` or an HTTP 400 with error detail. The UI labels this as syncing weekly data because the BJTU room page is parsed as a week view.

## Error Handling
- `/api/search` catches `ValueError` from `validate_period_range()` and returns HTTP 400 with the message.
- `/api/credentials` catches `CredentialError` and returns HTTP 400.
- `/api/sync` catches general exceptions and returns HTTP 400.
- Wrong-week occupancy payloads raise `SyncError` before database replacement and are surfaced by `/api/sync` as HTTP 400.
- `requestJson()` in `static/app.js` parses JSON, checks `response.ok`, and throws `payload.detail || "请求失败"`.
- Frontend data-shape safeguards currently exist for arrays from `payload.items`, `payload.preferred_buildings`, `payload.preferred_room_prefixes`, building list items, missing `payload.sync`, and missing `period_statuses`.

## Edge Cases
- 页面默认值统一按普通楼栋课表计算；YF 第二节 10:30–12:20 的差异不参与匹配。日期快捷入口只改日期，不重新匹配节次；刷新页面会根据刷新时的本机时间重新初始化。
- `period_statuses` missing from an older running backend response shows “暂无状态” in the UI. This prevents a frontend crash but means the Python service likely needs restart to load current code.
- `bjtu_rooms.cli:main()` starts uvicorn without reload. Static files may reflect disk changes immediately, while Python route logic can stay stale until restart.
- `sync_today()` raises `SyncError` if no rooms are parsed.
- `fetch_classroom_data()` falls back to headed Playwright mode if the fetched page still looks like a login page and the initial run was headless.
- Parser supports several structures, but BJTU HTML changes remain a known parser maintenance risk.
- Clicking “今天” or “明天” before any search only changes the date input; clicking after a successful search also refreshes results.
- On Sunday, the retention window is still current Monday through next Sunday, so next Monday remains queryable after data has been synced.
- Records older than current Monday and later than next Sunday are pruned on startup and after successful sync; `rooms` metadata is not pruned.

## Risks
| Risk | Evidence | Impact | Suggested Next Step |
|---|---|---|---|
| 默认节次依赖固定课表和浏览器本机时钟。 | `static/app.js:PERIOD_SCHEDULE` / `getDefaultSearchSelection()`；用户确认的 YF 差异。 | 校方调整作息、本机时间不准或 YF 第二节尚未结束时，默认节次可能不符合实际使用需求。 | 当前可手动改节次；课表调整时更新固定配置，按楼栋匹配另行确认需求。 |
| Running service can be stale after code changes. | `cli.py` uses `reload=False`; previous issue manifested as frontend expecting `period_statuses` while old backend did not return it. | UI can show fallback “暂无状态” or mismatch current code. | Restart `uv run bjtu-rooms` after backend code changes; use reload command for development. |
| Startup sync errors are not logged to the terminal. | `_startup_sync()` catches `Exception` after `sync_today()` records the error. | The page shows the stored error, but terminal-only users may miss it. | Consider adding structured terminal logging if operational diagnosis becomes difficult. |
| A background sync can delay automatic shutdown. | Lifespan shutdown awaits the startup sync task by design. | Exit can occur later than the nominal deadline while Playwright requests finish. | Existing page operations have 30-second timeouts; add a hard shutdown deadline only if delayed exits become a problem. |
| Parser depends on current BJTU page semantics. | `parser.py` uses table text, titles, background colors, and regexes. | Sync may parse zero rooms or wrong occupancies if upstream HTML changes. | Keep sample HTML-based parser tests updated when BJTU page changes. |
| Server-current-week discovery depends on the redirected room-view URL containing `zc`. | `fetch_classroom_data()` reads `page.url`; 2026-09-08 live verification redirected to `?zc=1`. | If the upstream redirect contract changes, sync will fail with a clear error before parsing or replacing data. | Update `_week_number_from_url()` or use the page's week selector if the upstream URL contract changes. |
| Credential storage depends on keyring availability. | `credentials.py` raises/returns based on `keyring` import and keychain operations. | Sync cannot run without saved password. | Document platform setup or provide clearer UI error if keyring fails. |
| Retention cleanup only deletes occupancy rows. | `prune_occupancies_outside_retention_window()` deletes from `occupancies`; `rooms` are retained. | Room metadata can accumulate if the upstream room list changes substantially. | Add room pruning only if stale room metadata becomes a real issue. |

## Possible Causes to Verify
| Possible Cause | Missing Evidence | Files to Check Next |
|---|---|---|
| If UI shows “暂无状态” after this commit, the running backend may still be stale. | Need live `/api/search` response from the currently running port. | Check `/api/search` response shape and restart CLI service if missing `period_statuses`. |
| If sync returns success but search results look wrong, parser may misclassify cells. | Need saved HTML sample and parsed output comparison. | `bjtu_rooms/parser.py`, `tests/test_parser.py`, optional `data/sample-room-view.html`. |
| If account save appears successful but sync says missing credentials, keyring lookup may fail. | Need platform keyring behavior and saved username state. | `bjtu_rooms/credentials.py`, `data/settings.json` runtime file. |

## Open Questions
- Should `free_until_period` remain in the API response even though the UI no longer displays “可空到”? Current code still keeps it in `SearchResult`.
- Should startup auto-sync failures be recorded in `sync_state` instead of silently ignored?
- Should there be an integration/API test for `/api/search` response shape? Current test verifies core dataclass serialization, not the FastAPI route.
- Should developer startup default to `--reload` or a separate dev script to avoid stale Python backends?
- Should old `rooms` with no retained occupancies ever be pruned, or should room metadata remain as the latest known classroom inventory?

## Recommended Next Step
- `task-planning-flow`：如果要调整行为，例如记录启动同步失败、增加 API 集成测试、改变 dev 启动方式，先出小任务方案。
- `bugfix-flow`：如果再次出现搜索状态缺失、同步错误、解析结果异常，先按 bug 流程复现和定位。
- `execute-agent`：如果已有明确方案并批准实现，再修改源码和测试。
- `review-agent`：如果需要对日期快捷入口提交 `74cf8c7 Add today and tomorrow date shortcuts` 或后续功能 diff 做第二视角复核，可只读审查 diff。
- `sync-docs-flow`：后续如果继续修改 API、状态流转或数据库逻辑，应同步更新本文档或拆分到更细的模块文档。
