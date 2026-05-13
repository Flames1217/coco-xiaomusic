const qs = (selector) => document.querySelector(selector);
const actionResult = qs("#action-result");
const eventsNode = qs("#events");
const keywordInput = qs("#keyword");
const volumeSlider = qs("#volume-slider");
const progressSlider = qs("#progress-slider");

let latestStatus = null;
let latestPlayerStatus = 0;
let lastPlayerStatusAt = 0;
let playerActionHoldUntil = 0;
let volumeTimer = null;
let volumeEditing = false;
let volumeHoldUntil = 0;
let lastVolumePointerUp = 0;
let progressEditing = false;
let lastProgressPointerUp = 0;
let previewItems = [];
let selectedProvider = "all";
let currentPlaybackAt = "";
let playerStartedAtMs = 0;
let playerDurationSec = 0;
let playerPositionSec = 0;
let lastCommittedVolume = null;

function clampVolume(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

function getVolumeInput() {
  return qs("#volume-input");
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || data.error || "请求失败");
  }
  return data;
}

function setText(selector, value) {
  const node = qs(selector);
  if (node) node.textContent = value || "--";
}

function makeInitial(title, artist) {
  const source = `${artist || ""}${title || ""}`.trim();
  if (!source) return "CO";
  const chars = [...source.replace(/[^\p{L}\p{N}]/gu, "")];
  return chars.slice(0, 2).join("").toUpperCase() || "CO";
}

function setPlayerCover(cover, title, artist) {
  const art = qs(".album-art");
  const img = qs("#player-cover");
  if (!art || !img) return;
  if (cover) {
    img.src = cover;
    img.onload = () => art.classList.add("has-cover");
    img.onerror = () => {
      img.removeAttribute("src");
      art.classList.remove("has-cover");
    };
  } else {
    img.removeAttribute("src");
    art.classList.remove("has-cover");
  }
  setText("#player-initial", makeInitial(title, artist));
}

function formatTime(totalSec) {
  const sec = Math.max(0, Number(totalSec) || 0);
  const minutes = Math.floor(sec / 60);
  const seconds = Math.floor(sec % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function formatDuration(value) {
  if (value === undefined || value === null || value === "") return "--:--";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return "--:--";
    if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(trimmed)) return trimmed;
    const numeric = Number(trimmed);
    if (!Number.isFinite(numeric)) return trimmed;
    value = numeric;
  }
  let seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "--:--";
  if (seconds > 10000) seconds = seconds / 1000;
  return formatTime(seconds);
}

function durationSeconds(value) {
  if (value === undefined || value === null || value === "") return 0;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return 0;
    const parts = trimmed.split(":").map(Number);
    if (parts.length === 2 && parts.every(Number.isFinite)) return parts[0] * 60 + parts[1];
    if (parts.length === 3 && parts.every(Number.isFinite)) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    value = Number(trimmed);
  }
  let seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return 0;
  return seconds > 10000 ? seconds / 1000 : seconds;
}

function parsePlaybackTime(value) {
  if (!value) return 0;
  const normalized = String(value).replace(" ", "T");
  const parsed = Date.parse(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
}

function showBottomPlayer() {
  document.body.classList.add("player-visible");
}

function currentProgressSeconds() {
  if (latestPlayerStatus === 1 && playerStartedAtMs) {
    return Math.max(0, (Date.now() - playerStartedAtMs) / 1000);
  }
  return Math.max(0, playerPositionSec || 0);
}

function setProgressUI(seconds) {
  const capped = playerDurationSec > 0 ? Math.min(Math.max(0, seconds), playerDurationSec) : Math.max(0, seconds);
  playerPositionSec = capped;
  setText("#player-elapsed", formatTime(capped));
  setText("#player-duration", playerDurationSec > 0 ? formatTime(playerDurationSec) : "--:--");
  const bar = qs("#player-progress");
  const ratio = playerDurationSec > 0 ? Math.min(100, (capped / playerDurationSec) * 100) : 0;
  if (bar) bar.style.width = `${ratio}%`;
  if (progressSlider && !progressEditing) {
    progressSlider.max = String(Math.max(1, Math.round(playerDurationSec || 100)));
    progressSlider.value = String(Math.round(capped));
    progressSlider.style.setProperty("--value", `${ratio}%`);
  }
}

function updateProgress() {
  if (progressEditing) return;
  setProgressUI(currentProgressSeconds());
}

function providerLabel(provider) {
  const labels = {
    qq: "QQ音乐",
    qqmp3: "QQMP3",
    migu: "咪咕",
    kugou: "酷狗",
    kuwo: "酷我",
    netease: "网易云",
    livepoo: "方音",
    fangyin: "方音",
    gequhai: "歌曲海",
    "jianbin-qq": "煎饼-QQ",
    "jianbin_qq": "煎饼-QQ",
    "jianbin-kugou": "煎饼-酷狗",
    "jianbin-kuwo": "煎饼-酷我",
    "jianbin-netease": "煎饼-网易",
  };
  return labels[provider] || provider || "未知渠道";
}

function setStep(selector, state, copy) {
  const node = qs(selector);
  node.classList.remove("done", "warn", "error");
  if (state) node.classList.add(state);
  qs(`${selector}-copy`).textContent = copy;
}

function renderOnboarding(status) {
  setStep("#step-account", status.account_configured ? "done" : "error", status.account_configured ? "账号已保存" : "请填写小米账号");
  setStep("#step-token", status.token_present ? "done" : "warn", status.token_present ? "token 文件已生成" : "保存账号后生成 token");
  setStep("#step-device", status.selected_device_present ? "done" : "warn", status.selected_device_present ? "目标设备已选中" : "请选择音箱");
  setStep(
    "#step-ready",
    status.ready && status.selected_device_present ? "done" : status.startup_error ? "error" : "warn",
    status.ready && status.selected_device_present ? "服务已就绪" : status.startup_error || "等待服务"
  );

  const devices = qs("#device-list");
  devices.innerHTML = "";
  if (!status.devices.length) {
    devices.innerHTML = '<div class="device-item"><strong>设备列表为空</strong><span>保存账号后等待登录完成，或检查账号与网络。</span></div>';
    return;
  }

  for (const device of status.devices) {
    const selected = status.selected_dids.includes(device.did);
    const manualTarget = status.manual_target_dids.includes(device.did);
    const row = document.createElement("article");
    row.className = "device-item";
    row.innerHTML = `
      <div>
        <strong>${device.name || "未命名设备"}</strong>
        <div class="preview-copy">原始名称：${device.raw_name || "未返回"}</div>
      </div>
      <span>DID：${device.did || "--"}</span>
      <div class="device-roles">
        <label><input type="checkbox" data-role="selected" data-did="${device.did || ""}" ${selected ? "checked" : ""}>参与语音监听</label>
        <label><input type="checkbox" data-role="manual" data-did="${device.did || ""}" ${manualTarget ? "checked" : ""}>后台默认推送</label>
      </div>
      <div class="device-actions">
        <input value="${device.alias || ""}" placeholder="本地别名">
        <button type="button" data-action="rename">${device.alias ? "保存别名" : "命名"}</button>
      </div>
    `;
    row.querySelector('[data-action="rename"]').addEventListener("click", async () => {
      const body = new FormData();
      body.set("did", device.did || "");
      body.set("alias", row.querySelector("input").value || "");
      await runAction("正在保存设备别名...", "/api/setup/device-alias", body);
    });
    devices.appendChild(row);
  }
}

function renderAccountState(status) {
  const form = qs("#account-form");
  const locked = qs("#account-locked");
  if (status.account_configured) {
    form.classList.add("hidden");
    locked.classList.remove("hidden");
  } else {
    locked.classList.add("hidden");
    form.classList.remove("hidden");
  }
}

function renderPlayerSummary(status) {
  const song = status.last_song || {};
  const hasSong = Boolean(song.title || status.last_keyword);
  const title = song.title || status.last_keyword || "暂无歌曲";
  const artist = song.artist || "--";
  const duration = song.duration || song.interval || song.time || song.extra?.duration || status.last_duration;
  setText("#player-track", title);
  setText("#player-artist", artist);
  setText("#player-meta", "");
  playerDurationSec = durationSeconds(duration);
  playerPositionSec = Number(status.last_position || 0);
  if (status.last_playback_at && status.last_playback_at !== currentPlaybackAt) {
    currentPlaybackAt = status.last_playback_at;
    playerStartedAtMs = latestPlayerStatus === 1
      ? Date.now() - playerPositionSec * 1000
      : parsePlaybackTime(status.last_playback_at) || Date.now();
  }
  if (!status.last_playback_at) {
    currentPlaybackAt = "";
    playerStartedAtMs = 0;
    playerPositionSec = 0;
  }
  if (status.playback_paused) {
    playerStartedAtMs = 0;
  }
  updateProgress();
  setPlayerCover(song.cover || song.extra?.cover || "", title, artist);
  if (hasSong) showBottomPlayer();
}

function renderStatus(payload) {
  const { status, settings } = payload;
  latestStatus = status;

  setText("#device-id", status.selected_dids.length ? `${status.selected_dids.length} 台` : "未选择");
  setText("#coco-base", status.coco_base);
  setText("#last-keyword", status.last_keyword || "暂无");
  setText("#last-playback", status.last_playback_at || "暂无");
  setText("#delay-sec", `${settings.official_answer_delay_sec}s`);
  setText("#search-tts", settings.search_tts);
  setText("#found-tts", settings.found_tts);
  setText("#keywords", settings.coco_keywords.join(" / "));

  qs("#runtime-coco-base").value = settings.coco_base || "";
  qs("#runtime-delay").value = settings.official_answer_delay_sec ?? 0;
  qs("#runtime-search-tts").value = settings.search_tts || "";
  qs("#runtime-found-tts").value = settings.found_tts || "";
  qs("#runtime-error-tts").value = settings.error_tts || "";

  const runtimeTitle = qs("#runtime-title");
  const runtimeCopy = qs("#runtime-copy");
  const runtimeDot = qs(".runtime-dot");
  if (status.ready) {
    runtimeTitle.textContent = "服务在线";
    runtimeCopy.textContent = "监听语音与后台推送";
    runtimeDot.style.background = "#15803d";
  } else {
    runtimeTitle.textContent = "启动中";
    runtimeCopy.textContent = status.startup_error || "等待 xiaomusic 就绪";
    runtimeDot.style.background = "#b45309";
  }

  renderOnboarding(status);
  renderAccountState(status);
  renderPlayerSummary(status);
}

function truncateMessage(message) {
  const value = String(message || "");
  if (value.length <= 110) return value;
  return `${value.slice(0, 110)}...`;
}

function renderEvents(items) {
  eventsNode.innerHTML = "";
  if (!items.length) {
    eventsNode.innerHTML = '<article class="event info"><span class="event-time">--:--:--</span><span class="event-level">INFO</span><span class="event-message">等待第一条事件</span></article>';
    return;
  }
  for (const item of items) {
    const row = document.createElement("article");
    row.className = `event ${item.level}`;
    const time = document.createElement("span");
    time.className = "event-time";
    time.textContent = (item.at || "").slice(11);
    const level = document.createElement("span");
    level.className = "event-level";
    level.textContent = (item.level || "info").toUpperCase();
    const message = document.createElement("span");
    message.className = "event-message";
    message.textContent = truncateMessage(item.message);
    message.title = item.message || "";
    row.append(time, level, message);
    eventsNode.appendChild(row);
  }
}

async function refresh() {
  const [status, events] = await Promise.all([getJson("/api/status"), getJson("/api/events")]);
  renderStatus(status);
  renderEvents(events.items);
}

function setPlayerButtonState(statusCode) {
  const button = qs("#pause-button");
  if (!button) return;
  const isPlaying = statusCode === 1;
  document.body.classList.toggle("player-playing", isPlaying);
  button.textContent = isPlaying ? "Ⅱ" : "▶";
  button.title = isPlaying ? "暂停" : "播放";
  button.setAttribute("aria-label", button.title);
}

function setLocalVolume(value) {
  const v = clampVolume(value);
  volumeSlider.value = String(v);
  volumeSlider.style.setProperty("--value", `${v}%`);
  const input = getVolumeInput();
  if (input) input.value = String(v);
  lastCommittedVolume ??= v;
  setText("#player-volume", `音量 ${v}`);
}

async function refreshPlayer({ silent = true } = {}) {
  const data = await getJson("/api/player-status");
  const first = data.targets?.[0];
  const status = first?.status || {};
  const nextStatusCode = Number(status.status || 0);
  const now = Date.now();

  // 用户刚操作过播放器时，短时间内不让轮询状态抢回按钮和音量。
  if (now > playerActionHoldUntil && (!silent || now - lastPlayerStatusAt > 3500 || nextStatusCode === latestPlayerStatus)) {
    latestPlayerStatus = latestStatus?.playback_paused ? 2 : nextStatusCode;
    lastPlayerStatusAt = now;
    setPlayerButtonState(latestPlayerStatus);
  }

  setText("#player-did", `DID ${first?.did || "--"}`);
  setText("#player-state", "");

  if (status.volume !== undefined && status.volume !== null && !volumeEditing && now > volumeHoldUntil) {
    setLocalVolume(status.volume);
  }

  if (!silent) {
    actionResult.textContent = JSON.stringify(data, null, 2);
  }
  updateProgress();
}

async function runAction(message, url, body) {
  actionResult.textContent = message;
  try {
    const data = await getJson(url, { method: "POST", body });
    actionResult.textContent = JSON.stringify(data, null, 2);
    await refresh();
    return data;
  } catch (error) {
    actionResult.textContent = `失败：${error.message}`;
    throw error;
  }
}

function renderProviderFilter(items) {
  const node = qs("#provider-filter");
  if (!node) return;
  const counts = new Map();
  for (const entry of items) {
    const provider = entry.item?.provider || "";
    if (!provider) continue;
    counts.set(provider, (counts.get(provider) || 0) + 1);
  }
  const providers = [...counts.keys()].sort((a, b) => providerLabel(a).localeCompare(providerLabel(b), "zh-Hans-CN"));
  if (!providers.length) {
    node.innerHTML = "";
    return;
  }
  if (selectedProvider !== "all" && !counts.has(selectedProvider)) selectedProvider = "all";
  const buttons = [
    `<button type="button" class="${selectedProvider === "all" ? "active" : ""}" data-provider="all">全部 <span>${items.length}</span></button>`,
    ...providers.map((provider) => `<button type="button" class="${selectedProvider === provider ? "active" : ""}" data-provider="${provider}">${providerLabel(provider)} <span>${counts.get(provider)}</span></button>`),
  ];
  node.innerHTML = buttons.join("");
  node.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      selectedProvider = button.dataset.provider || "all";
      renderProviderFilter(previewItems);
      renderPreviewItems(previewItems);
    });
  });
}

function renderPreviewItems(items) {
  const list = qs("#preview-list");
  list.innerHTML = "";
  const filtered = selectedProvider === "all" ? items : items.filter((entry) => (entry.item?.provider || "") === selectedProvider);
  if (!filtered.length) {
    list.innerHTML = '<article class="preview-empty">这个渠道暂时没有搜索结果</article>';
    return;
  }
  for (const entry of filtered) {
    const index = items.indexOf(entry);
    const song = entry.item || {};
    const cover = song.cover || song.extra?.cover || "";
    const provider = song.provider || "";
    const duration = formatDuration(song.duration || song.interval || song.time || song.extra?.duration);
    const album = song.album || song.extra?.album || "";
    const audioType = song.audio_type || song.type || song.extra?.type || "";
    const bitrate = song.bitrate || song.quality || song.extra?.bitrate || "";
    const badge = entry.is_first
      ? '<span class="badge good">语音默认</span>'
      : '<span class="badge">可选</span>';

    const row = document.createElement("article");
    row.className = "preview-item";
    row.innerHTML = `
      <span class="preview-rank">#${index + 1}</span>
      <span class="preview-cover">${cover ? `<img src="${cover}" alt="">` : makeInitial(song.title, song.artist)}</span>
      <div>
        <div class="preview-title">${song.title || "未知标题"} - ${song.artist || "未知歌手"}</div>
        <div class="preview-meta">
          <span>渠道 ${providerLabel(provider)}</span>
          <span>时长 ${duration}</span>
          ${album ? `<span>专辑 ${album}</span>` : ""}
          ${audioType || bitrate ? `<span>${[audioType, bitrate].filter(Boolean).join(" · ")}</span>` : ""}
        </div>
      </div>
      <div class="result-actions">
        ${badge}
        <button type="button" data-song-id="${song.id || ""}" data-provider="${provider}" data-title="${song.title || ""}" data-artist="${song.artist || ""}" data-cover="${cover}">推送</button>
      </div>
    `;

    row.querySelector("button").addEventListener("click", async (event) => {
      const target = event.currentTarget;
      const body = new FormData();
      body.set("song_id", target.dataset.songId || "");
      body.set("provider", target.dataset.provider || "");
      body.set("title", target.dataset.title || "");
      body.set("artist", target.dataset.artist || "");
      body.set("cover", target.dataset.cover || "");
      await runAction("正在推送选中的歌曲...", "/api/play-selected", body);
      showBottomPlayer();
      latestPlayerStatus = 1;
      playerStartedAtMs = Date.now();
      playerPositionSec = 0;
      currentPlaybackAt = "";
      setPlayerButtonState(latestPlayerStatus);
      await refreshPlayer({ silent: false });
    });

    list.appendChild(row);
  }
}

function previewVolume(value) {
  const v = clampVolume(value);
  setLocalVolume(v);
  volumeHoldUntil = Date.now() + 5000;
  return v;
}

async function commitVolume(value) {
  const v = previewVolume(value);
  if (lastCommittedVolume === v) return;
  clearTimeout(volumeTimer);
  volumeTimer = setTimeout(async () => {
    const body = new FormData();
    body.set("volume", String(v));
    try {
      await getJson("/api/volume", { method: "POST", body });
      lastCommittedVolume = v;
      volumeHoldUntil = Date.now() + 5000;
    } catch (error) {
      actionResult.textContent = `音量设置失败：${error.message}`;
    }
  }, 180);
}

qs("#play-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = await runAction("正在用 coco 第一条推送...", "/api/play", new FormData(event.currentTarget));
  if (result?.success) {
    showBottomPlayer();
    latestPlayerStatus = 1;
    playerStartedAtMs = Date.now();
    playerPositionSec = 0;
    currentPlaybackAt = "";
    setPlayerButtonState(latestPlayerStatus);
  }
  await refreshPlayer({ silent: false });
});

qs("#save-devices-button").addEventListener("click", async () => {
  const selected = [...document.querySelectorAll('[data-role="selected"]:checked')].map((node) => node.dataset.did);
  const manualTargets = [...document.querySelectorAll('[data-role="manual"]:checked')].map((node) => node.dataset.did);
  if (!selected.length) {
    actionResult.textContent = "至少选择一台参与语音监听的设备。";
    return;
  }
  const body = new FormData();
  body.set("dids", selected.join(","));
  body.set("manual_target_dids", manualTargets.join(","));
  await runAction("正在保存多设备方案...", "/api/setup/devices", body);
});

qs("#preview-button").addEventListener("click", async () => {
  const keyword = keywordInput.value.trim();
  if (!keyword) {
    actionResult.textContent = "请先输入关键词。";
    return;
  }
  qs("#preview-title").textContent = "正在搜索...";
  qs("#preview-copy").textContent = "正在读取 coco 返回的全部结果。";
  qs("#preview-list").innerHTML = "";
  try {
    const data = await getJson(`/api/search-preview?keyword=${encodeURIComponent(keyword)}`);
    const items = data.items || [];
    previewItems = items;
    selectedProvider = "all";
    qs("#preview-title").textContent = items.length ? `已找到 ${items.length} 条结果` : "没有结果";
    qs("#preview-copy").textContent = items.length ? "语音命令默认第一条；前端可以手动推送任意一条。" : "coco 没有返回搜索结果。";
    renderProviderFilter(items);
    renderPreviewItems(items);
  } catch (error) {
    qs("#preview-title").textContent = "搜索失败";
    qs("#preview-copy").textContent = error.message;
  }
});

qs("#stop-button").addEventListener("click", async () => {
  await runAction("正在停止小爱播放...", "/api/stop", new FormData());
  latestPlayerStatus = 0;
  setPlayerButtonState(latestPlayerStatus);
  await refreshPlayer({ silent: false });
});

qs("#pause-button").addEventListener("click", async () => {
  const shouldPause = latestPlayerStatus === 1;
  const endpoint = shouldPause ? "/api/pause" : "/api/resume";
  const currentPosition = currentProgressSeconds();
  latestPlayerStatus = shouldPause ? 2 : 1;
  playerActionHoldUntil = Date.now() + 3500;
  playerPositionSec = currentPosition;
  playerStartedAtMs = shouldPause ? 0 : Date.now() - currentPosition * 1000;
  setPlayerButtonState(latestPlayerStatus);
  await runAction(shouldPause ? "正在暂停..." : "正在继续...", endpoint, new FormData());
  latestPlayerStatus = shouldPause ? 2 : 1;
  playerActionHoldUntil = Date.now() + 3500;
  playerStartedAtMs = shouldPause ? 0 : Date.now() - playerPositionSec * 1000;
  setPlayerButtonState(latestPlayerStatus);
  await refreshPlayer({ silent: false });
});

qs("#refresh-player-button").addEventListener("click", async () => {
  actionResult.textContent = "正在刷新播放器状态...";
  try {
    await refreshPlayer({ silent: false });
  } catch (error) {
    actionResult.textContent = `失败：${error.message}`;
  }
});

async function commitSeek(value) {
  if (!playerDurationSec) {
    actionResult.textContent = "当前歌曲还没有可用时长，暂时不能拖动进度。";
    return;
  }
  const position = Math.max(0, Math.min(Number(value) || 0, playerDurationSec));
  const body = new FormData();
  body.set("position", String(position));
  playerPositionSec = position;
  playerStartedAtMs = Date.now() - position * 1000;
  latestPlayerStatus = 1;
  setPlayerButtonState(latestPlayerStatus);
  setProgressUI(position);
  await runAction(`正在跳转到 ${formatTime(position)}...`, "/api/seek", body);
  playerActionHoldUntil = Date.now() + 3500;
  await refreshPlayer({ silent: false });
}

if (progressSlider) {
  progressSlider.addEventListener("pointerdown", () => {
    progressEditing = true;
  });
  progressSlider.addEventListener("input", () => {
    const value = Number(progressSlider.value) || 0;
    const ratio = playerDurationSec > 0 ? Math.min(100, (value / playerDurationSec) * 100) : 0;
    progressSlider.style.setProperty("--value", `${ratio}%`);
    const bar = qs("#player-progress");
    if (bar) bar.style.width = `${ratio}%`;
    setText("#player-elapsed", formatTime(value));
  });
  progressSlider.addEventListener("pointerup", async () => {
    lastProgressPointerUp = Date.now();
    const value = progressSlider.value;
    progressEditing = false;
    await commitSeek(value);
  });
  progressSlider.addEventListener("change", async () => {
    if (Date.now() - lastProgressPointerUp < 600) return;
    progressEditing = false;
    await commitSeek(progressSlider.value);
  });
}

qs("#clear-events-button").addEventListener("click", async () => {
  try {
    await getJson("/api/events/clear", { method: "POST", body: new FormData() });
    renderEvents([]);
  } catch (error) {
    actionResult.textContent = `日志清理失败：${error.message}`;
  }
});

volumeSlider.addEventListener("pointerdown", () => {
  volumeEditing = true;
});

volumeSlider.addEventListener("pointerup", () => {
  lastVolumePointerUp = Date.now();
  volumeHoldUntil = Date.now() + 5000;
  commitVolume(volumeSlider.value);
  setTimeout(() => {
    volumeEditing = false;
  }, 1800);
});

volumeSlider.addEventListener("input", () => {
  previewVolume(volumeSlider.value);
});

volumeSlider.addEventListener("change", () => {
  if (Date.now() - lastVolumePointerUp < 600) return;
  commitVolume(volumeSlider.value);
});

const volumeInput = getVolumeInput();
if (volumeInput) {
  volumeInput.addEventListener("focus", () => {
    volumeEditing = true;
  });
  volumeInput.addEventListener("blur", () => {
    volumeHoldUntil = Date.now() + 5000;
    setLocalVolume(volumeInput.value);
    commitVolume(volumeInput.value);
    setTimeout(() => {
      volumeEditing = false;
    }, 1800);
  });
  volumeInput.addEventListener("input", () => {
    previewVolume(volumeInput.value);
  });
  volumeInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commitVolume(volumeInput.value);
      volumeInput.blur();
    }
  });
}

qs("#account-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runAction("正在保存账号并启动登录...", "/api/setup/account", new FormData(event.currentTarget));
});

qs("#edit-account-button").addEventListener("click", () => {
  qs("#account-locked").classList.add("hidden");
  qs("#account-form").classList.remove("hidden");
});

qs("#runtime-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runAction("正在保存策略...", "/api/setup/runtime", new FormData(event.currentTarget));
});

refresh();
refreshPlayer({ silent: false }).catch(() => {});
setInterval(refresh, 4000);
setInterval(() => refreshPlayer({ silent: true }).catch(() => {}), 7000);
setInterval(updateProgress, 1000);
