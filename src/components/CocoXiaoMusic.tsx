import { useEffect, useMemo, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  Activity,
  ArrowDown,
  Check,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Headphones,
  Home,
  ListMusic,
  Loader2,
  LogOut,
  MoreHorizontal,
  Moon,
  Music2,
  Pause,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Save,
  ScrollText,
  Search,
  Send,
  Settings,
  ShieldAlert,
  SkipBack,
  SkipForward,
  Speaker,
  Square,
  Sun,
  Trash2,
  UploadCloud,
  Volume2,
  VolumeX,
  X
} from "lucide-react";
import {
  checkForUpdates,
  clearEvents,
  getEvents,
  getStatus,
  handleCloseChoice,
  pausePlayback,
  playKeyword,
  playSelected,
  refreshDevices,
  renameDevice,
  resumePlayback,
  saveAccount,
  saveDevices,
  saveStrategy,
  search,
  seekPlayback,
  setVolume,
  syncTrayPlaylist,
  testCocoConnection,
  installUpdate,
  stopPlayback
} from "../lib/api";
import type { AppStatus, Device, EventItem, SearchItem, Song, UpdateInfo } from "../lib/types";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Checkbox } from "./ui/checkbox";
import { Input } from "./ui/input";
import { Slider } from "./ui/slider";
import { Switch } from "./ui/switch";
import { Textarea } from "./ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "./ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from "./ui/dropdown-menu";

type NavItem = "overview" | "search" | "devices" | "logs" | "settings" | "account";
type LogFilter = "all" | "info" | "ok" | "warn" | "error";
type Theme = "dark" | "light";
type Language = "zh" | "en";
type TakeoverMode = "keyword" | "all" | "off";
type ActionResult = { success?: boolean; error?: string; [key: string]: unknown };
type SearchFeedback = { tone: "info" | "success" | "warn" | "error"; message: string };

const playlistStorageKey = "coco-playlist";
const volumeStorageKey = "coco-last-volume";
const presetProviders = [
  { id: "geba", label: "歌曲宝" },
  { id: "gequhai", label: "歌曲海" },
  { id: "bugu", label: "布谷" },
  { id: "qq", label: "QQ音乐" },
  { id: "qqmp3", label: "QQMP3" },
  { id: "migu", label: "咪咕" },
  { id: "liyin", label: "力音" },
  { id: "jianbin-netease", label: "煎饼-网易" },
  { id: "jianbin-qq", label: "煎饼-qq" },
  { id: "jianbin-kugou", label: "煎饼-酷狗" },
  { id: "jianbin-kuwo", label: "煎饼-酷我" }
];

const providerLabels: Record<string, string> = {
  geba: "歌曲宝",
  songbao: "歌曲宝",
  gqb: "歌曲宝",
  gequhai: "歌曲海",
  bugu: "布谷",
  bilibili: "布谷",
  qq: "QQ音乐",
  qqmp3: "QQMP3",
  migu: "咪咕",
  liyin: "力音",
  fangyin: "力音",
  livepoo: "力音",
  netease: "煎饼-网易",
  "jianbin-netease": "煎饼-网易",
  "jianbing-netease": "煎饼-网易",
  "jianbin-wangyi": "煎饼-网易",
  "jianbing-wangyi": "煎饼-网易",
  "jianbin-qq": "煎饼-qq",
  "jianbing-qq": "煎饼-qq",
  kugou: "煎饼-酷狗",
  "jianbin-kugou": "煎饼-酷狗",
  "jianbing-kugou": "煎饼-酷狗",
  kuwo: "煎饼-酷我",
  "jianbin-kuwo": "煎饼-酷我",
  "jianbing-kuwo": "煎饼-酷我",
  coco: "coco"
};

function providerLabel(provider: string | undefined) {
  const value = String(provider || "coco").trim();
  return providerLabels[value.toLowerCase()] || value;
}

const defaultKeywords = ["播放", "放一首", "来一首", "唱", "coco"];

const text = {
  zh: {
    nav: {
      overview: "概览",
      search: "搜索与推送",
      devices: "设备管理",
      logs: "实时日志",
      settings: "策略设置",
      account: "账号授权"
    },
    status: {
      online: "在线",
      starting: "启动中",
      pending: "待处理",
      offline: "离线",
      connected: "已连接",
      connecting: "连接中",
      noDevice: "未选择设备",
      listening: "监听中",
      notListening: "未监听",
      running: "已运行"
    },
    action: {
      refresh: "刷新",
      switchDevice: "切换设备",
      playBest: "播放首选",
      search: "搜索",
      push: "推送",
      addToPlaylist: "加入列表",
      inPlaylist: "已加入",
      playAll: "播放列表",
      clearPlaylist: "清空列表",
      remove: "移除",
      refreshDevices: "刷新设备",
      saveDevices: "保存设备",
      all: "全部",
      autoScroll: "自动滚动",
      clear: "清空",
      test: "测试连接",
      add: "添加",
      saveStrategy: "保存策略",
      openVerify: "打开验证链接",
      copy: "复制链接",
      verifiedRefresh: "我已验证，刷新设备",
      logout: "退出登录",
      saveLogin: "保存并登录",
      close: "关闭",
      ok: "确定"
    },
    label: {
      backend: "后台服务",
      xiaoMusic: "XiaoMusic",
      devices: "设备",
      cocoService: "coco 服务",
      recentCommand: "最近口令",
      searchFeedback: "搜索状态",
      searchResults: "搜索结果",
      searchProviders: "搜索渠道",
      providerFilter: "渠道筛选",
      playlist: "播放列表",
      recentPush: "最近推送",
      recentActivity: "最近活动",
      todayPushes: "今日推送次数",
      voiceHits: "语音命中次数",
      uptime: "服务运行时长",
      discoveredDevices: "已发现设备",
      serviceConfig: "服务配置",
      cocoBase: "coco 服务地址",
      streamPort: "MP3 流服务端口",
      answerDelay: "官方回答延迟秒数",
      takeover: "语音接管",
      takeoverMode: "接管策略",
      keywords: "接管关键词",
      searchTts: "搜索提示话术",
      foundTts: "命中提示话术",
      errorTts: "失败提示话术",
      miVerify: "小米账号需要安全验证",
      miAccount: "小米账号",
      account: "账号",
      password: "密码",
      host: "本机访问地址",
      listen: "监听",
      push: "推送",
      defaultPush: "设为默认推送",
      saveAlias: "保存别名",
      rename: "命名",
      pushTo: "推送至"
    },
    table: {
      index: "#",
      cover: "封面",
      song: "歌曲",
      artist: "歌手",
      duration: "时长",
      source: "来源",
      action: "操作"
    },
    searchState: {
      idle: "输入关键词后按 Enter 或点击搜索",
      searching: "正在搜索「{keyword}」...",
      done: "搜索完成：找到 {count} 首",
      empty: "没有搜到「{keyword}」，换个关键词试试",
      error: "搜索失败：{error}",
      added: "已加入播放列表：{title}",
      duplicate: "播放列表里已经有这首歌了"
    },
    playlist: {
      empty: "播放列表为空",
      hint: "从搜索结果加入歌曲后，可在这里连续切歌",
      count: "{count} 首"
    },
    empty: {
      noSong: "暂无歌曲",
      noCommand: "暂无",
      noPush: "暂无推送记录",
      noActivity: "暂无活动",
      noSearch: "暂无搜索结果",
      noLog: "暂无日志",
      noProviderSearch: "当前渠道暂无搜索结果",
      noDevice: "暂无设备。完成小米安全验证后点击“刷新设备”。",
      unnamedDevice: "未命名设备"
    },
    placeholder: {
      search: "搜索歌曲、歌手或语音口令",
      keyword: "新增关键词",
      alias: "本地别名"
    },
    mode: {
      keyword: "仅关键词接管",
      all: "全部口令接管",
      off: "关闭接管"
    },
    message: {
      connecting: "正在连接后台服务...",
      verify: "小米账号需要安全验证，请到账号授权页处理",
      online: "服务在线",
      waiting: "等待账号或设备配置",
      copied: "验证链接已复制",
      noDeviceToAdd: "当前没有可添加的设备，请先刷新设备"
    },
    dialog: {
      cocoOk: "coco 服务连接成功",
      cocoFail: "coco 服务连接失败",
      statusCode: "HTTP 状态码",
      address: "地址"
    }
  },
  en: {
    nav: {
      overview: "Overview",
      search: "Search & Push",
      devices: "Devices",
      logs: "Live Logs",
      settings: "Strategy",
      account: "Account"
    },
    status: {
      online: "Online",
      starting: "Starting",
      pending: "Action needed",
      offline: "Offline",
      connected: "Connected",
      connecting: "Connecting",
      noDevice: "No device selected",
      listening: "Listening",
      notListening: "Not listening",
      running: "Running"
    },
    action: {
      refresh: "Refresh",
      switchDevice: "Switch device",
      playBest: "Play best",
      search: "Search",
      push: "Push",
      addToPlaylist: "Add",
      inPlaylist: "Added",
      playAll: "Play list",
      clearPlaylist: "Clear list",
      remove: "Remove",
      refreshDevices: "Refresh devices",
      saveDevices: "Save devices",
      all: "All",
      autoScroll: "Auto scroll",
      clear: "Clear",
      test: "Test",
      add: "Add",
      saveStrategy: "Save strategy",
      openVerify: "Open verification",
      copy: "Copy link",
      verifiedRefresh: "Verified, refresh devices",
      logout: "Log out",
      saveLogin: "Save & sign in",
      close: "Close",
      ok: "OK"
    },
    label: {
      backend: "Backend service: ",
      xiaoMusic: "XiaoMusic",
      devices: "Devices",
      cocoService: "coco Service",
      recentCommand: "Last command",
      searchFeedback: "Search status",
      searchResults: "Search results",
      searchProviders: "Search providers",
      providerFilter: "Provider filter",
      playlist: "Playlist",
      recentPush: "Recent pushes",
      recentActivity: "Recent activity",
      todayPushes: "Pushes today",
      voiceHits: "Voice hits",
      uptime: "Service uptime",
      discoveredDevices: "Discovered devices",
      serviceConfig: "Service config",
      cocoBase: "coco service URL",
      streamPort: "MP3 stream port",
      answerDelay: "Official answer delay",
      takeover: "Voice takeover",
      takeoverMode: "Takeover mode",
      keywords: "Takeover keywords",
      searchTts: "Searching prompt",
      foundTts: "Found prompt",
      errorTts: "Error prompt",
      miVerify: "Xiaomi account verification required",
      miAccount: "Xiaomi account",
      account: "Account",
      password: "Password",
      host: "Local access address",
      listen: "Listen",
      push: "Push",
      defaultPush: "Set as default",
      saveAlias: "Save alias",
      rename: "Rename",
      pushTo: "Push to"
    },
    table: {
      index: "#",
      cover: "Cover",
      song: "Song",
      artist: "Artist",
      duration: "Length",
      source: "Source",
      action: "Action"
    },
    searchState: {
      idle: "Type keywords, then press Enter or click Search",
      searching: "Searching for \"{keyword}\"...",
      done: "Search finished: {count} songs found",
      empty: "No results for \"{keyword}\". Try another keyword.",
      error: "Search failed: {error}",
      added: "Added to playlist: {title}",
      duplicate: "This song is already in the playlist"
    },
    playlist: {
      empty: "Playlist is empty",
      hint: "Add songs from search results, then switch tracks here",
      count: "{count} songs"
    },
    empty: {
      noSong: "No song",
      noCommand: "None",
      noPush: "No push history",
      noActivity: "No activity",
      noSearch: "No search results",
      noLog: "No logs",
      noProviderSearch: "No results for this provider",
      noDevice: "No devices. Finish Xiaomi verification, then click Refresh devices.",
      unnamedDevice: "Unnamed device"
    },
    placeholder: {
      search: "Search song, artist, or voice command",
      keyword: "Add keyword",
      alias: "Local alias"
    },
    mode: {
      keyword: "Keyword only",
      all: "All commands",
      off: "Off"
    },
    message: {
      connecting: "Connecting to backend service...",
      verify: "Xiaomi account verification is required. Open the Account page.",
      online: "Service online",
      waiting: "Waiting for account or device config",
      copied: "Verification link copied",
      noDeviceToAdd: "No device to add. Refresh devices first."
    },
    dialog: {
      cocoOk: "coco service connected",
      cocoFail: "coco service failed",
      statusCode: "HTTP status",
      address: "URL"
    }
  }
} as const;

const navItems: Array<{ id: NavItem; icon: typeof Home }> = [
  { id: "overview", icon: Home },
  { id: "search", icon: Search },
  { id: "devices", icon: Radio },
  { id: "logs", icon: ScrollText },
  { id: "settings", icon: Settings },
  { id: "account", icon: ShieldAlert }
];

function extractFirstUrl(value: string | undefined): string {
  const match = String(value ?? "").match(/https?:\/\/\S+/);
  return match?.[0] ?? "";
}

function formatTime(value: number): string {
  const seconds = Math.max(0, Math.floor(value || 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function localDateKey(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseLocalTimestamp(value: string | undefined): Date | null {
  if (!value) return null;
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
  if (!match) return null;
  const [, year, month, day, hour, minute, second] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second));
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatUptime(startedAt: string | undefined): string {
  const started = parseLocalTimestamp(startedAt);
  if (!started) return "--";
  const total = Math.max(0, Math.floor((Date.now() - started.getTime()) / 1000));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (days > 0) return `${days}天 ${hours}小时`;
  if (hours > 0) return `${hours}小时 ${minutes}分钟`;
  if (minutes > 0) return `${minutes}分钟 ${seconds}秒`;
  return `${seconds}秒`;
}

function durationText(value: unknown): string {
  if (typeof value === "number") return formatTime(value > 10000 ? value / 1000 : value);
  const text = String(value ?? "").trim();
  return text || "--:--";
}

function levelLabel(level: string): string {
  const upper = level.toUpperCase();
  if (upper === "OK") return "OK";
  if (upper === "WARN") return "WARN";
  if (upper === "ERROR") return "ERROR";
  return "INFO";
}

function levelTone(level: string) {
  const label = levelLabel(level);
  if (label === "OK") return "bg-emerald-500/15 text-emerald-500 border-emerald-500/20";
  if (label === "WARN") return "bg-amber-500/15 text-amber-500 border-amber-500/20";
  if (label === "ERROR") return "bg-red-500/15 text-red-500 border-red-500/20";
  return "bg-blue-500/15 text-blue-500 border-blue-500/20";
}

function songArtist(song: Song | null | undefined): string {
  return song?.artist || "--";
}

function songKey(song: Song | null | undefined): string {
  return [
    song?.provider || "coco",
    song?.id || "",
    song?.title || "",
    song?.artist || ""
  ].join("|");
}

function formatMessage(template: string, values: Record<string, string | number>): string {
  return Object.entries(values).reduce(
    (text, [key, value]) => text.replaceAll(`{${key}}`, String(value)),
    template
  );
}

function formatFileSize(value: number): string {
  if (!value) return "--";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function loadPlaylist(): Song[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(playlistStorageKey) || "[]");
    return Array.isArray(parsed) ? parsed.filter((song) => song && typeof song === "object") : [];
  } catch {
    return [];
  }
}

function loadSavedVolume(): number {
  const value = Number(localStorage.getItem(volumeStorageKey) ?? 50);
  return Number.isFinite(value) ? Math.max(0, Math.min(100, Math.round(value))) : 50;
}

export default function CocoXiaoMusic() {
  const [activeNav, setActiveNav] = useState<NavItem>("overview");
  const [theme, setTheme] = useState<Theme>("light");
  const [language] = useState<Language>("zh");
  const t = text[language];
  const [status, setStatus] = useState<AppStatus>({});
  const [events, setEvents] = useState<EventItem[]>([]);
  const [results, setResults] = useState<SearchItem[]>([]);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [selectedProviders, setSelectedProviders] = useState<Set<string>>(new Set());
  const [providerFilter, setProviderFilter] = useState("all");
  const [searching, setSearching] = useState(false);
  const [searchFeedback, setSearchFeedback] = useState<SearchFeedback | null>(null);
  const [playlist, setPlaylist] = useState<Song[]>(loadPlaylist);
  const [playlistIndex, setPlaylistIndex] = useState(-1);
  const [playlistPanelOpen, setPlaylistPanelOpen] = useState(false);
  const [volumePanelOpen, setVolumePanelOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string>(t.message.connecting);
  const [dialog, setDialog] = useState<{ title: string; message: string; tone: "success" | "error" } | null>(null);
  const [closePromptOpen, setClosePromptOpen] = useState(false);
  const [rememberCloseChoice, setRememberCloseChoice] = useState(false);
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);
  const [updateRead, setUpdateRead] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [logFilter, setLogFilter] = useState<LogFilter>("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [volume, setLocalVolume] = useState(loadSavedVolume);
  const [progress, setProgress] = useState(0);
  const [account, setAccount] = useState("");
  const [password, setPasswordValue] = useState("");
  const [hostname, setHostname] = useState("");
  const [cocoBase, setCocoBase] = useState("");
  const [adminPort, setAdminPort] = useState("8088");
  const [takeoverMode, setTakeoverMode] = useState<TakeoverMode>("keyword");
  const [delay, setDelay] = useState("0");
  const [searchTts, setSearchTts] = useState("");
  const [foundTts, setFoundTts] = useState("");
  const [errorTts, setErrorTts] = useState("");
  const [keywords, setKeywords] = useState<string[]>(defaultKeywords);
  const [keywordDraft, setKeywordDraft] = useState("");
  const [selectedDids, setSelectedDids] = useState<Set<string>>(new Set());
  const [manualTargetDids, setManualTargetDids] = useState<Set<string>>(new Set());
  const [aliases, setAliases] = useState<Record<string, string>>({});
  const formsHydrated = useRef(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const updateCheckedRef = useRef(false);
  const previousVolumeRef = useRef(loadSavedVolume() > 0 ? loadSavedVolume() : 50);

  const isDark = theme === "dark";
  const closeCopy = language === "zh"
    ? {
        title: "关闭 coco-xiaomusic？",
        message: "可以最小化到右下角托盘继续运行，也可以退出应用并关闭后台服务。",
        remember: "记住我的选择",
        tray: "最小化到右下角",
        exit: "退出应用"
      }
    : {
        title: "Close coco-xiaomusic?",
        message: "Keep it running in the system tray, or exit the app and stop the background service.",
        remember: "Remember my choice",
        tray: "Minimize to tray",
        exit: "Exit app"
      };
  const devices = status.devices ?? [];
  const currentSong = status.last_song ?? null;
  const isPlaying = Boolean(status.last_used_url && !status.playback_paused);
  const duration = Number(status.last_duration ?? 0);
  const position = Number(status.last_position ?? 0);
  const verificationUrl = extractFirstUrl(status.startup_error || toast);
  const readyLabel = status.ready ? t.status.online : status.starting ? t.status.starting : status.startup_error ? t.status.pending : t.status.offline;
  const activeDeviceName =
    devices.find((device) => manualTargetDids.has(device.did))?.name || devices[0]?.name || t.status.noDevice;
  const targetDevice = devices.find((device) => manualTargetDids.has(device.did)) || devices[0];
  const providerCounts = useMemo(() => {
    const counts = new Map<string, number>();
    results.forEach((result) => {
      const provider = result.item.provider || "coco";
      counts.set(provider, (counts.get(provider) ?? 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [results]);
  const filteredResults = useMemo(() => {
    if (providerFilter === "all") return results;
    return results.filter((result) => (result.item.provider || "coco") === providerFilter);
  }, [providerFilter, results]);
  const selectedResult = filteredResults[selectedIndex]?.item;
  const playlistKeys = useMemo(() => new Set(playlist.map((song) => songKey(song))), [playlist]);
  const selectedResultInPlaylist = selectedResult ? playlistKeys.has(songKey(selectedResult)) : false;
  const activeSearchProviders = useMemo(() => [...selectedProviders], [selectedProviders]);
  const today = localDateKey();
  const todayPushes = events.filter((event) => event.at?.startsWith(today) && Boolean(event.song)).length;
  const voiceHits = events.filter((event) => event.keyword || event.message.includes("语音") || event.message.includes("关键词")).length;
  const serviceUptime = formatUptime(status.service_started_at);

  const filteredLogs = useMemo(() => {
    return events.filter((event) => logFilter === "all" || levelLabel(event.level).toLowerCase() === logFilter);
  }, [events, logFilter]);

  const recentSongs = useMemo(() => {
    const seen = new Set<string>();
    return events
      .map((event) => event.song)
      .filter((song): song is Song => Boolean(song?.title))
      .filter((song) => {
        const key = `${song.title}-${song.artist}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .slice(0, 4);
  }, [events]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.classList.toggle("dark", isDark);
    if ("__TAURI_INTERNALS__" in window) {
      getCurrentWindow().setTheme(isDark ? "dark" : "light").catch(() => undefined);
    }
  }, [isDark, theme]);

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [autoScroll, filteredLogs.length]);

  useEffect(() => {
    if (duration > 0) setProgress(Math.min(100, (position / duration) * 100));
  }, [duration, position]);

  useEffect(() => {
    if (typeof status.last_volume === "number") {
      const nextVolume = Math.max(0, Math.min(100, Math.round(status.last_volume)));
      setLocalVolume(nextVolume);
      if (nextVolume > 0) previousVolumeRef.current = nextVolume;
      localStorage.setItem(volumeStorageKey, String(nextVolume));
    }
  }, [status.last_volume]);

  useEffect(() => {
    if (volume > 0) previousVolumeRef.current = volume;
    localStorage.setItem(volumeStorageKey, String(volume));
  }, [volume]);

  useEffect(() => {
    localStorage.setItem(playlistStorageKey, JSON.stringify(playlist));
    if (playlist.length === 0) setPlaylistIndex(-1);
    else if (playlistIndex >= playlist.length) setPlaylistIndex(playlist.length - 1);
  }, [playlist, playlistIndex]);

  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    syncTrayPlaylist(playlist, playlistIndex).catch(() => undefined);
  }, [playlist, playlistIndex]);

  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    let unlistenClose: (() => void) | undefined;
    let unlistenTray: (() => void) | undefined;
    listen("coco-close-requested", () => {
      setClosePromptOpen(true);
    }).then((cleanup) => {
      unlistenClose = cleanup;
    });
    listen<{ index?: number; refresh?: boolean }>("coco-tray-action", (event) => {
      if (typeof event.payload?.index === "number") {
        setPlaylistIndex(event.payload.index);
      }
      if (event.payload?.refresh) {
        refresh(true);
      }
    }).then((cleanup) => {
      unlistenTray = cleanup;
    });
    return () => {
      unlistenClose?.();
      unlistenTray?.();
    };
  }, []);

  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window) || updateCheckedRef.current) return;
    updateCheckedRef.current = true;
    window.setTimeout(() => {
      checkForUpdates()
        .then((info) => {
          if (info.has_update) {
            setUpdateInfo(info);
            setUpdateRead(false);
            setUpdateDialogOpen(true);
          }
        })
        .catch(() => undefined);
    }, 2500);
  }, []);

  useEffect(() => {
    setSelectedIndex(0);
  }, [providerFilter]);

  function hydrateForms(next: AppStatus, force = false) {
    const settings = next.settings ?? {};
    if (!force && formsHydrated.current) return;
    setAccount(settings.account ?? "");
    setPasswordValue(settings.password ?? "");
    setHostname(settings.hostname ?? "");
    setCocoBase(settings.coco_base ?? next.coco_base ?? "");
    setAdminPort(String(settings.admin_port ?? 8088));
    setTakeoverMode((settings.takeover_mode === "all" || settings.takeover_mode === "off" ? settings.takeover_mode : "keyword") as TakeoverMode);
    setDelay(String(settings.official_answer_delay_sec ?? 0));
    setSearchTts(settings.search_tts ?? "");
    setFoundTts(settings.found_tts ?? "");
    setErrorTts(settings.error_tts ?? "");
    setKeywords(settings.coco_keywords?.length ? settings.coco_keywords : defaultKeywords);
    setSelectedDids(new Set(next.selected_dids ?? []));
    setManualTargetDids(new Set(next.manual_target_dids ?? []));
    setAliases(Object.fromEntries((next.devices ?? []).map((device) => [device.did, device.alias ?? ""])));
    if (typeof next.last_volume === "number") setLocalVolume(Math.round(next.last_volume));
    formsHydrated.current = true;
  }

  function showDialog(title: string, message: string, tone: "success" | "error" = "success") {
    setDialog({ title, message, tone });
  }

  async function chooseCloseBehavior(behavior: "tray" | "exit") {
    try {
      await handleCloseChoice(behavior, rememberCloseChoice);
      setClosePromptOpen(false);
    } catch (error) {
      setToast(String(error));
    }
  }

  async function startUpdateInstall() {
    if (!updateInfo?.portable_url) {
      setToast("当前版本没有可用的便携更新包，请到 GitHub Release 页面手动下载。");
      return;
    }
    setUpdating(true);
    try {
      await installUpdate(updateInfo.portable_url);
    } catch (error) {
      setUpdating(false);
      setToast(String(error));
    }
  }

  async function manualCheckUpdate() {
    setBusy(true);
    try {
      const info = await checkForUpdates();
      setUpdateInfo(info);
      setUpdateRead(false);
      if (info.has_update) {
        setUpdateDialogOpen(true);
      } else {
        showDialog("已是最新版本", `当前版本：${info.current_version}\n最新版本：${info.latest_version || info.current_version}`, "success");
      }
    } catch (error) {
      showDialog("检查更新失败", String(error), "error");
    } finally {
      setBusy(false);
    }
  }

  async function refresh(forceHydrate = false) {
    try {
      const [nextStatus, nextEvents] = await Promise.all([getStatus(), getEvents(180)]);
      setStatus(nextStatus);
      setEvents(nextEvents);
      hydrateForms(nextStatus, forceHydrate);
      const startupError = nextStatus.startup_error || "";
      setToast(
        extractFirstUrl(startupError)
          ? t.message.verify
          : startupError || (nextStatus.ready ? t.message.online : t.message.waiting)
      );
    } catch (error) {
      setToast(String(error));
    }
  }

  async function run<T>(task: () => Promise<T>, success: string) {
    setBusy(true);
    try {
      const result = await task();
      if (
        result &&
        typeof result === "object" &&
        "success" in result &&
        (result as ActionResult).success === false
      ) {
        throw new Error(String((result as ActionResult).error ?? "操作失败"));
      }
      setToast(success);
      await refresh(true);
      return result;
    } catch (error) {
      setToast(String(error));
      throw error;
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh(true);
    const timer = window.setInterval(() => refresh(false), 1200);
    return () => window.clearInterval(timer);
  }, [language]);

  async function doSearch() {
    const keyword = query.trim();
    if (!keyword) return;
    setSearching(true);
    setBusy(true);
    setSearchFeedback({
      tone: "info",
      message: formatMessage(t.searchState.searching, { keyword })
    });
    try {
      const items = await search(keyword, activeSearchProviders);
      setResults(items);
      setProviderFilter("all");
      setSelectedIndex(0);
      setSearchFeedback({
        tone: items.length > 0 ? "success" : "warn",
        message: items.length > 0
          ? formatMessage(t.searchState.done, { count: items.length })
          : formatMessage(t.searchState.empty, { keyword })
      });
    } catch (error) {
      const message = String(error);
      setSearchFeedback({
        tone: "error",
        message: formatMessage(t.searchState.error, { error: message })
      });
      setToast(message);
    } finally {
      setSearching(false);
      setBusy(false);
    }
  }

  async function doPlayKeyword() {
    const keyword = query.trim();
    if (!keyword) return;
    await run(() => playKeyword(keyword), "已发送播放请求");
  }

  function addToPlaylist(song: Song | null | undefined) {
    if (!song?.title) return;
    if (playlist.some((item) => songKey(item) === songKey(song))) {
      setSearchFeedback({ tone: "warn", message: t.searchState.duplicate });
      return;
    }
    setPlaylist([...playlist, song]);
    setSearchFeedback({
      tone: "success",
      message: formatMessage(t.searchState.added, { title: song.title })
    });
  }

  function toggleSearchProvider(provider: string) {
    const next = new Set(selectedProviders);
    if (next.has(provider)) next.delete(provider);
    else next.add(provider);
    setSelectedProviders(next);
  }

  function removeFromPlaylist(index: number) {
    setPlaylist(playlist.filter((_, itemIndex) => itemIndex !== index));
    if (playlistIndex === index) setPlaylistIndex(-1);
    else if (playlistIndex > index) setPlaylistIndex(playlistIndex - 1);
  }

  async function playPlaylistItem(index: number) {
    const song = playlist[index];
    if (!song) return;
    setPlaylistIndex(index);
    await run(() => playSelected(song), "已推送播放列表歌曲");
  }

  async function playNextPlaylist() {
    if (playlist.length === 0) return;
    const nextIndex = playlistIndex >= 0 ? (playlistIndex + 1) % playlist.length : 0;
    await playPlaylistItem(nextIndex);
  }

  async function playPreviousPlaylist() {
    if (playlist.length === 0) return;
    const nextIndex = playlistIndex > 0 ? playlistIndex - 1 : playlist.length - 1;
    await playPlaylistItem(nextIndex);
  }

  function clearPlaylist() {
    setPlaylist([]);
    setPlaylistIndex(-1);
  }

  async function togglePlayback() {
    await run(() => (isPlaying ? pausePlayback() : resumePlayback()), isPlaying ? "已暂停" : "已继续播放");
  }

  async function commitProgress(nextProgress: number) {
    if (duration <= 0) return;
    await run(() => seekPlayback((nextProgress / 100) * duration), "已调整播放进度");
  }

  async function applyVolume(value: number, message?: string) {
    const nextVolume = Math.max(0, Math.min(100, Math.round(value)));
    setLocalVolume(nextVolume);
    if (nextVolume > 0) previousVolumeRef.current = nextVolume;
    await run(() => setVolume(nextVolume), message ?? `音量已调整到 ${nextVolume}%`);
  }

  async function commitVolume(values: number[]) {
    await applyVolume(values[0] ?? volume);
  }

  async function toggleMute() {
    if (volume > 0) {
      previousVolumeRef.current = volume;
      await applyVolume(0, "已静音");
      return;
    }
    const value = previousVolumeRef.current > 0 ? previousVolumeRef.current : 50;
    await applyVolume(value, `音量已恢复到 ${value}%`);
  }

  function toggleSet(source: Set<string>, did: string, enabled: boolean): Set<string> {
    const next = new Set(source);
    if (enabled) next.add(did);
    else next.delete(did);
    return next;
  }

  function addKeyword() {
    const value = keywordDraft.trim();
    if (!value || keywords.includes(value)) return;
    setKeywords([...keywords, value]);
    setKeywordDraft("");
  }

  function removeKeyword(value: string) {
    setKeywords(keywords.filter((keyword) => keyword !== value));
  }

  async function submitStrategy() {
    await run(
      () => saveStrategy(cocoBase, Number(adminPort || 8088), takeoverMode, Number(delay || 0), searchTts, foundTts, errorTts, keywords),
      "策略已保存"
    );
  }

  async function testCoco() {
    setBusy(true);
    try {
      const result = (await testCocoConnection(cocoBase)) as ActionResult & { status?: number; coco_base?: string };
      if (result.success === false) {
        showDialog(t.dialog.cocoFail, String(result.error ?? "HTTP status is not 200"), "error");
        setToast(String(result.error ?? t.dialog.cocoFail));
        return;
      }
      showDialog(
        t.dialog.cocoOk,
        `${t.dialog.address}: ${String(result.coco_base ?? cocoBase)}\n${t.dialog.statusCode}: ${String(result.status ?? 200)}`,
        "success"
      );
      setToast(t.dialog.cocoOk);
    } catch (error) {
      showDialog(t.dialog.cocoFail, String(error), "error");
      setToast(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function logoutAccount() {
    setAccount("");
    setPasswordValue("");
    await run(() => saveAccount("", "", hostname), "账号已退出");
  }

  async function addCurrentDeviceAsTarget() {
    if (!targetDevice) {
      setToast(t.message.noDeviceToAdd);
      return;
    }
    const nextSelected = new Set(selectedDids);
    nextSelected.add(targetDevice.did);
    const nextTargets = new Set(manualTargetDids);
    nextTargets.add(targetDevice.did);
    setSelectedDids(nextSelected);
    setManualTargetDids(nextTargets);
    await run(() => saveDevices([...nextSelected], [...nextTargets]), "设备已添加到监听和推送");
  }

  async function copyVerificationUrl() {
    if (!verificationUrl) return;
    await navigator.clipboard.writeText(verificationUrl);
    setToast(t.message.copied);
  }

  return (
    <div
      className={cn(
        "flex h-screen w-full overflow-hidden font-sans",
        isDark ? "bg-[#0a0a0a] text-white" : "bg-[#f5f5f5] text-zinc-950"
      )}
    >
      <aside className={cn("flex w-[220px] shrink-0 flex-col border-r", isDark ? "border-white/[0.06] bg-[#111111]" : "border-zinc-200 bg-[#fafafa]")}>
        <div className="flex items-center gap-2 px-4 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/20">
            <Music2 className="h-4 w-4 text-violet-500" />
          </div>
          <div className="min-w-0">
            <div className="text-[14px] font-semibold leading-tight">coco</div>
            <div className="text-[12px] text-zinc-500">xiaomusic</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-2">
          <ul className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = activeNav === item.id;
              return (
                <li key={item.id}>
                  <button
                    onClick={() => setActiveNav(item.id)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition-colors",
                      active
                        ? "border-l-2 border-violet-500 bg-violet-500/10 text-violet-600 dark:text-violet-300"
                        : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-white/5 dark:hover:text-zinc-200"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {t.nav[item.id]}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="border-t border-border px-4 py-3">
          <div className="mb-2 flex items-center gap-2">
            <div className={cn("h-2.5 w-2.5 rounded-full", status.sidecar_ready ? "bg-emerald-500 pulse-dot" : "bg-amber-500")} />
            <span className="text-[12px] text-zinc-500">{t.label.backend}{status.sidecar_ready ? t.status.connected : t.status.connecting}</span>
          </div>
          <div className="text-[11px] text-zinc-600">XiaoMusic: {readyLabel}</div>
        </div>
      </aside>

      <div className="relative flex flex-1 flex-col overflow-hidden">
        <header className="flex h-12 items-center justify-between border-b border-border px-5">
          <div className="flex items-center gap-3">
            {busy && <Loader2 className="h-4 w-4 animate-spin text-violet-500" />}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={manualCheckUpdate} disabled={busy}>
              <Download className="h-3.5 w-3.5" />
              检查更新
            </Button>
            <Button variant="secondary" size="sm" onClick={() => refresh(true)}>
              <RefreshCw className="h-3.5 w-3.5" />
              {t.action.refresh}
            </Button>
            <Button variant="secondary" size="icon-sm" onClick={() => setTheme(isDark ? "light" : "dark")}>
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6 pb-32">
          {activeNav === "overview" && (
            <div className="space-y-5">
              <section className="flex items-center justify-between rounded-[10px] border border-border bg-card px-4 py-3">
                <div className="flex min-w-0 items-center gap-3">
                  <Speaker className="h-5 w-5 shrink-0 text-zinc-400" />
                  <span className="truncate text-[13px] font-medium">{targetDevice?.name || t.status.noDevice}</span>
                  <Badge variant="secondary" className="gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    {selectedDids.size > 0 ? t.status.listening : t.status.notListening}
                  </Badge>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setActiveNav("devices")}>
                  {t.action.switchDevice}
                </Button>
              </section>

              <section className="grid grid-cols-4 gap-3">
                <Metric title="XiaoMusic" value={readyLabel} icon={<Speaker />} />
                <Metric title={t.label.devices} value={language === "zh" ? `${devices.length} 台` : String(devices.length)} icon={<Radio />} />
                <Metric title={t.label.cocoService} value={status.coco_base || cocoBase || "--"} icon={<Music2 />} />
                <Metric title={t.label.recentCommand} value={status.last_keyword || t.empty.noCommand} icon={<Send />} />
              </section>

              <section className="grid grid-cols-[minmax(0,1fr)_360px] gap-4">
                <Card className="gap-0 rounded-[10px] py-0">
                  <CardHeader className="px-4 py-4">
                    <CardTitle className="text-[15px]">{t.label.recentPush}</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <div className="grid grid-cols-2 gap-3">
                      {recentSongs.map((song, index) => (
                        <div key={`${song.provider}-${song.id}-${song.title}-${index}`} className="group flex min-w-0 items-center gap-3 rounded-lg border border-border p-3 transition-colors hover:border-violet-500/30">
                          <CoverArt song={song} className="h-16 w-16" />
                          <div className="min-w-0 flex-1 space-y-1">
                            <div className="flex min-w-0 items-start justify-between gap-2">
                              <div className="min-w-0">
                                <p className="truncate text-[13px] font-semibold">{song.title || "--"}</p>
                                <p className="truncate text-[12px] text-zinc-500">{song.artist || "--"}</p>
                              </div>
                              <Badge variant="secondary" className="shrink-0">{durationText(song.duration)}</Badge>
                            </div>
                            <p className="truncate text-[11px] text-zinc-500">专辑：{song.album || "--"}</p>
                            <div className="flex flex-wrap gap-1.5">
                              <Badge variant="outline">{providerLabel(song.provider)}</Badge>
                              {(song.quality || song.bitrate) && <Badge variant="outline">{song.quality || song.bitrate}</Badge>}
                              {song.audio_type && <Badge variant="outline">{song.audio_type}</Badge>}
                            </div>
                          </div>
                        </div>
                      ))}
                      {recentSongs.length === 0 && <Empty className="col-span-2">{t.empty.noPush}</Empty>}
                    </div>
                  </CardContent>
                </Card>

                <Card className="gap-0 rounded-[10px] py-0">
                  <CardHeader className="px-4 py-4">
                    <CardTitle className="text-[15px]">{t.label.recentActivity}</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <div className="space-y-2">
                      {events.slice(0, 5).map((event, index) => (
                        <LogLine key={`${event.at}-${index}`} event={event} compact />
                      ))}
                      {events.length === 0 && <Empty>{t.empty.noActivity}</Empty>}
                    </div>
                  </CardContent>
                </Card>
              </section>

              <section className="grid grid-cols-3 gap-3">
                <Metric title={t.label.todayPushes} value={String(todayPushes)} icon={<Send />} />
                <Metric title={t.label.voiceHits} value={String(voiceHits)} icon={<Activity />} />
                <Metric title={t.label.uptime} value={serviceUptime} icon={<Clock />} />
              </section>
            </div>
          )}

          {activeNav === "search" && (
            <div className="grid grid-cols-[minmax(0,1fr)_340px] gap-4">
              <section className="min-w-0">
              <div className="relative mb-4">
                <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      doSearch();
                    }
                  }}
                  placeholder={t.placeholder.search}
                  className="h-11 rounded-[10px] pl-11 pr-48 text-[13px]"
                />
                <div className="absolute right-2 top-1/2 flex -translate-y-1/2 gap-2">
                  <Button onClick={doSearch} disabled={searching || !query.trim()} size="sm">
                    {searching && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {t.action.search}
                  </Button>
                  <Button onClick={doPlayKeyword} disabled={busy || !query.trim()} variant="secondary" size="sm">
                    {t.action.playBest}
                  </Button>
                </div>
              </div>

              <div className="mb-4 flex flex-wrap items-center gap-2 rounded-[10px] border border-border bg-card px-3 py-2">
                <span className="mr-1 text-[12px] text-zinc-500">{t.label.searchProviders}</span>
                <button
                  type="button"
                  onClick={() => setSelectedProviders(new Set())}
                  className={cn(
                    "rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors",
                    selectedProviders.size === 0
                      ? "bg-violet-500 text-white"
                      : "bg-muted text-zinc-500 hover:text-foreground"
                  )}
                >
                  {t.action.all}
                </button>
                {presetProviders.map((provider) => (
                  <button
                    key={provider.id}
                    type="button"
                    onClick={() => toggleSearchProvider(provider.id)}
                    className={cn(
                      "rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors",
                      selectedProviders.has(provider.id)
                        ? "bg-violet-500 text-white"
                        : "bg-muted text-zinc-500 hover:text-foreground"
                    )}
                  >
                    {provider.label}
                  </button>
                ))}
              </div>

              <div
                className={cn(
                  "mb-4 flex items-center justify-between rounded-[10px] border px-4 py-3 text-[13px] shadow-sm",
                  !searchFeedback && "border-violet-500/20 bg-violet-500/10 text-violet-600 dark:text-violet-300",
                  searchFeedback?.tone === "info" && "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-300",
                  searchFeedback?.tone === "success" && "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300",
                  searchFeedback?.tone === "warn" && "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-300",
                  searchFeedback?.tone === "error" && "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-300"
                )}
              >
                <div className="flex min-w-0 items-center gap-2">
                  {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  <span className="truncate font-medium">{searchFeedback?.message ?? t.searchState.idle}</span>
                </div>
                {selectedResult && !selectedResultInPlaylist && (
                  <Button variant="secondary" size="sm" onClick={() => addToPlaylist(selectedResult)}>
                    <Plus className="h-3.5 w-3.5" />
                    {t.action.addToPlaylist}
                  </Button>
                )}
              </div>

              {results.length > 0 && (
                <div className="mb-4 flex flex-wrap items-center gap-2 rounded-[10px] border border-border bg-card px-3 py-2">
                  <span className="mr-1 text-[12px] text-zinc-500">{t.label.providerFilter}</span>
                  <button
                    type="button"
                    onClick={() => setProviderFilter("all")}
                    className={cn(
                      "rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors",
                      providerFilter === "all"
                        ? "bg-violet-500 text-white"
                        : "bg-muted text-zinc-500 hover:text-foreground"
                    )}
                  >
                    {t.action.all} <span className="font-mono">{results.length}</span>
                  </button>
                  {providerCounts.map(([provider, count]) => (
                    <button
                      key={provider}
                      type="button"
                      onClick={() => setProviderFilter(provider)}
                      className={cn(
                        "rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors",
                        providerFilter === provider
                          ? "bg-violet-500 text-white"
                          : "bg-muted text-zinc-500 hover:text-foreground"
                      )}
                    >
                      {providerLabel(provider)} <span className="font-mono">{count}</span>
                    </button>
                  ))}
                </div>
              )}

              <div className="overflow-hidden rounded-[10px] border border-border bg-card">
                {filteredResults.length > 0 && (
                  <div className="grid grid-cols-[40px_50px_minmax(180px,1.6fr)_minmax(100px,1fr)_74px_78px_128px] items-center gap-3 border-b border-border bg-muted/50 px-4 py-3 text-[11px] font-medium text-zinc-500">
                    <span className="text-right font-mono">{t.table.index}</span>
                    <span>{t.table.cover}</span>
                    <span>{t.table.song}</span>
                    <span>{t.table.artist}</span>
                    <span className="text-center">{t.table.duration}</span>
                    <span className="text-center">{t.table.source}</span>
                    <span className="text-right">{t.table.action}</span>
                  </div>
                )}
                {results.length === 0 && <Empty className="p-8">{t.empty.noSearch}</Empty>}
                {results.length > 0 && filteredResults.length === 0 && <Empty className="p-8">{t.empty.noProviderSearch}</Empty>}
                {filteredResults.map((result, index) => (
                  <div
                    key={`${result.item.provider}-${result.item.id}-${index}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedIndex(index)}
                    onDoubleClick={() => run(() => playSelected(result.item), "已推送选中歌曲")}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        setSelectedIndex(index);
                        addToPlaylist(result.item);
                      }
                    }}
                    className={cn(
                      "group grid min-h-[68px] w-full grid-cols-[40px_50px_minmax(180px,1.6fr)_minmax(100px,1fr)_74px_78px_128px] items-center gap-3 border-b border-border px-4 text-left transition-colors last:border-0 hover:bg-muted/60",
                      selectedIndex === index && "bg-violet-500/10"
                    )}
                  >
                    <span className="text-right font-mono text-[12px] text-zinc-500">{String(index + 1).padStart(2, "0")}</span>
                    <CoverArt song={result.item} className="h-11 w-11" />
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium">{result.item.title || "--"}</p>
                      <p className="truncate text-[12px] text-zinc-500">{result.item.album || "--"}</p>
                    </div>
                    <span className="truncate text-[12px] text-zinc-500">{result.item.artist || "--"}</span>
                    <div className="flex justify-center">
                      <Badge variant="secondary">{durationText(result.item.duration)}</Badge>
                    </div>
                    <div className="flex justify-center">
                      <Badge variant="outline">{providerLabel(result.item.provider)}</Badge>
                    </div>
                    <div className="flex justify-end gap-1">
                      {playlistKeys.has(songKey(result.item)) ? (
                        <Badge variant="secondary" className="h-8 px-2 text-[11px]">{t.action.inPlaylist}</Badge>
                      ) : (
                        <Button
                          size="icon-sm"
                          variant="secondary"
                          title={t.action.addToPlaylist}
                          onClick={(event) => {
                            event.stopPropagation();
                            addToPlaylist(result.item);
                          }}
                        >
                          <Plus className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button
                        size="sm"
                        onClick={(event) => {
                          event.stopPropagation();
                          run(() => playSelected(result.item), "已推送选中歌曲");
                        }}
                      >
                        {t.action.push}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              </section>

              <aside className="min-w-0 rounded-[10px] border border-border bg-card">
                <div className="flex items-center justify-between border-b border-border px-4 py-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <ListMusic className="h-4 w-4 text-violet-500" />
                    <div className="min-w-0">
                      <h2 className="truncate text-[14px] font-semibold">{t.label.playlist}</h2>
                      <p className="text-[11px] text-zinc-500">{formatMessage(t.playlist.count, { count: playlist.length })}</p>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="secondary" size="icon-sm" disabled={playlist.length === 0 || busy} title={t.action.playAll} onClick={() => playPlaylistItem(playlistIndex >= 0 ? playlistIndex : 0)}>
                      <Play className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon-sm" disabled={playlist.length === 0} title={t.action.clearPlaylist} onClick={clearPlaylist}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
                <div className="max-h-[calc(100vh-310px)] overflow-y-auto p-3">
                  {playlist.length === 0 && (
                    <div className="rounded-[10px] border border-dashed border-border p-5 text-center">
                      <ListMusic className="mx-auto mb-2 h-6 w-6 text-zinc-400" />
                      <p className="text-[13px] font-medium">{t.playlist.empty}</p>
                      <p className="mt-1 text-[12px] text-zinc-500">{t.playlist.hint}</p>
                    </div>
                  )}
                  <div className="space-y-2">
                    {playlist.map((song, index) => (
                      <div
                        key={`${songKey(song)}-${index}`}
                        className={cn(
                          "group flex items-center gap-3 rounded-[10px] border border-border p-2 transition-colors hover:bg-muted/60",
                          playlistIndex === index && "border-violet-500/30 bg-violet-500/10"
                        )}
                      >
                        <CoverArt song={song} className="h-10 w-10" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-medium">{song.title || "--"}</p>
                          <p className="truncate text-[12px] text-zinc-500">{song.artist || "--"}</p>
                        </div>
                        <Button variant="ghost" size="icon-sm" disabled={busy} title={t.action.push} onClick={() => playPlaylistItem(index)}>
                          <Play className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon-sm" title={t.action.remove} onClick={() => removeFromPlaylist(index)}>
                          <X className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              </aside>
            </div>
          )}

          {activeNav === "devices" && (
            <div>
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h2 className="text-[15px] font-semibold">{t.label.discoveredDevices}</h2>
                  <Badge variant="secondary">{devices.length}</Badge>
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => run(() => refreshDevices(), "已刷新设备")} disabled={busy}>
                    <RefreshCw className="h-3.5 w-3.5" />
                    {t.action.refreshDevices}
                  </Button>
                  <Button onClick={() => run(() => saveDevices([...selectedDids], [...manualTargetDids]), "设备设置已保存")} disabled={busy || devices.length === 0}>
                    <Save className="h-3.5 w-3.5" />
                    {t.action.saveDevices}
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                {devices.map((device) => (
                  <DeviceRow
                    key={device.did}
                    device={device}
                    listening={selectedDids.has(device.did)}
                    target={manualTargetDids.has(device.did)}
                    alias={aliases[device.did] ?? ""}
                    onListen={(checked) => setSelectedDids(toggleSet(selectedDids, device.did, checked))}
                    onTarget={(checked) => setManualTargetDids(toggleSet(manualTargetDids, device.did, checked))}
                    onAlias={(value) => setAliases({ ...aliases, [device.did]: value })}
                    onSave={() => run(() => renameDevice(device.did, aliases[device.did] ?? ""), "设备别名已保存")}
                    onMakeDefault={() => {
                      setSelectedDids(new Set([device.did]));
                      setManualTargetDids(new Set([device.did]));
                    }}
                    uiText={t}
                  />
                ))}
                <button
                  onClick={addCurrentDeviceAsTarget}
                  className="flex h-16 w-full items-center justify-center gap-2 rounded-[10px] border border-dashed border-border text-[13px] text-zinc-500 transition-colors hover:border-violet-500/30 hover:text-violet-500"
                >
                  <Plus className="h-4 w-4" />
                  {t.action.add}{t.label.devices}
                </button>
                {devices.length === 0 && <Empty className="rounded-[10px] border border-dashed border-border p-8">{t.empty.noDevice}</Empty>}
              </div>
            </div>
          )}

          {activeNav === "logs" && (
            <div className="flex h-full flex-col">
              <div className="mb-3 flex items-center justify-between">
                <div className="flex gap-1">
                  {(["all", "info", "ok", "warn", "error"] as LogFilter[]).map((level) => (
                    <Button key={level} variant={logFilter === level ? "default" : "ghost"} size="sm" onClick={() => setLogFilter(level)}>
                      {level === "all" ? t.action.all : level.toUpperCase()}
                    </Button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Button variant={autoScroll ? "secondary" : "ghost"} size="sm" onClick={() => setAutoScroll(!autoScroll)}>
                    <ArrowDown className="h-3.5 w-3.5" />
                    {t.action.autoScroll}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => run(async () => { await clearEvents(); setEvents([]); return { success: true }; }, "日志已清空")}>
                    <Trash2 className="h-3.5 w-3.5" />
                    {t.action.clear}
                  </Button>
                </div>
              </div>
              <div ref={logContainerRef} className="scanlines flex-1 overflow-y-auto rounded-[10px] bg-zinc-950 p-4 font-mono text-[12px] text-zinc-200">
                {filteredLogs.map((event, index) => (
                  <LogLine key={`${event.at}-${index}`} event={event} terminal />
                ))}
                {filteredLogs.length === 0 && <span className="text-zinc-500">{t.empty.noLog}</span>}
              </div>
            </div>
          )}

          {activeNav === "settings" && (
            <div className="mx-auto w-full max-w-[760px] space-y-4">
              <Panel title={t.label.serviceConfig}>
                <Label title={t.label.cocoBase}>
                  <div className="flex gap-2">
                    <Input value={cocoBase} onChange={(event) => setCocoBase(event.target.value)} />
                    <Button variant="secondary" onClick={testCoco} disabled={busy}>
                      {t.action.test}
                    </Button>
                  </div>
                </Label>
                <Label title={t.label.streamPort}>
                  <Input value={adminPort} onChange={(event) => setAdminPort(event.target.value)} inputMode="numeric" className="max-w-[220px]" />
                </Label>
                <Label title={t.label.answerDelay}>
                  <Input value={delay} onChange={(event) => setDelay(event.target.value)} inputMode="decimal" className="max-w-[220px]" />
                </Label>
              </Panel>

              <Panel title={t.label.takeover}>
                <Label title={t.label.takeoverMode}>
                  <Select value={takeoverMode} onValueChange={(value) => setTakeoverMode(value as TakeoverMode)}>
                    <SelectTrigger className="w-[220px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="keyword">{t.mode.keyword}</SelectItem>
                      <SelectItem value="all">{t.mode.all}</SelectItem>
                      <SelectItem value="off">{t.mode.off}</SelectItem>
                    </SelectContent>
                  </Select>
                </Label>
                <Label title={t.label.keywords}>
                  <div className="flex flex-wrap gap-2">
                    {keywords.map((keyword) => (
                      <Badge key={keyword} variant="secondary" className="gap-1.5 px-2.5 py-1.5 text-[12px]">
                        {keyword}
                        <button onClick={() => removeKeyword(keyword)} className="rounded-full hover:text-red-500">
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                  <div className="mt-2 flex gap-2">
                    <Input value={keywordDraft} onChange={(event) => setKeywordDraft(event.target.value)} onKeyDown={(event) => event.key === "Enter" && addKeyword()} placeholder={t.placeholder.keyword} />
                    <Button type="button" variant="secondary" onClick={addKeyword}>
                      <Plus className="h-3.5 w-3.5" />
                      {t.action.add}
                    </Button>
                  </div>
                </Label>
                <Label title={t.label.searchTts}>
                  <Textarea value={searchTts} onChange={(event) => setSearchTts(event.target.value)} rows={2} />
                </Label>
                <Label title={t.label.foundTts}>
                  <Textarea value={foundTts} onChange={(event) => setFoundTts(event.target.value)} rows={2} />
                </Label>
                <Label title={t.label.errorTts}>
                  <Textarea value={errorTts} onChange={(event) => setErrorTts(event.target.value)} rows={2} />
                </Label>
                <div className="flex justify-end">
                  <Button onClick={submitStrategy} disabled={busy}>{t.action.saveStrategy}</Button>
                </div>
              </Panel>
            </div>
          )}

          {activeNav === "account" && (
            <div className="mx-auto w-full max-w-[780px] space-y-4">
              {verificationUrl && (
                <section className="rounded-[10px] border border-amber-500/30 bg-amber-500/10 p-4">
                  <div className="mb-3 flex items-center gap-2 text-[14px] font-semibold text-amber-600 dark:text-amber-300">
                    <ShieldAlert className="h-4 w-4" />
                    {t.label.miVerify}
                  </div>
                  <Input value={verificationUrl} readOnly className="mb-3 font-mono text-[12px]" />
                  <div className="flex flex-wrap gap-2">
                    <Button asChild>
                      <a href={verificationUrl} target="_blank" rel="noreferrer">
                        <ExternalLink className="h-3.5 w-3.5" />
                        {t.action.openVerify}
                      </a>
                    </Button>
                    <Button variant="secondary" onClick={copyVerificationUrl}>
                      <Copy className="h-3.5 w-3.5" />
                      {t.action.copy}
                    </Button>
                    <Button variant="secondary" onClick={() => run(() => refreshDevices(), "已刷新设备")} disabled={busy}>
                      <RefreshCw className="h-3.5 w-3.5" />
                      {t.action.verifiedRefresh}
                    </Button>
                  </div>
                </section>
              )}

              <Panel title={t.label.miAccount}>
                <Label title={t.label.account}>
                  <Input value={account} onChange={(event) => setAccount(event.target.value)} autoComplete="username" />
                </Label>
                <Label title={t.label.password}>
                  <Input value={password} onChange={(event) => setPasswordValue(event.target.value)} type="text" autoComplete="current-password" />
                </Label>
                <Label title={t.label.host}>
                  <Input value={hostname} readOnly />
                </Label>
                <div className="flex justify-between">
                  <Button variant="outline" onClick={logoutAccount} disabled={busy} className="border-red-500/30 text-red-500 hover:bg-red-500/10">
                    <LogOut className="h-3.5 w-3.5" />
                    {t.action.logout}
                  </Button>
                  <Button onClick={() => run(() => saveAccount(account, password, hostname), "账号已保存，正在重新登录")} disabled={busy}>
                    {t.action.saveLogin}
                  </Button>
                </div>
              </Panel>
            </div>
          )}
        </main>

        {playlistPanelOpen && (
          <section className="absolute bottom-24 right-5 z-40 flex max-h-[calc(100%-120px)] w-[390px] flex-col rounded-[14px] border border-border bg-card shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div className="flex min-w-0 items-center gap-2">
                <ListMusic className="h-4 w-4 text-violet-500" />
                <div className="min-w-0">
                  <h2 className="truncate text-[15px] font-semibold">{t.label.playlist}</h2>
                  <p className="text-[11px] text-zinc-500">{formatMessage(t.playlist.count, { count: playlist.length })}</p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Button variant="secondary" size="icon-sm" disabled={playlist.length === 0 || busy} title={t.action.playAll} onClick={() => playPlaylistItem(playlistIndex >= 0 ? playlistIndex : 0)}>
                  <Play className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="icon-sm" disabled={playlist.length === 0} title={t.action.clearPlaylist} onClick={clearPlaylist}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="icon-sm" title={t.action.close} onClick={() => setPlaylistPanelOpen(false)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
            <div className="overflow-y-auto p-3">
              {playlist.length === 0 ? (
                <div className="rounded-[10px] border border-dashed border-border p-6 text-center">
                  <ListMusic className="mx-auto mb-2 h-7 w-7 text-zinc-400" />
                  <p className="text-[13px] font-medium">{t.playlist.empty}</p>
                  <p className="mt-1 text-[12px] text-zinc-500">{t.playlist.hint}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {playlist.map((song, index) => (
                    <div
                      key={`${songKey(song)}-${index}`}
                      className={cn(
                        "group flex items-center gap-3 rounded-[10px] border border-border p-2 transition-colors hover:bg-muted/60",
                        playlistIndex === index && "border-violet-500/35 bg-violet-500/10"
                      )}
                    >
                      <CoverArt song={song} className="h-12 w-12" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium">{song.title || "--"}</p>
                        <p className="truncate text-[12px] text-zinc-500">{song.artist || "--"}</p>
                        <div className="mt-1 flex min-w-0 items-center gap-1.5">
                          <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{providerLabel(song.provider)}</Badge>
                          <span className="truncate text-[11px] text-zinc-500">{song.album || "--"}</span>
                        </div>
                      </div>
                      <span className="w-10 text-right font-mono text-[11px] text-zinc-500">{durationText(song.duration)}</span>
                      <Button variant="ghost" size="icon-sm" disabled={busy} title={t.action.push} onClick={() => playPlaylistItem(index)}>
                        <Play className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon-sm" title={t.action.remove} onClick={() => removeFromPlaylist(index)}>
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        )}

        <footer className="absolute bottom-0 left-0 right-0 flex h-24 items-center border-t border-border bg-card px-5 py-3">
          <div className="flex w-[28%] min-w-0 items-center gap-3">
            <CoverArt song={currentSong ?? undefined} className="h-11 w-11" fallbackIcon={<Headphones className="h-5 w-5 text-violet-500" />} />
            <div className="min-w-0">
              <p className="truncate text-[14px] font-medium">{currentSong?.title || t.empty.noSong}</p>
              <p className="truncate text-[12px] text-zinc-500">{songArtist(currentSong)}</p>
            </div>
          </div>

          <div className="flex w-[44%] flex-col items-center gap-2">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="icon-sm" disabled={playlist.length === 0 || busy} onClick={playPreviousPlaylist}><SkipBack className="h-4 w-4" /></Button>
              <Button onClick={togglePlayback} disabled={busy} size="icon-sm" className="h-10 w-10 rounded-full">
                {isPlaying ? <Pause className="h-5 w-5" /> : <Play className="ml-0.5 h-5 w-5" />}
              </Button>
              <Button onClick={() => run(stopPlayback, "已停止")} disabled={busy} variant="ghost" size="icon-sm"><Square className="h-3.5 w-3.5" /></Button>
              <Button variant="ghost" size="icon-sm" disabled={playlist.length === 0 || busy} onClick={playNextPlaylist}><SkipForward className="h-4 w-4" /></Button>
            </div>
            <div className="flex w-full max-w-2xl items-center gap-3">
              <span className="w-10 text-right text-[11px] text-zinc-500">{formatTime(position)}</span>
              <Slider value={[progress]} min={0} max={100} onValueChange={(value) => setProgress(value[0] ?? 0)} onValueCommit={(value) => commitProgress(value[0] ?? progress)} />
              <span className="w-10 text-[11px] text-zinc-500">{duration ? formatTime(duration) : "--:--"}</span>
            </div>
          </div>

          <div className="flex w-[28%] items-center justify-end gap-3">
            <Button
              variant={playlistPanelOpen ? "secondary" : "ghost"}
              size="icon-sm"
              title={t.label.playlist}
              onClick={() => setPlaylistPanelOpen((open) => !open)}
            >
              <ListMusic className="h-4 w-4" />
            </Button>
            <div
              className="relative flex items-center"
              onMouseEnter={() => setVolumePanelOpen(true)}
              onMouseLeave={() => setVolumePanelOpen(false)}
            >
              {volumePanelOpen && (
                <>
                  <div className="absolute bottom-8 left-1/2 z-40 h-14 w-12 -translate-x-1/2" />
                  <div className="absolute bottom-[82px] left-1/2 z-50 -translate-x-1/2">
                    <div className="flex h-[132px] w-12 flex-col items-center gap-2 overflow-hidden rounded-2xl border border-border bg-popover px-3 py-3 shadow-2xl">
                      <Slider
                        orientation="vertical"
                        value={[volume]}
                        min={0}
                        max={100}
                        onValueChange={(value) => setLocalVolume(value[0] ?? volume)}
                        onValueCommit={commitVolume}
                        className="h-[82px] min-h-0 data-[orientation=vertical]:h-[82px] data-[orientation=vertical]:min-h-0"
                      />
                      <span className="h-4 font-mono text-[10px] leading-4 text-zinc-500">{volume}%</span>
                    </div>
                  </div>
                </>
              )}
              <Button
                variant="ghost"
                size="icon-sm"
                title={volume > 0 ? "静音" : "恢复音量"}
                onClick={toggleMute}
              >
                {volume > 0 ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              </Button>
            </div>
            <div className="flex max-w-[190px] items-center gap-1.5 rounded-md bg-muted px-2 py-1">
              <Speaker className="h-3 w-3 shrink-0 text-zinc-500" />
              <span className="truncate text-[11px] text-zinc-500">{t.label.pushTo}: {activeDeviceName}</span>
            </div>
          </div>
        </footer>

        {dialog && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/35 px-4" onClick={() => setDialog(null)}>
            <div className="w-full max-w-[420px] rounded-[10px] border border-border bg-card p-5 shadow-2xl" onClick={(event) => event.stopPropagation()}>
              <div className="mb-2 flex items-center gap-2">
                <div className={cn("h-2.5 w-2.5 rounded-full", dialog.tone === "success" ? "bg-emerald-500" : "bg-red-500")} />
                <h3 className="text-[15px] font-semibold">{dialog.title}</h3>
              </div>
              <p className="whitespace-pre-wrap break-words text-[13px] text-zinc-500">{dialog.message}</p>
              <div className="mt-5 flex justify-end">
                <Button onClick={() => setDialog(null)}>{t.action.ok}</Button>
              </div>
            </div>
          </div>
        )}

        {updateDialogOpen && updateInfo && (
          <div className="absolute inset-0 z-[55] flex items-center justify-center bg-black/40 px-4">
            <div className="w-full max-w-[620px] rounded-[10px] border border-border bg-card p-5 shadow-2xl">
              <div className="mb-4 flex items-start gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-violet-500/15 text-violet-500">
                  <UploadCloud className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <h3 className="text-[16px] font-semibold">发现新版本 {updateInfo.latest_version}</h3>
                  <p className="mt-1 text-[12px] text-zinc-500">
                    当前版本 {updateInfo.current_version}，更新包将下载到应用目录下的 runtime/update，安装完成后自动重启。
                  </p>
                </div>
              </div>

              <div className="mb-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[10px] border border-border bg-muted/40 p-3">
                  <div className="mb-1 flex items-center gap-2 text-[13px] font-medium">
                    <Download className="h-4 w-4 text-violet-500" />
                    便携更新包
                  </div>
                  <p className="truncate text-[12px] text-zinc-500">{updateInfo.portable_name || "暂未发布"}</p>
                  <p className="mt-1 text-[11px] text-zinc-500">{formatFileSize(updateInfo.portable_size)}</p>
                </div>
                <div className="rounded-[10px] border border-border bg-muted/40 p-3">
                  <div className="mb-1 flex items-center gap-2 text-[13px] font-medium">
                    <ScrollText className="h-4 w-4 text-violet-500" />
                    安装版
                  </div>
                  <p className="truncate text-[12px] text-zinc-500">{updateInfo.installer_name || "暂未发布"}</p>
                  <p className="mt-1 text-[11px] text-zinc-500">{formatFileSize(updateInfo.installer_size)}</p>
                </div>
              </div>

              <div className="rounded-[10px] border border-border bg-background">
                <div className="flex items-center gap-2 border-b border-border px-3 py-2 text-[13px] font-medium">
                  <ScrollText className="h-4 w-4 text-violet-500" />
                  更新日志
                </div>
                <div className="max-h-[220px] overflow-y-auto whitespace-pre-wrap break-words p-3 text-[12px] leading-6 text-zinc-600 dark:text-zinc-300">
                  {updateInfo.notes || "本次发布没有填写更新日志。"}
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <label className="flex cursor-pointer items-center gap-2 text-[13px] text-zinc-600 dark:text-zinc-300">
                  <Checkbox checked={updateRead} onCheckedChange={(checked) => setUpdateRead(checked === true)} />
                  <span>我已阅读更新日志</span>
                </label>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setUpdateDialogOpen(false)} disabled={updating}>
                    稍后提醒
                  </Button>
                  <Button onClick={startUpdateInstall} disabled={!updateRead || updating || !updateInfo.portable_url}>
                    {updating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                    立即更新并重启
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}

        {closePromptOpen && (
          <div className="absolute inset-0 z-[60] flex items-center justify-center bg-black/40 px-4">
            <div className="w-full max-w-[440px] rounded-[10px] border border-border bg-card p-5 shadow-2xl">
              <div className="mb-2 flex items-center gap-2">
                <div className="h-2.5 w-2.5 rounded-full bg-violet-500" />
                <h3 className="text-[15px] font-semibold">{closeCopy.title}</h3>
              </div>
              <p className="text-[13px] leading-6 text-zinc-500">{closeCopy.message}</p>
              <label className="mt-4 flex cursor-pointer items-center gap-2 text-[13px] text-zinc-600 dark:text-zinc-300">
                <Checkbox
                  checked={rememberCloseChoice}
                  onCheckedChange={(checked) => setRememberCloseChoice(checked === true)}
                />
                <span>{closeCopy.remember}</span>
              </label>
              <div className="mt-5 flex justify-end gap-2">
                <Button variant="secondary" onClick={() => chooseCloseBehavior("tray")}>
                  {closeCopy.tray}
                </Button>
                <Button onClick={() => chooseCloseBehavior("exit")}>
                  {closeCopy.exit}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ title, value, icon }: { title: string; value: string; icon: React.ReactNode }) {
  return (
    <Card className="gap-0 rounded-[10px] py-0">
      <CardContent className="p-4">
        <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/10 text-violet-500 [&_svg]:h-4 [&_svg]:w-4">
          {icon}
        </div>
        <p className="truncate text-[20px] font-semibold">{value}</p>
        <p className="mt-1 text-[12px] text-zinc-500">{title}</p>
      </CardContent>
    </Card>
  );
}

function Empty({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("text-center text-[13px] text-zinc-500", className)}>{children}</div>;
}

function CoverArt({
  song,
  className = "",
  fallbackIcon
}: {
  song?: Song | null;
  className?: string;
  fallbackIcon?: React.ReactNode;
}) {
  const [failed, setFailed] = useState(false);
  const cover = song?.cover?.trim();
  const showImage = Boolean(cover && !failed);

  return (
    <div className={cn("relative flex shrink-0 items-center justify-center overflow-hidden rounded-lg bg-violet-500/15 text-violet-500", className)}>
      {showImage ? (
        <img
          src={cover}
          alt={song?.title || "cover"}
          referrerPolicy="no-referrer"
          className="h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        fallbackIcon ?? <Music2 className="h-4 w-4" />
      )}
    </div>
  );
}

function DeviceRow({
  device,
  listening,
  target,
  alias,
  onListen,
  onTarget,
  onAlias,
  onSave,
  onMakeDefault,
  uiText
}: {
  device: Device;
  listening: boolean;
  target: boolean;
  alias: string;
  onListen: (checked: boolean) => void;
  onTarget: (checked: boolean) => void;
  onAlias: (value: string) => void;
  onSave: () => void;
  onMakeDefault: () => void;
  uiText: (typeof text)[Language];
}) {
  return (
    <div className="grid grid-cols-[42px_minmax(0,1fr)_104px_104px_190px_72px_36px] items-center gap-3 rounded-[10px] border border-border bg-card px-4 py-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
        <Speaker className="h-5 w-5 text-zinc-400" />
      </div>
      <div className="min-w-0">
        <p className="truncate text-[13px] font-medium">{device.name || device.raw_name || uiText.empty.unnamedDevice}</p>
        <p className="truncate text-[11px] text-zinc-500">DID: {device.did} · {device.hardware || "--"}</p>
      </div>
      <div className="flex items-center gap-2">
        <Switch checked={listening} onCheckedChange={onListen} />
        <span className="text-[12px] text-zinc-500">{uiText.label.listen}</span>
      </div>
      <div className="flex items-center gap-2">
        <Switch checked={target} onCheckedChange={onTarget} />
        <span className="text-[12px] text-zinc-500">{uiText.label.push}</span>
      </div>
      <Input value={alias} onChange={(event) => onAlias(event.target.value)} placeholder={uiText.placeholder.alias} className="h-9 text-[12px]" />
      <Button onClick={onSave} variant="secondary" size="sm">{uiText.label.rename}</Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={onMakeDefault}>
            <Check className="h-4 w-4" />
            {uiText.label.defaultPush}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onSave}>
            <Save className="h-4 w-4" />
            {uiText.label.saveAlias}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function LogLine({ event, terminal = false, compact = false }: { event: EventItem; terminal?: boolean; compact?: boolean }) {
  const label = levelLabel(event.level);
  if (compact) {
    return (
      <div className="grid grid-cols-[58px_44px_minmax(0,1fr)] items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted">
        <span className="text-[11px] text-zinc-500">{String(event.at).slice(-8)}</span>
        <span className={cn("self-start rounded border px-1.5 py-0.5 text-center text-[10px] leading-none", levelTone(event.level))}>{label}</span>
        <span className="truncate text-[12px]">{event.message}</span>
      </div>
    );
  }
  return (
    <div className={cn("flex items-start gap-3 py-1.5", terminal ? "" : "text-zinc-700 dark:text-zinc-300")}>
      <span className="w-20 shrink-0 text-zinc-500">{terminal ? String(event.at).slice(-8) : event.at}</span>
      <span className={cn("w-12 shrink-0 rounded border px-1 py-1 text-center text-[10px] leading-none", levelTone(event.level))}>{label}</span>
      <span className={cn("min-w-0 flex-1 break-words", terminal ? "text-zinc-200" : "")}>{event.message}</span>
    </div>
  );
}

function Panel({ children, title }: { children: React.ReactNode; title: string }) {
  return (
    <Card className="gap-0 rounded-[10px] py-0">
      <CardHeader className="px-5 py-5">
        <CardTitle className="text-[14px] text-zinc-500">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 px-5 pb-5">{children}</CardContent>
    </Card>
  );
}

function Label({ children, title }: { children: React.ReactNode; title: string }) {
  return (
    <label className="block space-y-2">
      <span className="block text-[13px] text-zinc-500">{title}</span>
      {children}
    </label>
  );
}
