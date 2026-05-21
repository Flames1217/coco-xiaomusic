export type Level = "ok" | "warn" | "error" | "info" | string;

export interface Song {
  id?: string;
  provider?: string;
  title?: string;
  artist?: string;
  album?: string;
  cover?: string;
  duration?: string | number;
  audio_type?: string;
  bitrate?: string;
  quality?: string;
}

export interface SearchItem {
  item: Song;
  is_first?: boolean;
  has_url?: boolean | null;
  preview_reason?: string;
}

export interface Device {
  did: string;
  device_id?: string;
  name?: string;
  raw_name?: string;
  alias?: string;
  hardware?: string;
}

export interface EventItem {
  at: string;
  level: Level;
  message: string;
  keyword?: string;
  song?: Song;
}

export interface SettingsPublic {
  account?: string;
  password?: string;
  selected_dids?: string[];
  manual_target_dids?: string[];
  hostname?: string;
  xiaomusic_port?: number;
  admin_port?: number;
  coco_base?: string;
  takeover_mode?: "keyword" | "all" | "off" | string;
  official_answer_delay_sec?: number;
  search_tts?: string;
  found_tts?: string;
  error_tts?: string;
  edge_tts_voice?: string;
  coco_keywords?: string[];
}

export interface AppStatus {
  ready?: boolean;
  starting?: boolean;
  sidecar_ready?: boolean;
  startup_error?: string;
  last_keyword?: string;
  last_song?: Song | null;
  last_error?: string;
  last_duration?: number;
  last_position?: number;
  last_used_url?: string;
  last_volume?: number;
  playback_paused?: boolean;
  selected_dids?: string[];
  manual_target_dids?: string[];
  coco_base?: string;
  token_present?: boolean;
  account_configured?: boolean;
  selected_device_present?: boolean;
  stream_url?: string;
  devices?: Device[];
  settings?: SettingsPublic;
}

export interface UpdateInfo {
  current_version: string;
  latest_version: string;
  has_update: boolean;
  release_name: string;
  notes: string;
  published_at: string;
  html_url: string;
  portable_url: string;
  portable_name: string;
  installer_url: string;
  installer_name: string;
  portable_size: number;
  installer_size: number;
}
