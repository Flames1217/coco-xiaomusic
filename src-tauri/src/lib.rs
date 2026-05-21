use rand::{distributions::Alphanumeric, Rng};
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    env, fs, io,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::Duration,
};
use tauri::{Manager, State, WebviewUrl, WebviewWindowBuilder};
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

#[derive(Debug, Serialize)]
struct SidecarBootstrap {
    base_url: String,
    token: String,
    home: String,
}

impl AppState {
    fn new() -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("reqwest client"),
            sidecar: Mutex::new(None),
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
    let mut command = Command::new(python);
    command
        .arg("-m")
        .arg("coco_sidecar.api")
        .current_dir(&home)
        .env("PYTHONPATH", &sidecar_dir)
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
async fn get_status(state: State<'_, AppState>) -> Result<Value, String> {
    state.get("/status").await
}

#[tauri::command]
async fn get_events(limit: Option<u16>, state: State<'_, AppState>) -> Result<Value, String> {
    let limit = limit.unwrap_or(120);
    state.get(&format!("/events?limit={limit}")).await
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
async fn clear_events(state: State<'_, AppState>) -> Result<Value, String> {
    state.delete("/events").await
}

pub fn run() {
    tauri::Builder::default()
        .manage(AppState::new())
        .setup(|app| {
            let home =
                prepare_home().map_err(|error| io::Error::new(io::ErrorKind::Other, error))?;
            WebviewWindowBuilder::new(app.handle(), "main", WebviewUrl::App("index.html".into()))
                .title("coco-xiaomusic")
                .inner_size(1480.0, 840.0)
                .min_inner_size(1180.0, 720.0)
                .data_directory(home.join("webview"))
                .build()?;

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
