use rand::{distributions::Alphanumeric, Rng};
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    env, fs, io,
    net::Ipv4Addr,
    path::PathBuf,
    process::{Child, Command, Output, Stdio},
    sync::Mutex,
    time::Duration,
};
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem, Submenu},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, State, WebviewUrl, WebviewWindowBuilder, WindowEvent,
};
use tokio::time::sleep;

#[derive(Debug)]
struct SidecarProcess {
    child: Child,
    base_url: String,
    token: String,
}

#[derive(Debug)]
struct AppState {
    client: reqwest::Client,
    sidecar: Mutex<Option<SidecarProcess>>,
    tray: Mutex<TrayState>,
    close_behavior: Mutex<Option<CloseBehavior>>,
    runtime_home: Mutex<Option<PathBuf>>,
    quitting: Mutex<bool>,
}

#[derive(Debug, Default)]
struct TrayState {
    playlist: Vec<Value>,
    current_index: i32,
}

#[derive(Debug, Deserialize)]
struct KeywordPayload {
    keyword: String,
    #[serde(default)]
    providers: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct SongPayload {
    song: Value,
}

#[derive(Debug, Deserialize)]
struct TrayPlaylistPayload {
    playlist: Vec<Value>,
    current_index: i32,
}

#[derive(Debug, Deserialize)]
struct CloseChoicePayload {
    behavior: String,
    remember: bool,
}

#[derive(Debug, Deserialize)]
struct AutoStartPayload {
    enabled: bool,
}

#[derive(Debug, Deserialize, Serialize)]
struct AppPrefs {
    close_behavior: Option<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CloseBehavior {
    Tray,
    Exit,
}

impl CloseBehavior {
    fn from_str(value: &str) -> Option<Self> {
        match value {
            "tray" | "minimize" => Some(Self::Tray),
            "exit" | "quit" => Some(Self::Exit),
            _ => None,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Tray => "tray",
            Self::Exit => "exit",
        }
    }
}
#[derive(Debug, Deserialize)]
struct SeekPayload {
    seconds: f64,
}

#[derive(Debug, Deserialize)]
struct VolumePayload {
    volume: i32,
}

#[derive(Debug, Deserialize)]
struct AccountPayload {
    account: String,
    password: String,
    hostname: String,
}

#[derive(Debug, Deserialize)]
struct DevicesPayload {
    selected_dids: Vec<String>,
    manual_target_dids: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct AliasPayload {
    did: String,
    alias: String,
}

#[derive(Debug, Deserialize)]
struct StrategyPayload {
    coco_base: String,
    admin_port: i32,
    takeover_mode: String,
    delay: f64,
    search_tts: String,
    found_tts: String,
    error_tts: String,
    coco_keywords: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct CocoTestPayload {
    coco_base: String,
}

#[derive(Debug, Deserialize)]
struct InstallUpdatePayload {
    download_url: String,
}

#[derive(Debug, Serialize)]
struct SidecarBootstrap {
    base_url: String,
    token: String,
    home: String,
}

#[derive(Debug, Deserialize)]
struct GithubRelease {
    tag_name: String,
    name: Option<String>,
    body: Option<String>,
    html_url: Option<String>,
    published_at: Option<String>,
    assets: Vec<GithubAsset>,
}

#[derive(Debug, Deserialize)]
struct GithubAsset {
    name: String,
    browser_download_url: String,
    size: Option<u64>,
}

#[derive(Debug, Serialize)]
struct UpdateInfo {
    current_version: String,
    latest_version: String,
    has_update: bool,
    release_name: String,
    notes: String,
    published_at: String,
    html_url: String,
    portable_url: String,
    portable_name: String,
    installer_url: String,
    installer_name: String,
    portable_size: u64,
    installer_size: u64,
}

impl AppState {
    fn new() -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(Duration::from_secs(600))
                .build()
                .expect("reqwest client"),
            sidecar: Mutex::new(None),
            tray: Mutex::new(TrayState {
                playlist: Vec::new(),
                current_index: -1,
            }),
            close_behavior: Mutex::new(None),
            runtime_home: Mutex::new(None),
            quitting: Mutex::new(false),
        }
    }

    fn set_runtime_home(&self, home: PathBuf) -> Result<(), String> {
        let mut guard = self
            .runtime_home
            .lock()
            .map_err(|_| "运行目录状态锁异常".to_string())?;
        *guard = Some(home);
        Ok(())
    }

    fn runtime_home(&self) -> Result<PathBuf, String> {
        let guard = self
            .runtime_home
            .lock()
            .map_err(|_| "运行目录状态锁异常".to_string())?;
        guard
            .clone()
            .ok_or_else(|| "运行目录尚未初始化".to_string())
    }

    fn close_behavior(&self) -> Result<Option<CloseBehavior>, String> {
        let guard = self
            .close_behavior
            .lock()
            .map_err(|_| "关闭偏好状态锁异常".to_string())?;
        Ok(*guard)
    }

    fn set_close_behavior(&self, behavior: Option<CloseBehavior>) -> Result<(), String> {
        let mut guard = self
            .close_behavior
            .lock()
            .map_err(|_| "关闭偏好状态锁异常".to_string())?;
        *guard = behavior;
        Ok(())
    }

    fn is_quitting(&self) -> bool {
        self.quitting.lock().map(|guard| *guard).unwrap_or(false)
    }

    fn mark_quitting(&self) {
        if let Ok(mut guard) = self.quitting.lock() {
            *guard = true;
        }
    }

    fn snapshot(&self) -> Result<(String, String), String> {
        let guard = self
            .sidecar
            .lock()
            .map_err(|_| "后台服务状态锁异常".to_string())?;
        let sidecar = guard
            .as_ref()
            .ok_or_else(|| "后台服务未启动".to_string())?;
        Ok((sidecar.base_url.clone(), sidecar.token.clone()))
    }

    async fn get(&self, path: &str) -> Result<Value, String> {
        let (base_url, token) = self.snapshot()?;
        let response = self
            .client
            .get(format!("{base_url}{path}"))
            .headers(auth_headers(&token)?)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        decode_response(response).await
    }

    async fn delete(&self, path: &str) -> Result<Value, String> {
        let (base_url, token) = self.snapshot()?;
        let response = self
            .client
            .delete(format!("{base_url}{path}"))
            .headers(auth_headers(&token)?)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        decode_response(response).await
    }

    async fn post(&self, path: &str, body: Value) -> Result<Value, String> {
        let (base_url, token) = self.snapshot()?;
        let response = self
            .client
            .post(format!("{base_url}{path}"))
            .headers(auth_headers(&token)?)
            .json(&body)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        decode_response(response).await
    }
}

impl Drop for AppState {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.sidecar.lock() {
            if let Some(mut sidecar) = guard.take() {
                let _ = sidecar.child.kill();
                let _ = sidecar.child.wait();
            }
        }
    }
}

fn auth_headers(token: &str) -> Result<HeaderMap, String> {
    let mut headers = HeaderMap::new();
    let value =
        HeaderValue::from_str(&format!("Bearer {token}")).map_err(|error| error.to_string())?;
    headers.insert(AUTHORIZATION, value);
    Ok(headers)
}

async fn decode_response(response: reqwest::Response) -> Result<Value, String> {
    let status = response.status();
    let body = response.text().await.map_err(|error| error.to_string())?;
    if !status.is_success() {
        return Err(format!("后台服务 HTTP {status}: {body}"));
    }
    serde_json::from_str(&body)
        .map_err(|error| format!("后台服务返回了无效 JSON: {error}; body={body}"))
}

fn random_token() -> String {
    rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(48)
        .map(char::from)
        .collect()
}

const AUTO_START_REG_PATH: &str = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";
const AUTO_START_REG_NAME: &str = "coco-xiaomusic";

fn hidden_command_output(command: &mut Command) -> io::Result<Output> {
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command.output()
}

fn startup_command_value() -> Result<String, String> {
    let exe = env::current_exe().map_err(|error| format!("读取程序路径失败: {error}"))?;
    Ok(format!("\"{}\"", exe.display()))
}

fn query_auto_start_value() -> Result<Option<String>, String> {
    let mut command = Command::new("reg");
    command
        .arg("query")
        .arg(AUTO_START_REG_PATH)
        .arg("/v")
        .arg(AUTO_START_REG_NAME);
    let output = hidden_command_output(&mut command)
        .map_err(|error| format!("读取开机自启状态失败: {error}"))?;
    if !output.status.success() {
        return Ok(None);
    }
    let text = String::from_utf8_lossy(&output.stdout);
    for line in text.lines() {
        if !line.contains(AUTO_START_REG_NAME) {
            continue;
        }
        if let Some((_, value)) = line.split_once("REG_SZ") {
            return Ok(Some(value.trim().to_string()));
        }
    }
    Ok(None)
}

fn is_auto_start_enabled() -> Result<bool, String> {
    let Some(value) = query_auto_start_value()? else {
        return Ok(false);
    };
    let expected = startup_command_value()?.to_lowercase().replace('/', "\\");
    Ok(value.to_lowercase().replace('/', "\\") == expected)
}

fn set_auto_start_enabled(enabled: bool) -> Result<bool, String> {
    if enabled {
        let mut command = Command::new("reg");
        command
            .arg("add")
            .arg(AUTO_START_REG_PATH)
            .arg("/v")
            .arg(AUTO_START_REG_NAME)
            .arg("/t")
            .arg("REG_SZ")
            .arg("/d")
            .arg(startup_command_value()?)
            .arg("/f");
        let output = hidden_command_output(&mut command)
            .map_err(|error| format!("开启开机自启失败: {error}"))?;
        if !output.status.success() {
            let error = String::from_utf8_lossy(&output.stderr);
            return Err(format!("开启开机自启失败: {}", error.trim()));
        }
    } else {
        let mut command = Command::new("reg");
        command
            .arg("delete")
            .arg(AUTO_START_REG_PATH)
            .arg("/v")
            .arg(AUTO_START_REG_NAME)
            .arg("/f");
        let output = hidden_command_output(&mut command)
            .map_err(|error| format!("关闭开机自启失败: {error}"))?;
        if !output.status.success() && query_auto_start_value()?.is_some() {
            let error = String::from_utf8_lossy(&output.stderr);
            return Err(format!("关闭开机自启失败: {}", error.trim()));
        }
    }
    is_auto_start_enabled()
}

fn resolve_python() -> String {
    env::var("COCO_XIAOMUSIC_PYTHON").unwrap_or_else(|_| "python".to_string())
}

fn resolve_project_dir() -> Result<PathBuf, String> {
    if let Ok(path) = env::var("COCO_XIAOMUSIC_PROJECT_DIR") {
        return Ok(PathBuf::from(path));
    }

    if cfg!(debug_assertions) {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        return Ok(manifest_dir
            .parent()
            .ok_or_else(|| "missing project root".to_string())?
            .to_path_buf());
    }

    let exe = env::current_exe().map_err(|error| format!("current exe unavailable: {error}"))?;
    let exe_dir = exe
        .parent()
        .ok_or_else(|| "current exe has no parent directory".to_string())?
        .to_path_buf();

    if matches!(
        exe_dir.file_name().and_then(|name| name.to_str()),
        Some("debug" | "release")
    ) {
        if let Some(target_dir) = exe_dir.parent() {
            if target_dir.file_name().and_then(|name| name.to_str()) == Some("target") {
                if let Some(src_tauri_dir) = target_dir.parent() {
                    if src_tauri_dir.file_name().and_then(|name| name.to_str()) == Some("src-tauri")
                    {
                        if let Some(project_dir) = src_tauri_dir.parent() {
                            return Ok(project_dir.to_path_buf());
                        }
                    }
                }
            }
        }
    }

    Ok(exe_dir)
}

fn resolve_sidecar_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    if let Ok(path) = env::var("COCO_XIAOMUSIC_SIDECAR_DIR") {
        return Ok(PathBuf::from(path));
    }

    let project_dir = resolve_project_dir()?;
    let exe_dir = env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|parent| parent.to_path_buf()));
    let resource_dir = app.path().resource_dir().ok();

    let mut candidates = vec![project_dir.join("sidecar")];
    if let Some(path) = &resource_dir {
        candidates.push(path.join("sidecar"));
        candidates.push(path.join("_up_").join("sidecar"));
    }
    if let Some(path) = &exe_dir {
        candidates.push(path.join("sidecar"));
        candidates.push(path.join("_up_").join("sidecar"));
    }

    for candidate in candidates {
        if candidate.join("coco_sidecar").exists() {
            return Ok(candidate);
        }
    }

    Err(format!(
        "后台服务代码目录未找到: {}",
        project_dir.display()
    ))
}

fn prepare_home() -> Result<PathBuf, String> {
    let home = if let Ok(path) = env::var("COCO_XIAOMUSIC_HOME") {
        PathBuf::from(path)
    } else {
        resolve_project_dir()?.join("runtime")
    };
    for item in [
        "data",
        "conf",
        "music",
        "music/tmp",
        "music/cache",
        "logs",
        "tmp",
        "cache",
        "cache/pip",
        "pycache",
        "webview",
        "win-appdata/roaming",
        "win-appdata/local",
        "home",
    ] {
        fs::create_dir_all(home.join(item))
            .map_err(|error| format!("create runtime dir failed: {error}"))?;
    }
    Ok(home)
}

fn detect_lan_hostname() -> String {
    #[cfg(windows)]
    {
        let mut command = Command::new("ipconfig");
        command
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);

        if let Ok(output) = command.output() {
            let text = String::from_utf8_lossy(&output.stdout);
            for part in text.split(|ch: char| !(ch.is_ascii_digit() || ch == '.')) {
                if let Ok(address) = part.parse::<Ipv4Addr>() {
                    if !address.is_loopback() && !address.is_link_local() && is_private_ipv4(address) {
                        return format!("http://{address}");
                    }
                }
            }
        }
    }
    "http://127.0.0.1".to_string()
}

fn is_private_ipv4(address: Ipv4Addr) -> bool {
    let octets = address.octets();
    octets[0] == 10
        || (octets[0] == 172 && (16..=31).contains(&octets[1]))
        || (octets[0] == 192 && octets[1] == 168)
}

fn extract_json_string(text: &str, key: &str) -> Option<String> {
    let pattern = format!("\"{key}\"");
    let start = text.find(&pattern)?;
    let after_key = &text[start + pattern.len()..];
    let colon = after_key.find(':')?;
    let mut value = after_key[colon + 1..].trim_start().chars();
    if value.next()? != '"' {
        return None;
    }
    let mut output = String::new();
    let mut escaped = false;
    for ch in value {
        if escaped {
            output.push(ch);
            escaped = false;
            continue;
        }
        if ch == '\\' {
            escaped = true;
            continue;
        }
        if ch == '"' {
            return Some(output);
        }
        output.push(ch);
    }
    None
}

fn extract_json_number(text: &str, key: &str) -> Option<i64> {
    let pattern = format!("\"{key}\"");
    let start = text.find(&pattern)?;
    let after_key = &text[start + pattern.len()..];
    let colon = after_key.find(':')?;
    let number = after_key[colon + 1..]
        .trim_start()
        .chars()
        .take_while(|ch| ch.is_ascii_digit())
        .collect::<String>();
    number.parse().ok()
}

fn salvage_settings_text(text: &str) -> Value {
    let mut settings = json!({});
    for key in ["account", "password", "hostname", "admin_host", "coco_base", "takeover_mode"] {
        if let Some(value) = extract_json_string(text, key) {
            settings[key] = json!(value);
        }
    }
    for key in ["xiaomusic_port", "admin_port", "last_volume"] {
        if let Some(value) = extract_json_number(text, key) {
            settings[key] = json!(value);
        }
    }
    settings
}

fn fallback_status(home: &PathBuf, error: String) -> Value {
    let settings_path = home.join("data").join("app_settings.json");
    let mut settings = fs::read_to_string(&settings_path)
        .ok()
        .map(|content| {
            serde_json::from_str::<Value>(&content)
                .unwrap_or_else(|_| salvage_settings_text(&content))
        })
        .unwrap_or_else(|| json!({}));

    if !settings.is_object() {
        settings = json!({});
    }
    if settings.get("hostname").and_then(Value::as_str).unwrap_or("").is_empty() {
        settings["hostname"] = json!(detect_lan_hostname());
    }
    if settings.get("coco_base").and_then(Value::as_str).unwrap_or("").is_empty() {
        settings["coco_base"] = json!("https://coco.viper3.top");
    }
    if settings.get("admin_port").and_then(Value::as_i64).is_none() {
        settings["admin_port"] = json!(8088);
    }

    json!({
        "ready": false,
        "starting": true,
        "sidecar_ready": false,
        "startup_error": error,
        "settings": settings,
        "selected_dids": settings.get("selected_dids").cloned().unwrap_or_else(|| json!([])),
        "manual_target_dids": settings.get("manual_target_dids").cloned().unwrap_or_else(|| json!([])),
        "coco_base": settings.get("coco_base").cloned().unwrap_or_else(|| json!("https://coco.viper3.top")),
        "last_volume": settings.get("last_volume").cloned().unwrap_or_else(|| json!(50)),
        "devices": []
    })
}

fn compare_versions(left: &str, right: &str) -> std::cmp::Ordering {
    let parse = |value: &str| {
        value
            .trim()
            .trim_start_matches('v')
            .split(|ch: char| !ch.is_ascii_digit())
            .filter(|part| !part.is_empty())
            .map(|part| part.parse::<u32>().unwrap_or(0))
            .collect::<Vec<_>>()
    };
    let mut left_parts = parse(left);
    let mut right_parts = parse(right);
    let max_len = left_parts.len().max(right_parts.len()).max(3);
    left_parts.resize(max_len, 0);
    right_parts.resize(max_len, 0);
    left_parts.cmp(&right_parts)
}

fn release_asset<'a>(assets: &'a [GithubAsset], portable: bool) -> Option<&'a GithubAsset> {
    assets.iter().find(|asset| {
        let name = asset.name.to_lowercase();
        if portable {
            name.contains("portable") && name.ends_with(".zip")
        } else {
            (name.contains("setup") || name.contains("installer") || name.contains("安装"))
                && name.ends_with(".exe")
        }
    })
}

fn safe_download_name(url: &str) -> String {
    let name = url
        .rsplit('/')
        .next()
        .unwrap_or("coco-xiaomusic-update.zip")
        .split('?')
        .next()
        .unwrap_or("coco-xiaomusic-update.zip")
        .chars()
        .filter(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '.' | '-' | '_'))
        .collect::<String>();
    if name.is_empty() {
        "coco-xiaomusic-update.zip".to_string()
    } else {
        name
    }
}

fn updater_script() -> &'static str {
    r#"
param(
  [Parameter(Mandatory=$true)][int]$ProcessId,
  [Parameter(Mandatory=$true)][string]$ZipPath,
  [Parameter(Mandatory=$true)][string]$AppDir,
  [Parameter(Mandatory=$true)][string]$ExeName
)
$ErrorActionPreference = 'Stop'
$resolvedAppDir = (Resolve-Path -LiteralPath $AppDir).Path
$resolvedZip = (Resolve-Path -LiteralPath $ZipPath).Path
$updateRoot = Join-Path $resolvedAppDir 'runtime\update'
$stage = Join-Path $updateRoot 'stage'
try {
  Wait-Process -Id $ProcessId -Timeout 45 -ErrorAction SilentlyContinue
} catch {}
if (Test-Path -LiteralPath $stage) {
  Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Expand-Archive -LiteralPath $resolvedZip -DestinationPath $stage -Force
$candidate = Get-ChildItem -LiteralPath $stage -Recurse -Filter $ExeName | Select-Object -First 1
if (-not $candidate) {
  throw "更新包中没有找到 $ExeName"
}
$sourceRoot = $candidate.Directory.FullName
if (-not $sourceRoot.StartsWith($stage, [StringComparison]::OrdinalIgnoreCase)) {
  throw "更新包路径异常"
}
Get-ChildItem -LiteralPath $sourceRoot -Force | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $resolvedAppDir -Recurse -Force
}
Start-Process -FilePath (Join-Path $resolvedAppDir $ExeName) -WorkingDirectory $resolvedAppDir
"#
}

fn prefs_path(home: &std::path::Path) -> PathBuf {
    home.join("data").join("app_prefs.json")
}

fn load_close_behavior(home: &std::path::Path) -> Option<CloseBehavior> {
    let text = fs::read_to_string(prefs_path(home)).ok()?;
    let prefs = serde_json::from_str::<AppPrefs>(&text).ok()?;
    CloseBehavior::from_str(prefs.close_behavior.as_deref()?)
}

fn save_close_behavior(home: &std::path::Path, behavior: CloseBehavior) -> Result<(), String> {
    let prefs = AppPrefs {
        close_behavior: Some(behavior.as_str().to_string()),
    };
    let path = prefs_path(home);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("保存关闭偏好失败: {error}"))?;
    }
    let text = serde_json::to_string_pretty(&prefs)
        .map_err(|error| format!("保存关闭偏好失败: {error}"))?;
    fs::write(path, text).map_err(|error| format!("保存关闭偏好失败: {error}"))
}

fn menu_text(value: &str, max_chars: usize) -> String {
    let cleaned = value.replace('&', "&&");
    let mut text: String = cleaned.chars().take(max_chars).collect();
    if cleaned.chars().count() > max_chars {
        text.push_str("...");
    }
    text
}

fn song_menu_text(song: &Value, index: usize, current_index: i32) -> String {
    let title = song
        .get("title")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("未知歌曲");
    let artist = song
        .get("artist")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("--");
    let marker = if current_index == index as i32 {
        "正在播放 "
    } else {
        ""
    };
    menu_text(
        &format!("{:02}. {marker}{title} - {artist}", index + 1),
        48,
    )
}

fn build_tray_menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let menu = Menu::with_id(app, "tray-menu")?;
    menu.append(&MenuItem::with_id(
        app,
        "tray-open",
        "打开主窗口",
        true,
        None::<&str>,
    )?)?;
    let auto_start_enabled = is_auto_start_enabled().unwrap_or(false);
    menu.append(&MenuItem::with_id(
        app,
        "tray-autostart",
        if auto_start_enabled {
            "开机自启：已开启"
        } else {
            "开机自启：已关闭"
        },
        true,
        None::<&str>,
    )?)?;
    menu.append(&PredefinedMenuItem::separator(app)?)?;
    menu.append(&MenuItem::with_id(
        app,
        "tray-prev",
        "上一首",
        true,
        None::<&str>,
    )?)?;
    menu.append(&MenuItem::with_id(
        app,
        "tray-toggle",
        "播放 / 暂停",
        true,
        None::<&str>,
    )?)?;
    menu.append(&MenuItem::with_id(
        app,
        "tray-next",
        "下一首",
        true,
        None::<&str>,
    )?)?;
    menu.append(&PredefinedMenuItem::separator(app)?)?;

    let playlist_menu = Submenu::with_id(app, "tray-playlist", "播放列表", true)?;
    let (playlist, current_index) = {
        let state = app.state::<AppState>();
        let snapshot = match state.tray.lock() {
            Ok(guard) => (guard.playlist.clone(), guard.current_index),
            Err(_) => (Vec::new(), -1),
        };
        snapshot
    };
    if playlist.is_empty() {
        playlist_menu.append(&MenuItem::with_id(
            app,
            "tray-empty",
            "播放列表为空",
            false,
            None::<&str>,
        )?)?;
    } else {
        for (index, song) in playlist.iter().take(25).enumerate() {
            playlist_menu.append(&MenuItem::with_id(
                app,
                format!("tray-play-{index}"),
                song_menu_text(song, index, current_index),
                true,
                None::<&str>,
            )?)?;
        }
        if playlist.len() > 25 {
            playlist_menu.append(&MenuItem::with_id(
                app,
                "tray-more",
                format!("还有 {} 首，请在主窗口查看", playlist.len() - 25),
                false,
                None::<&str>,
            )?)?;
        }
    }
    menu.append(&playlist_menu)?;
    menu.append(&PredefinedMenuItem::separator(app)?)?;
    menu.append(&MenuItem::with_id(
        app,
        "tray-exit",
        "退出应用并关闭服务",
        true,
        None::<&str>,
    )?)?;
    Ok(menu)
}

fn update_tray_menu(app: &AppHandle) -> Result<(), String> {
    if let Some(tray) = app.tray_by_id("main") {
        let menu = build_tray_menu(app).map_err(|error| error.to_string())?;
        tray.set_menu(Some(menu)).map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn hide_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
}

fn emit_tray_action(app: &AppHandle, index: Option<i32>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.emit("coco-tray-action", json!({ "index": index, "refresh": true }));
    }
}

async fn play_tray_index(app: AppHandle, index: usize) {
    let song = {
        let state = app.state::<AppState>();
        let mut guard = match state.tray.lock() {
            Ok(guard) => guard,
            Err(_) => return,
        };
        let song = guard.playlist.get(index).cloned();
        if song.is_some() {
            guard.current_index = index as i32;
        }
        song
    };
    if let Some(song) = song {
        let _ = app
            .state::<AppState>()
            .post("/play/selected", json!({ "song": song }))
            .await;
        let _ = update_tray_menu(&app);
        emit_tray_action(&app, Some(index as i32));
    }
}

async fn play_tray_offset(app: AppHandle, offset: i32) {
    let next_index = {
        let state = app.state::<AppState>();
        let guard = match state.tray.lock() {
            Ok(guard) => guard,
            Err(_) => return,
        };
        if guard.playlist.is_empty() {
            return;
        }
        let len = guard.playlist.len() as i32;
        let current = if guard.current_index >= 0 {
            guard.current_index
        } else {
            0
        };
        (current + offset).rem_euclid(len) as usize
    };
    play_tray_index(app, next_index).await;
}

async fn toggle_tray_playback(app: AppHandle) {
    let state = app.state::<AppState>();
    let status = match state.get("/status").await {
        Ok(status) => status,
        Err(_) => return,
    };
    let has_playback = status
        .get("last_used_url")
        .and_then(Value::as_str)
        .map(|value| !value.is_empty())
        .unwrap_or(false);
    let paused = status
        .get("playback_paused")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let path = if has_playback && !paused {
        "/playback/pause"
    } else {
        "/playback/resume"
    };
    let _ = state.post(path, json!({})).await;
    emit_tray_action(&app, None);
}

fn create_tray(app: &tauri::App) -> tauri::Result<()> {
    let menu = build_tray_menu(app.handle())?;
    let mut builder = TrayIconBuilder::with_id("main")
        .tooltip("coco-xiaomusic")
        .menu(&menu)
        .show_menu_on_left_click(true);
    if let Some(icon) = app.default_window_icon().cloned() {
        builder = builder.icon(icon);
    }
    builder
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn handle_tray_menu(app: &AppHandle, id: &str) {
    match id {
        "tray-open" => show_main_window(app),
        "tray-autostart" => {
            let next_enabled = !is_auto_start_enabled().unwrap_or(false);
            if let Ok(enabled) = set_auto_start_enabled(next_enabled) {
                let _ = update_tray_menu(app);
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.emit("coco-auto-start-changed", json!({ "enabled": enabled }));
                }
            }
        }
        "tray-prev" => {
            let handle = app.clone();
            tauri::async_runtime::spawn(async move { play_tray_offset(handle, -1).await });
        }
        "tray-toggle" => {
            let handle = app.clone();
            tauri::async_runtime::spawn(async move { toggle_tray_playback(handle).await });
        }
        "tray-next" => {
            let handle = app.clone();
            tauri::async_runtime::spawn(async move { play_tray_offset(handle, 1).await });
        }
        "tray-exit" => {
            let state = app.state::<AppState>();
            state.mark_quitting();
            app.exit(0);
        }
        _ if id.starts_with("tray-play-") => {
            if let Ok(index) = id.trim_start_matches("tray-play-").parse::<usize>() {
                let handle = app.clone();
                tauri::async_runtime::spawn(async move { play_tray_index(handle, index).await });
            }
        }
        _ => {}
    }
}

fn spawn_sidecar(
    app: &tauri::AppHandle,
    state: &AppState,
    home: PathBuf,
) -> Result<SidecarBootstrap, String> {
    let port = portpicker::pick_unused_port().ok_or_else(|| "no free local port".to_string())?;
    let token = random_token();
    let base_url = format!("http://127.0.0.1:{port}");
    let sidecar_dir = resolve_sidecar_dir(app)?;
    if !sidecar_dir.join("coco_sidecar").exists() {
        return Err(format!(
            "后台服务代码目录未找到: {}",
            sidecar_dir.display()
        ));
    }

    let python = resolve_python();
    let vendor_dir = sidecar_dir.join("vendor");
    let python_path = if vendor_dir.exists() {
        env::join_paths([vendor_dir.as_path(), sidecar_dir.as_path()])
            .map_err(|error| format!("构建后台服务依赖路径失败: {error}"))?
    } else {
        sidecar_dir.clone().into_os_string()
    };
    let mut command = Command::new(python);
    command
        .arg("-m")
        .arg("coco_sidecar.api")
        .current_dir(&home)
        .env("PYTHONPATH", python_path)
        .env("COCO_XIAOMUSIC_HOME", &home)
        .env("COCO_XIAOMUSIC_CONTROL_HOST", "127.0.0.1")
        .env("COCO_XIAOMUSIC_CONTROL_PORT", port.to_string())
        .env("COCO_XIAOMUSIC_API_TOKEN", &token)
        .env("TEMP", home.join("tmp"))
        .env("TMP", home.join("tmp"))
        .env("HOME", home.join("home"))
        .env("USERPROFILE", home.join("home"))
        .env("APPDATA", home.join("win-appdata").join("roaming"))
        .env("LOCALAPPDATA", home.join("win-appdata").join("local"))
        .env("XDG_CACHE_HOME", home.join("cache"))
        .env("PIP_CACHE_DIR", home.join("cache").join("pip"))
        .env("PYTHONPYCACHEPREFIX", home.join("pycache"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    let child = command
        .spawn()
        .map_err(|error| format!("启动后台服务失败: {error}"))?;
    let bootstrap = SidecarBootstrap {
        base_url: base_url.clone(),
        token: token.clone(),
        home: home.display().to_string(),
    };
    let mut guard = state
        .sidecar
        .lock()
        .map_err(|_| "后台服务状态锁异常".to_string())?;
    *guard = Some(SidecarProcess {
        child,
        base_url,
        token,
    });
    Ok(bootstrap)
}

async fn wait_for_health(state: &AppState) -> Result<(), String> {
    for _ in 0..80 {
        match state.get("/health").await {
            Ok(_) => return Ok(()),
            Err(_) => sleep(Duration::from_millis(150)).await,
        }
    }
    Err("后台服务健康检查超时".to_string())
}

#[tauri::command]
fn get_auto_start() -> Result<bool, String> {
    is_auto_start_enabled()
}

#[tauri::command]
fn set_auto_start(payload: AutoStartPayload, app: AppHandle) -> Result<bool, String> {
    let enabled = set_auto_start_enabled(payload.enabled)?;
    update_tray_menu(&app)?;
    Ok(enabled)
}

#[tauri::command]
async fn get_status(state: State<'_, AppState>) -> Result<Value, String> {
    match state.get("/status").await {
        Ok(value) => Ok(value),
        Err(error) => {
            let home = state.runtime_home()?;
            Ok(fallback_status(&home, error))
        }
    }
}

#[tauri::command]
async fn get_events(limit: Option<u16>, state: State<'_, AppState>) -> Result<Value, String> {
    let limit = limit.unwrap_or(120);
    match state.get(&format!("/events?limit={limit}")).await {
        Ok(value) => Ok(value),
        Err(_) => Ok(json!({ "items": [] })),
    }
}

#[tauri::command]
async fn search(payload: KeywordPayload, state: State<'_, AppState>) -> Result<Value, String> {
    state
        .post("/search", json!({ "keyword": payload.keyword, "providers": payload.providers }))
        .await
}

#[tauri::command]
async fn play_keyword(
    payload: KeywordPayload,
    state: State<'_, AppState>,
) -> Result<Value, String> {
    state
        .post("/play/keyword", json!({ "keyword": payload.keyword }))
        .await
}

#[tauri::command]
async fn play_selected(payload: SongPayload, state: State<'_, AppState>) -> Result<Value, String> {
    state
        .post("/play/selected", json!({ "song": payload.song }))
        .await
}

#[tauri::command]
fn sync_tray_playlist(
    payload: TrayPlaylistPayload,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<(), String> {
    {
        let mut guard = state
            .tray
            .lock()
            .map_err(|_| "播放列表状态锁异常".to_string())?;
        guard.playlist = payload.playlist;
        guard.current_index = payload.current_index;
    }
    update_tray_menu(&app)
}

#[tauri::command]
fn handle_close_choice(
    payload: CloseChoicePayload,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let behavior = CloseBehavior::from_str(&payload.behavior)
        .ok_or_else(|| "未知关闭方式".to_string())?;
    if payload.remember {
        let home = state.runtime_home()?;
        save_close_behavior(&home, behavior)?;
        state.set_close_behavior(Some(behavior))?;
    }
    match behavior {
        CloseBehavior::Tray => hide_main_window(&app),
        CloseBehavior::Exit => {
            state.mark_quitting();
            app.exit(0);
        }
    }
    Ok(())
}

#[tauri::command]
async fn pause_playback(state: State<'_, AppState>) -> Result<Value, String> {
    state.post("/playback/pause", json!({})).await
}

#[tauri::command]
async fn resume_playback(state: State<'_, AppState>) -> Result<Value, String> {
    state.post("/playback/resume", json!({})).await
}

#[tauri::command]
async fn stop_playback(state: State<'_, AppState>) -> Result<Value, String> {
    state.post("/playback/stop", json!({})).await
}

#[tauri::command]
async fn seek_playback(payload: SeekPayload, state: State<'_, AppState>) -> Result<Value, String> {
    state
        .post("/playback/seek", json!({ "seconds": payload.seconds }))
        .await
}

#[tauri::command]
async fn set_volume(payload: VolumePayload, state: State<'_, AppState>) -> Result<Value, String> {
    state
        .post("/playback/volume", json!({ "volume": payload.volume }))
        .await
}

#[tauri::command]
async fn save_account(
    payload: AccountPayload,
    state: State<'_, AppState>,
) -> Result<Value, String> {
    state
        .post(
            "/account",
            json!({
                "account": payload.account,
                "password": payload.password,
                "hostname": payload.hostname
            }),
        )
        .await
}

#[tauri::command]
async fn save_devices(
    payload: DevicesPayload,
    state: State<'_, AppState>,
) -> Result<Value, String> {
    state
        .post(
            "/devices",
            json!({
                "selected_dids": payload.selected_dids,
                "manual_target_dids": payload.manual_target_dids
            }),
        )
        .await
}

#[tauri::command]
async fn refresh_devices(state: State<'_, AppState>) -> Result<Value, String> {
    state.post("/devices/refresh", json!({})).await
}

#[tauri::command]
async fn rename_device(payload: AliasPayload, state: State<'_, AppState>) -> Result<Value, String> {
    state
        .post(
            &format!(
                "/devices/{}/alias",
                url::form_urlencoded::byte_serialize(payload.did.as_bytes()).collect::<String>()
            ),
            json!({ "alias": payload.alias }),
        )
        .await
}

#[tauri::command]
async fn save_strategy(
    payload: StrategyPayload,
    state: State<'_, AppState>,
) -> Result<Value, String> {
    state
        .post(
            "/strategy",
            json!({
                "coco_base": payload.coco_base,
                "admin_port": payload.admin_port,
                "takeover_mode": payload.takeover_mode,
                "delay": payload.delay,
                "search_tts": payload.search_tts,
                "found_tts": payload.found_tts,
                "error_tts": payload.error_tts,
                "coco_keywords": payload.coco_keywords
            }),
        )
        .await
}

#[tauri::command]
async fn test_coco_connection(
    payload: CocoTestPayload,
    state: State<'_, AppState>,
) -> Result<Value, String> {
    state
        .post("/test/coco", json!({ "coco_base": payload.coco_base }))
        .await
}

#[tauri::command]
async fn check_for_updates(state: State<'_, AppState>) -> Result<UpdateInfo, String> {
    let current_version = env!("CARGO_PKG_VERSION").to_string();
    let release = state
        .client
        .get("https://api.github.com/repos/Flames1217/coco-xiaomusic/releases/latest")
        .header("User-Agent", "coco-xiaomusic")
        .send()
        .await
        .map_err(|error| format!("检查更新失败: {error}"))?;
    if !release.status().is_success() {
        return Err(format!("检查更新失败: GitHub HTTP {}", release.status()));
    }
    let release = release
        .json::<GithubRelease>()
        .await
        .map_err(|error| format!("解析更新信息失败: {error}"))?;
    let latest_version = release.tag_name.trim_start_matches('v').to_string();
    let portable = release_asset(&release.assets, true);
    let installer = release_asset(&release.assets, false);
    Ok(UpdateInfo {
        current_version: current_version.clone(),
        latest_version: latest_version.clone(),
        has_update: compare_versions(&latest_version, &current_version).is_gt(),
        release_name: release.name.unwrap_or_else(|| release.tag_name.clone()),
        notes: release.body.unwrap_or_default(),
        published_at: release.published_at.unwrap_or_default(),
        html_url: release.html_url.unwrap_or_default(),
        portable_url: portable
            .map(|asset| asset.browser_download_url.clone())
            .unwrap_or_default(),
        portable_name: portable.map(|asset| asset.name.clone()).unwrap_or_default(),
        installer_url: installer
            .map(|asset| asset.browser_download_url.clone())
            .unwrap_or_default(),
        installer_name: installer.map(|asset| asset.name.clone()).unwrap_or_default(),
        portable_size: portable.and_then(|asset| asset.size).unwrap_or(0),
        installer_size: installer.and_then(|asset| asset.size).unwrap_or(0),
    })
}

#[tauri::command]
async fn install_update(
    payload: InstallUpdatePayload,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<(), String> {
    if !payload.download_url.starts_with("https://") {
        return Err("更新下载地址无效".to_string());
    }
    let home = state.runtime_home()?;
    let update_dir = home.join("update");
    fs::create_dir_all(&update_dir).map_err(|error| format!("创建更新目录失败: {error}"))?;
    let archive_path = update_dir.join(safe_download_name(&payload.download_url));
    let response = state
        .client
        .get(&payload.download_url)
        .header("User-Agent", "coco-xiaomusic")
        .send()
        .await
        .map_err(|error| format!("下载更新失败: {error}"))?;
    if !response.status().is_success() {
        return Err(format!("下载更新失败: HTTP {}", response.status()));
    }
    let bytes = response
        .bytes()
        .await
        .map_err(|error| format!("读取更新包失败: {error}"))?;
    fs::write(&archive_path, bytes).map_err(|error| format!("保存更新包失败: {error}"))?;

    let exe_path = env::current_exe().map_err(|error| format!("读取程序路径失败: {error}"))?;
    let app_dir = exe_path
        .parent()
        .ok_or_else(|| "程序目录无效".to_string())?
        .to_path_buf();
    let exe_name = exe_path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "程序文件名无效".to_string())?
        .to_string();
    let script_path = update_dir.join("apply_update.ps1");
    fs::write(&script_path, updater_script())
        .map_err(|error| format!("写入更新脚本失败: {error}"))?;

    let mut command = Command::new("powershell");
    command
        .arg("-NoProfile")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-File")
        .arg(&script_path)
        .arg("-ProcessId")
        .arg(std::process::id().to_string())
        .arg("-ZipPath")
        .arg(&archive_path)
        .arg("-AppDir")
        .arg(&app_dir)
        .arg("-ExeName")
        .arg(exe_name)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command
        .spawn()
        .map_err(|error| format!("启动更新器失败: {error}"))?;
    state.mark_quitting();
    app.exit(0);
    Ok(())
}

#[tauri::command]
async fn clear_events(state: State<'_, AppState>) -> Result<Value, String> {
    state.delete("/events").await
}

pub fn run() {
    tauri::Builder::default()
        .manage(AppState::new())
        .on_menu_event(|app, event| handle_tray_menu(app, event.id().as_ref()))
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                let state = app.state::<AppState>();
                if state.is_quitting() {
                    return;
                }
                match state.close_behavior().unwrap_or(None) {
                    Some(CloseBehavior::Tray) => {
                        api.prevent_close();
                        hide_main_window(app);
                    }
                    Some(CloseBehavior::Exit) => {
                        api.prevent_close();
                        state.mark_quitting();
                        app.exit(0);
                    }
                    None => {
                        api.prevent_close();
                        let _ = window.show();
                        let _ = window.unminimize();
                        let _ = window.set_focus();
                        let _ = window.emit("coco-close-requested", json!({}));
                    }
                }
            }
        })
        .setup(|app| {
            let home =
                prepare_home().map_err(|error| io::Error::new(io::ErrorKind::Other, error))?;
            {
                let state = app.state::<AppState>();
                state
                    .set_runtime_home(home.clone())
                    .map_err(|error| io::Error::new(io::ErrorKind::Other, error))?;
                state
                    .set_close_behavior(load_close_behavior(&home))
                    .map_err(|error| io::Error::new(io::ErrorKind::Other, error))?;
            }
            WebviewWindowBuilder::new(app.handle(), "main", WebviewUrl::App("index.html".into()))
                .title("coco-xiaomusic")
                .inner_size(1480.0, 840.0)
                .min_inner_size(1180.0, 720.0)
                .data_directory(home.join("webview"))
                .build()?;
            create_tray(app)?;

            let state = app.state::<AppState>();
            let bootstrap = spawn_sidecar(app.handle(), state.inner(), home)
                .map_err(|error| io::Error::new(io::ErrorKind::Other, error))?;
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(error) = wait_for_health(handle.state::<AppState>().inner()).await {
                    eprintln!("{error}");
                }
            });
            let _ = bootstrap;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_status,
            get_events,
            search,
            play_keyword,
            play_selected,
            sync_tray_playlist,
            handle_close_choice,
            pause_playback,
            resume_playback,
            stop_playback,
            seek_playback,
            set_volume,
            save_account,
            save_devices,
            refresh_devices,
            rename_device,
            save_strategy,
            test_coco_connection,
            check_for_updates,
            install_update,
            get_auto_start,
            set_auto_start,
            clear_events
        ])
        .run(tauri::generate_context!())
        .expect("error while running coco-xiaomusic");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn auth_header_uses_bearer_token() {
        let headers = auth_headers("abc").expect("headers");
        assert_eq!(headers.get(AUTHORIZATION).unwrap(), "Bearer abc");
    }

    #[test]
    fn random_token_is_long_enough() {
        assert_eq!(random_token().len(), 48);
    }

    #[test]
    fn debug_sidecar_dir_points_to_project_sidecar() {
        let manifest_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
        assert!(manifest_dir.ends_with("src-tauri"));
    }
}
