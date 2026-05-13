const qs = (selector) => document.querySelector(selector);
const actionResult = qs("#action-result");
const eventsNode = qs("#events");
const keywordInput = qs("#keyword");

async function getJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || data.error || "请求失败");
  }
  return data;
}

function setText(selector, value) {
  qs(selector).textContent = value || "--";
}

function renderStatus(payload) {
  const { status, settings } = payload;
  setText("#device-id", status.selected_dids.length ? `${status.selected_dids.length} 台` : "未选择");
  setText("#coco-base", status.coco_base);
  setText("#last-keyword", status.last_keyword || "暂无");
  setText("#last-playback", status.last_playback_at || "暂无");
  setText("#delay-sec", `${settings.official_answer_delay_sec}s`);
  setText("#search-tts", settings.search_tts);
  setText("#found-tts", settings.found_tts);
  setText("#keywords", settings.coco_keywords.join(" / "));
  qs("#runtime-coco-base").value = settings.coco_base || "";
  qs("#runtime-delay").value = settings.official_answer_delay_sec ?? 2.4;
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
    runtimeCopy.textContent = "等待 xiaomusic 就绪";
    runtimeDot.style.background = "#b45309";
  }

  renderOnboarding(status);
  renderAccountState(status);
}

function setStep(selector, state, copy) {
  const node = qs(selector);
  node.classList.remove("done", "warn", "error");
  if (state) node.classList.add(state);
  qs(`${selector}-copy`).textContent = copy;
}

function renderOnboarding(status) {
  setStep(
    "#step-account",
    status.account_configured ? "done" : "error",
    status.account_configured ? "账号已保存" : "请在下方输入小米账号和密码"
  );
  setStep(
    "#step-token",
    status.token_present ? "done" : "warn",
    status.token_present ? "token 文件已生成" : "保存账号后，系统会尝试登录并生成 token"
  );
  setStep(
    "#step-device",
    status.selected_device_present ? "done" : "warn",
    status.selected_device_present ? "目标设备已选中" : "登录成功后，从下方设备列表选择音箱"
  );
  setStep(
    "#step-ready",
    status.ready && status.selected_device_present ? "done" : status.startup_error ? "error" : "warn",
    status.ready && status.selected_device_present
      ? "服务已就绪，可以语音或后台推送"
      : status.selected_device_present
        ? "服务仍在启动"
        : "先选择目标音箱，之后才能开始播放"
  );

  const devices = qs("#device-list");
  devices.innerHTML = "";
  if (!status.devices.length) {
    devices.innerHTML = '<div class="device-item"><strong>设备列表为空</strong><span>保存账号后等待登录完成</span><span>或检查账号与网络</span></div>';
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
      <div>
        <div class="device-roles">
          <label><input type="checkbox" data-role="selected" data-did="${device.did || ""}" ${selected ? "checked" : ""}>参与语音监听</label>
          <label><input type="checkbox" data-role="manual" data-did="${device.did || ""}" ${manualTarget ? "checked" : ""}>后台默认推送</label>
        </div>
        <div class="device-actions">
          <input value="${device.alias || ""}" placeholder="本地别名">
          <button type="button" data-action="rename">${device.alias ? "保存别名" : "命名"}</button>
        </div>
      </div>
    `;
    row.querySelector('[data-action="rename"]').addEventListener("click", async () => {
      const body = new FormData();
      body.set("did", device.did || "");
      body.set("alias", row.querySelector("input").value || "");
      actionResult.textContent = "正在保存设备别名...";
      try {
        const data = await getJson("/api/setup/device-alias", { method: "POST", body });
        actionResult.textContent = JSON.stringify(data, null, 2);
        await refresh();
      } catch (error) {
        actionResult.textContent = `失败：${error.message}`;
      }
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

function renderEvents(items) {
  eventsNode.innerHTML = "";
  if (!items.length) {
    eventsNode.innerHTML = '<div class="event info"><span>暂无</span><span>INFO</span><span>等待第一条事件</span></div>';
    return;
  }
  for (const item of items) {
    const row = document.createElement("article");
    row.className = `event ${item.level}`;
    row.innerHTML = `
      <span>${item.at.slice(11)}</span>
      <span class="event-level">${item.level.toUpperCase()}</span>
      <span>${item.message}</span>
    `;
    eventsNode.appendChild(row);
  }
}

async function refresh() {
  const [status, events] = await Promise.all([
    getJson("/api/status"),
    getJson("/api/events"),
  ]);
  renderStatus(status);
  renderEvents(events.items);
}

qs("#play-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  actionResult.textContent = "正在用 coco 第一条推送...";
  try {
    const body = new FormData(event.currentTarget);
    const data = await getJson("/api/play", { method: "POST", body });
    actionResult.textContent = JSON.stringify(data, null, 2);
    await refresh();
  } catch (error) {
    actionResult.textContent = `失败：${error.message}`;
  }
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
  actionResult.textContent = "正在保存多设备方案...";
  try {
    const data = await getJson("/api/setup/devices", { method: "POST", body });
    actionResult.textContent = JSON.stringify(data, null, 2);
    await refresh();
  } catch (error) {
    actionResult.textContent = `失败：${error.message}`;
  }
});

qs("#preview-button").addEventListener("click", async () => {
  const keyword = keywordInput.value.trim();
  if (!keyword) {
    actionResult.textContent = "请先输入关键词。";
    return;
  }
  qs("#preview-title").textContent = "正在预览...";
  qs("#preview-copy").textContent = "正在读取 coco 返回的全部结果。";
  qs("#preview-list").innerHTML = "";
  try {
    const data = await getJson(`/api/search-preview?keyword=${encodeURIComponent(keyword)}`);
    const items = data.items || [];
    qs("#preview-title").textContent = items.length ? `已找到 ${items.length} 条结果` : "没有结果";
    qs("#preview-copy").textContent = items.length ? "语音命令默认播放第一条；前端可以手动推送任意一条。" : "coco 没有返回搜索结果。";
    const list = qs("#preview-list");
    list.innerHTML = "";
    for (const [index, entry] of items.entries()) {
      const song = entry.item || {};
      const row = document.createElement("article");
      row.className = "preview-item";
      const badge = entry.is_first
        ? `<span class="badge ${entry.has_url ? "good" : "bad"}">${entry.has_url ? "语音默认" : "第一条无直链"}</span>`
        : '<span class="badge">可选</span>';
      row.innerHTML = `
        <span class="preview-rank">#${index + 1}</span>
        <div>
          <div class="preview-title">${song.title || "未知标题"} - ${song.artist || "未知歌手"}</div>
          <div class="preview-copy">provider=${song.provider || "--"} · id=${song.id || "--"}</div>
        </div>
        <div class="result-actions">
          ${badge}
          <button type="button" data-song-id="${song.id || ""}" data-provider="${song.provider || ""}" data-title="${song.title || ""}" data-artist="${song.artist || ""}">播放这首</button>
        </div>
      `;
      row.querySelector("button").addEventListener("click", async (event) => {
        const target = event.currentTarget;
        const body = new FormData();
        body.set("song_id", target.dataset.songId || "");
        body.set("provider", target.dataset.provider || "");
        body.set("title", target.dataset.title || "");
        body.set("artist", target.dataset.artist || "");
        actionResult.textContent = "正在推送选中的歌曲...";
        try {
          const data = await getJson("/api/play-selected", { method: "POST", body });
          actionResult.textContent = JSON.stringify(data, null, 2);
          await refresh();
        } catch (error) {
          actionResult.textContent = `失败：${error.message}`;
        }
      });
      list.appendChild(row);
    }
  } catch (error) {
    qs("#preview-title").textContent = "预览失败";
    qs("#preview-copy").textContent = error.message;
  }
});

qs("#stop-button").addEventListener("click", async () => {
  actionResult.textContent = "正在停止小爱播放...";
  try {
    const data = await getJson("/api/stop", { method: "POST" });
    actionResult.textContent = JSON.stringify(data, null, 2);
    await refresh();
  } catch (error) {
    actionResult.textContent = `失败：${error.message}`;
  }
});

qs("#account-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  actionResult.textContent = "正在保存账号并启动登录...";
  try {
    const data = await getJson("/api/setup/account", {
      method: "POST",
      body: new FormData(event.currentTarget),
    });
    actionResult.textContent = JSON.stringify(data, null, 2);
    await refresh();
  } catch (error) {
    actionResult.textContent = `失败：${error.message}`;
  }
});

qs("#edit-account-button").addEventListener("click", () => {
  qs("#account-locked").classList.add("hidden");
  qs("#account-form").classList.remove("hidden");
});

qs("#runtime-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  actionResult.textContent = "正在保存播放策略...";
  try {
    const data = await getJson("/api/setup/runtime", {
      method: "POST",
      body: new FormData(event.currentTarget),
    });
    actionResult.textContent = JSON.stringify(data, null, 2);
    await refresh();
  } catch (error) {
    actionResult.textContent = `失败：${error.message}`;
  }
});

refresh();
setInterval(refresh, 4000);
