from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
END_TIMES = ["09:50", "12:00", "14:00", "16:00", "18:10", "20:50", "21:50"]


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def frontend(browser):
    context = browser.new_context(timezone_id="Asia/Shanghai")
    page = context.new_page()
    requests = []
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def serve(route):
        path = urlsplit(route.request.url).path
        if path.startswith("/api/"):
            requests.append(route.request.url)
            payloads = {
                "/api/status": {"rooms_count": 0, "has_username": True},
                "/api/buildings": {"items": [{"value": "yf", "label": "逸夫楼"}]},
                "/api/preferences": {
                    "preferred_buildings": ["yf"],
                    "preferred_room_prefixes": ["4", "5", "6"],
                },
                "/api/search": {"items": []},
            }
            route.fulfill(json=payloads[path])
        elif path == "/":
            route.fulfill(path=STATIC_DIR / "index.html", content_type="text/html")
        elif path in {"/static/app.js", "/static/styles.css"}:
            route.fulfill(path=STATIC_DIR / path.rsplit("/", 1)[1])
        else:
            route.fulfill(status=404)

    page.route("http://room.test/**", serve)
    yield page, requests, errors
    assert not errors
    context.close()


def open_at(frontend, timestamp):
    page, requests, _ = frontend
    page.clock.install(time=datetime.fromisoformat(timestamp + "+08:00"))
    page.goto("http://room.test/")
    expect(page.locator("#buildingPrefs")).to_have_value("yf")
    assert not any("/api/search?" in url for url in requests)
    return page


def assert_selection(page, day, period):
    expect(page.locator("#dateInput")).to_have_value(day)
    expect(page.locator("#startPeriod")).to_have_value(str(period))
    expect(page.locator("#endPeriod")).to_have_value(str(period))


@pytest.mark.parametrize("period,end_time", list(enumerate(END_TIMES, start=1)))
@pytest.mark.parametrize("offset_seconds", [-1, 0])
def test_defaults_at_each_end_boundary(frontend, period, end_time, offset_seconds):
    timestamp = datetime.fromisoformat(f"2026-10-09T{end_time}:00") + timedelta(
        seconds=offset_seconds
    )
    page = open_at(frontend, timestamp.isoformat())
    if offset_seconds == -1:
        assert_selection(page, "2026-10-09", period)
    elif period < 7:
        assert_selection(page, "2026-10-09", period + 1)
    else:
        assert_selection(page, "2026-10-10", 1)


@pytest.mark.parametrize(
    "timestamp,day,period",
    [
        ("2026-10-09T00:00:00", "2026-10-09", 1),
        ("2026-10-09T07:00:00", "2026-10-09", 1),
        ("2026-10-09T08:30:00", "2026-10-09", 1),
        ("2026-10-09T10:00:00", "2026-10-09", 2),
        ("2026-10-09T11:00:00", "2026-10-09", 2),
        ("2026-10-09T12:05:00", "2026-10-09", 3),
        ("2026-10-09T13:00:00", "2026-10-09", 3),
        ("2026-10-09T14:05:00", "2026-10-09", 4),
        ("2026-10-09T15:00:00", "2026-10-09", 4),
        ("2026-10-09T16:07:00", "2026-10-09", 5),
        ("2026-10-09T17:00:00", "2026-10-09", 5),
        ("2026-10-09T18:30:00", "2026-10-09", 6),
        ("2026-10-09T20:00:00", "2026-10-09", 6),
        ("2026-10-09T20:55:00", "2026-10-09", 7),
        ("2026-10-09T21:30:00", "2026-10-09", 7),
        ("2026-10-09T23:59:59", "2026-10-10", 1),
        ("2026-10-31T21:50:00", "2026-11-01", 1),
        ("2026-12-31T21:50:00", "2027-01-01", 1),
        ("2028-02-28T21:50:00", "2028-02-29", 1),
    ],
)
def test_defaults_during_classes_breaks_and_date_rollovers(frontend, timestamp, day, period):
    assert_selection(open_at(frontend, timestamp), day, period)


def test_search_uses_defaults_and_refresh_recalculates(frontend):
    page = open_at(frontend, "2026-10-09T16:07:00")
    requests = frontend[1]
    page.locator("#searchForm button[type=submit]").click()
    expect(page.locator("#resultCount")).to_have_text("第 5 节 可用 · 0 间")
    query = parse_qs(urlsplit(requests[-1]).query)
    assert query == {"date": ["2026-10-09"], "start_period": ["5"], "end_period": ["5"]}

    page.clock.set_fixed_time(datetime.fromisoformat("2026-10-09T21:50:00+08:00"))
    assert_selection(page, "2026-10-09", 5)
    search_count = sum("/api/search?" in url for url in requests)
    page.reload()
    expect(page.locator("#buildingPrefs")).to_have_value("yf")
    assert_selection(page, "2026-10-10", 1)
    assert sum("/api/search?" in url for url in requests) == search_count


def test_manual_choices_and_date_shortcuts_keep_selected_periods(frontend):
    page = open_at(frontend, "2026-10-09T16:07:00")
    page.locator("#dateInput").fill("2026-10-12")
    page.locator("#startPeriod").select_option("2")
    page.locator("#endPeriod").select_option("3")
    page.locator("#buildingInput").select_option("yf")
    page.clock.fast_forward(6 * 60 * 60 * 1000)
    expect(page.locator("#dateInput")).to_have_value("2026-10-12")
    expect(page.locator("#startPeriod")).to_have_value("2")
    expect(page.locator("#endPeriod")).to_have_value("3")
    assert not any("/api/search?" in url for url in frontend[1])

    page.locator("#todayButton").click()
    expect(page.locator("#dateInput")).to_have_value("2026-10-09")
    page.locator("#searchForm button[type=submit]").click()
    expect(page.locator("#resultCount")).to_have_text("第 2-3 节 可用 · 0 间")
    with page.expect_response("**/api/search?*"):
        page.locator("#tomorrowButton").click()
    expect(page.locator("#dateInput")).to_have_value("2026-10-10")
    query = parse_qs(urlsplit(frontend[1][-1]).query)
    assert query == {
        "date": ["2026-10-10"], "start_period": ["2"], "end_period": ["3"], "building": ["yf"]
    }
