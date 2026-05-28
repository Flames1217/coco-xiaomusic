import { invoke } from "@tauri-apps/api/core";
import type { AppStatus, EventItem, SearchItem, Song, UpdateInfo } from "./types";

export async function getStatus(): Promise<AppStatus> {
  return invoke<AppStatus>("get_status");
}

export async function getEvents(limit = 120): Promise<EventItem[]> {
  const response = await invoke<{ items: EventItem[] }>("get_events", { limit });
  return response.items ?? [];
}

export async function search(keyword: string, providers: string[] = []): Promise<SearchItem[]> {
  const response = await invoke<{ items: SearchItem[] }>("search", { payload: { keyword, providers } });
  return response.items ?? [];
}

export async function playKeyword(keyword: string) {
  return invoke("play_keyword", { payload: { keyword } });
}

export async function playSelected(song: Song) {
  return invoke("play_selected", { payload: { song } });
}

export async function syncTrayPlaylist(playlist: Song[], current_index: number) {
  return invoke("sync_tray_playlist", { payload: { playlist, current_index } });
}

export async function handleCloseChoice(behavior: "tray" | "exit", remember: boolean) {
  return invoke("handle_close_choice", { payload: { behavior, remember } });
}

export async function getAutoStart(): Promise<boolean> {
  return invoke<boolean>("get_auto_start");
}

export async function setAutoStart(enabled: boolean): Promise<boolean> {
  return invoke<boolean>("set_auto_start", { payload: { enabled } });
}

export async function pausePlayback() {
  return invoke("pause_playback");
}

export async function resumePlayback() {
  return invoke("resume_playback");
}

export async function stopPlayback() {
  return invoke("stop_playback");
}

export async function seekPlayback(seconds: number) {
  return invoke("seek_playback", { payload: { seconds } });
}

export async function setVolume(volume: number) {
  return invoke("set_volume", { payload: { volume } });
}

export async function saveAccount(account: string, password: string, hostname: string) {
  return invoke("save_account", { payload: { account, password, hostname } });
}

export async function saveDevices(selected_dids: string[], manual_target_dids: string[]) {
  return invoke("save_devices", { payload: { selected_dids, manual_target_dids } });
}

export async function refreshDevices() {
  return invoke("refresh_devices");
}

export async function renameDevice(did: string, alias: string) {
  return invoke("rename_device", { payload: { did, alias } });
}

export async function saveStrategy(
  coco_base: string,
  admin_port: number,
  takeover_mode: string,
  delay: number,
  search_tts: string,
  found_tts: string,
  error_tts: string,
  coco_keywords: string[]
) {
  return invoke("save_strategy", {
    payload: { coco_base, admin_port, takeover_mode, delay, search_tts, found_tts, error_tts, coco_keywords }
  });
}

export async function clearEvents() {
  return invoke("clear_events");
}

export async function testCocoConnection(coco_base: string) {
  return invoke("test_coco_connection", { payload: { coco_base } });
}

export async function checkForUpdates(): Promise<UpdateInfo> {
  return invoke<UpdateInfo>("check_for_updates");
}

export async function installUpdate(download_url: string) {
  return invoke("install_update", { payload: { download_url } });
}
