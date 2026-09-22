# BJTU Room Finder

本地空教室查询工具。启动后打开本地网页，用日期和节次查询北京交通大学教务系统里的空教室，并按个人偏好和连续空闲时长排序。

## Quick start

```bash
uv sync
uv run playwright install chromium
uv run bjtu-rooms
```

默认访问地址是 <http://127.0.0.1:8000>。

本地服务默认在启动 30 分钟后自动退出，已打开的浏览器标签不会被关闭。可以修改运行时长，或用 `0` 禁用自动退出：

```bash
uv run bjtu-rooms --shutdown-after-minutes 60
uv run bjtu-rooms --shutdown-after-minutes 0
```

首次使用时，在页面里保存教务系统账号。用户名会写入本地 `data/settings.json`，密码通过系统 Keychain/keyring 保存，不写入项目文件。

## Development

```bash
uv run pytest
uv run uvicorn bjtu_rooms.app:create_app --factory --reload
```

## Using a saved classroom page

如果需要用浏览器保存下来的教室查询页校准解析器，可以先把 HTML 放到 `data/sample-room-view.html`，然后在 Python 里导入：

```bash
uv run python -c "import asyncio; from datetime import date; from pathlib import Path; from bjtu_rooms.sync import sync_from_html_file; asyncio.run(sync_from_html_file(Path('data/sample-room-view.html'), date.today()))"
```

BJTU 教室页是周视图，页面里的 `星期一 06月29日` 这类表头会被解析成真实日期；白色格子视为空闲，其他颜色视为占用。

## Notes

- 每次启动会读取本机当前日期；如果今天尚未成功同步，会在后台尝试自动同步。
- 同步失败不会清除之前成功同步的日期；当天只要成功过一次，再次启动就不会重复自动同步。
- 页面状态区会显示本次服务预计自动关闭的时间；禁用自动退出时不显示。
- 如果教务系统需要验证码或登录页结构变化，同步会退到可视化浏览器登录流程。
- 同步请求会优先使用 `perpage=500`，尽量一次抓完整周全部教室。
