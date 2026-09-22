const statusText = document.querySelector("#statusText");
const accountButton = document.querySelector("#accountButton");
const syncButton = document.querySelector("#syncButton");
const searchForm = document.querySelector("#searchForm");
const preferenceForm = document.querySelector("#preferenceForm");
const credentialForm = document.querySelector("#credentialForm");
const accountModal = document.querySelector("#accountModal");
const closeAccountButton = document.querySelector("#closeAccountButton");
const cancelAccountButton = document.querySelector("#cancelAccountButton");
const dateInput = document.querySelector("#dateInput");
const todayButton = document.querySelector("#todayButton");
const tomorrowButton = document.querySelector("#tomorrowButton");
const startPeriod = document.querySelector("#startPeriod");
const endPeriod = document.querySelector("#endPeriod");
const buildingInput = document.querySelector("#buildingInput");
const buildingPrefs = document.querySelector("#buildingPrefs");
const roomPrefs = document.querySelector("#roomPrefs");
const usernameInput = document.querySelector("#usernameInput");
const passwordInput = document.querySelector("#passwordInput");
const resultCount = document.querySelector("#resultCount");
const resultsBody = document.querySelector("#resultsBody");
const toast = document.querySelector("#toast");
let hasSearched = false;

init();

function init() {
  const today = new Date();
  dateInput.value = formatLocalDate(today);
  fillPeriods();
  startPeriod.value = "1";
  endPeriod.value = "2";
  loadStatus();
  loadBuildings();
  loadPreferences();
}

function fillPeriods() {
  for (let period = 1; period <= 7; period += 1) {
    const startOption = document.createElement("option");
    startOption.value = String(period);
    startOption.textContent = `第 ${period} 节`;
    startPeriod.append(startOption);

    const endOption = document.createElement("option");
    endOption.value = String(period);
    endOption.textContent = `第 ${period} 节`;
    endPeriod.append(endOption);
  }
}

syncButton.addEventListener("click", async () => {
  syncButton.disabled = true;
  showToast("开始同步本周教室数据...");
  try {
    const payload = await requestJson("/api/sync", { method: "POST" });
    showToast(payload.message || "本周数据同步完成。");
    await loadStatus();
    await loadBuildings();
    if (hasSearched) {
      await runSearch();
    }
  } catch (error) {
    showToast(error.message, true);
    await loadStatus();
  } finally {
    syncButton.disabled = false;
  }
});

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runSearch();
});

todayButton.addEventListener("click", async () => {
  await setDateFromToday(0);
});

tomorrowButton.addEventListener("click", async () => {
  await setDateFromToday(1);
});

async function runSearch() {
  const params = new URLSearchParams({
    date: dateInput.value,
    start_period: startPeriod.value,
    end_period: endPeriod.value,
  });
  if (buildingInput.value.trim()) {
    params.set("building", buildingInput.value.trim());
  }
  try {
    const payload = await requestJson(`/api/search?${params.toString()}`);
    renderResults(toArray(payload.items));
    hasSearched = true;
  } catch (error) {
    showToast(error.message, true);
  }
}

async function setDateFromToday(offsetDays) {
  const targetDate = new Date();
  targetDate.setDate(targetDate.getDate() + offsetDays);
  dateInput.value = formatLocalDate(targetDate);
  if (hasSearched) {
    await runSearch();
  }
}

preferenceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    preferred_buildings: splitCsv(buildingPrefs.value),
    preferred_room_prefixes: splitCsv(roomPrefs.value),
  };
  try {
    await requestJson("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showToast("偏好已保存。");
    if (hasSearched) {
      await runSearch();
    }
  } catch (error) {
    showToast(error.message, true);
  }
});

accountButton.addEventListener("click", () => {
  accountModal.hidden = false;
  usernameInput.focus();
});

closeAccountButton.addEventListener("click", closeAccountModal);
cancelAccountButton.addEventListener("click", closeAccountModal);

accountModal.addEventListener("click", (event) => {
  if (event.target === accountModal) {
    closeAccountModal();
  }
});

credentialForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await requestJson("/api/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: usernameInput.value,
        password: passwordInput.value,
      }),
    });
    passwordInput.value = "";
    showToast("账号已保存到本机。");
    closeAccountModal();
    await loadStatus();
  } catch (error) {
    showToast(error.message, true);
  }
});

async function loadStatus() {
  try {
    const payload = await requestJson("/api/status");
    const sync = payload.sync || {};
    const pieces = [];
    pieces.push(`本地教室数：${payload.rooms_count ?? 0}`);
    if (sync.last_sync_date) {
      pieces.push(`最近同步：${sync.last_sync_date}`);
    } else {
      pieces.push("尚未同步");
    }
    if (!payload.has_username) {
      pieces.push("请先保存教务账号");
    }
    if (sync.status === "error") {
      pieces.push(`同步错误：${sync.message}`);
    }
    const shutdownTime = formatShutdownTime(payload.runtime?.shutdown_at);
    if (shutdownTime) {
      pieces.push(`服务将在 ${shutdownTime} 自动关闭`);
    }
    statusText.textContent = pieces.join(" · ");
    accountButton.textContent = payload.has_username ? "账号已保存" : "保存教务账号";
  } catch (error) {
    statusText.textContent = `状态读取失败：${error.message}`;
  }
}

function formatShutdownTime(value) {
  if (!value) {
    return null;
  }
  const shutdownAt = new Date(value);
  if (Number.isNaN(shutdownAt.getTime())) {
    return null;
  }
  return shutdownAt.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

async function loadBuildings() {
  try {
    const payload = await requestJson("/api/buildings");
    const currentValue = buildingInput.value;
    buildingInput.textContent = "";

    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "全部教学楼";
    buildingInput.append(allOption);

    for (const item of toArray(payload.items)) {
      const building = item || {};
      const option = document.createElement("option");
      option.value = building.value || "";
      option.textContent = building.label || building.value || "-";
      buildingInput.append(option);
    }
    buildingInput.value = currentValue;
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadPreferences() {
  try {
    const payload = await requestJson("/api/preferences");
    buildingPrefs.value = toArray(payload.preferred_buildings).join(", ");
    roomPrefs.value = toArray(payload.preferred_room_prefixes).join(", ");
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderResults(items) {
  const results = toArray(items);
  resultCount.textContent = `${periodRangeText()} 可用 · ${results.length} 间`;
  resultsBody.textContent = "";
  if (!results.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="5" class="empty">所选节次没有查到可用教室。</td>`;
    resultsBody.append(row);
    return;
  }

  for (const item of results) {
    const result = item || {};
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(result.raw_name || "-")}</td>
      <td>${escapeHtml(result.building_label || result.building || "-")}</td>
      <td>${renderPeriodStatuses(result.period_statuses)}</td>
      <td class="result-meta">${escapeHtml(result.continuous_free_periods ?? "-")} 节</td>
      <td>${result.preference_matched ? '<span class="badge">偏好</span>' : ""}</td>
    `;
    resultsBody.append(row);
  }
}

function renderPeriodStatuses(statuses) {
  if (!Array.isArray(statuses)) {
    return '<span class="result-meta">暂无状态</span>';
  }
  const dots = statuses
    .map((status) => {
      const item = status || {};
      const classes = ["period-dot"];
      if (!item.available) {
        classes.push("busy");
      }
      if (item.selected) {
        classes.push("selected");
      }
      const period = item.period ?? "-";
      const title = `第 ${period} 节${item.available ? "空闲" : "占用"}${
        item.selected ? "，当前查询" : ""
      }`;
      return `<span class="${classes.join(" ")}" title="${escapeHtml(title)}">${escapeHtml(
        period,
      )}</span>`;
    })
    .join("");
  return `<span class="status-strip" aria-label="今日节次状态">${dots}</span>`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "请求失败");
  }
  return payload;
}

function splitCsv(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.classList.remove("show");
  }, 3600);
}

function closeAccountModal() {
  accountModal.hidden = true;
  passwordInput.value = "";
}

function periodRangeText() {
  if (startPeriod.value === endPeriod.value) {
    return `第 ${startPeriod.value} 节`;
  }
  return `第 ${startPeriod.value}-${endPeriod.value} 节`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatLocalDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
