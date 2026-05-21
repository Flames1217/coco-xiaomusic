import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowDown,
  Check,
  Clock,
  Copy,
  ExternalLink,
  Headphones,
  Home,
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
  Volume2,
  X
} from "lucide-react";
import {
  clearEvents,
  getEvents,
  getStatus,
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
  testCocoConnection,
  stopPlayback
} from "../lib/api";
import type { AppStatus, Device, EventItem, SearchItem, Song } from "../lib/types";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
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

const navItems: Array<{ id: NavItem; icon: typeof Home; label: string }> = [
  { id: "overview", icon: Home, label: "概览" },
  { id: "search", icon: Search, label: "搜索与推送" },
  { id: "devices", icon: Radio, label: "设备管理" },
  { id: "logs", icon: ScrollText, label: "实时日志" },
  { id: "settings", icon: Settings, label: "策略设置" },
  { id: "account", icon: ShieldAlert, label: "账号授权" }
];

const defaultKeywords = ["播放", "放一首", "来一首", "唱", "coco"];

function extractFirstUrl(value: string | undefined): string {
  const match = String(value ?? "").match(/https?:\/\/\S+/);
  return match?.[0] ?? "";
}

function formatTime(value: number): string {
  const seconds = Math.max(0, Math.floor(value || 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
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

function songTitle(song: Song | null | undefined): string {
  return song?.title || "暂无歌曲";
}

function songArtist(song: Song | null | undefined): string {
  return song?.artist || "--";
}

export default function CocoXiaoMusic() {
  const [activeNav, setActiveNav] = useState<NavItem>("overview");
  const [theme, setTheme] = useState<Theme>("light");
  const [language, setLanguage] = useState<Language>("zh");
  const [status, setStatus] = useState<AppStatus>({});
  const [events, setEvents] = useState<EventItem[]>([]);
  const [results, setResults] = useState<SearchItem[]>([]);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("正在连接后台服务...");
  const [logFilter, setLogFilter] = useState<LogFilter>("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [volume, setLocalVolume] = useState(50);
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

  const isDark = theme === "dark";
  const devices = status.devices ?? [];
  const currentSong = status.last_song ?? null;
  const isPlaying = Boolean(status.last_used_url && !status.playback_paused);
  const duration = Number(status.last_duration ?? 0);
  const position = Number(status.last_position ?? 0);
  const verificationUrl = extractFirstUrl(status.startup_error || toast);
  const readyLabel = status.ready ? "在线" : status.starting ? "启动中" : status.startup_error ? "待处理" : "离线";
  const activeDeviceName =
    devices.find((device) => manualTargetDids.has(device.did))?.name || devices[0]?.name || "未选择设备";
  const targetDevice = devices.find((device) => manualTargetDids.has(device.did)) || devices[0];
  const today = new Date().toISOString().slice(0, 10);
  const todayPushes = events.filter((event) => event.at?.startsWith(today) && Boolean(event.song)).length;
  const voiceHits = events.filter((event) => event.keyword || event.message.includes("语音") || event.message.includes("关键词")).length;
  const firstEventTime = events.at(-1)?.at;
  const serviceUptime = firstEventTime ? "已运行" : "--";

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
      setLocalVolume(Math.max(0, Math.min(100, Math.round(status.last_volume))));
    }
  }, [status.last_volume]);

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

  async function refresh(forceHydrate = false) {
    try {
      const [nextStatus, nextEvents] = await Promise.all([getStatus(), getEvents(180)]);
      setStatus(nextStatus);
      setEvents(nextEvents);
      hydrateForms(nextStatus, forceHydrate);
      const startupError = nextStatus.startup_error || "";
      setToast(
        extractFirstUrl(startupError)
          ? "小米账号需要安全验证，请到账号授权页处理"
          : startupError || (nextStatus.ready ? "服务在线" : "等待账号或设备配置")
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
  }, []);

  async function doSearch() {
    const keyword = query.trim();
    if (!keyword) return;
    await run(async () => {
      const items = await search(keyword);
      setResults(items);
      setSelectedIndex(0);
      return { success: true };
    }, `搜索完成：${keyword}`);
  }

  async function doPlayKeyword() {
    const keyword = query.trim();
    if (!keyword) return;
    await run(() => playKeyword(keyword), "已发送播放请求");
  }

  async function togglePlayback() {
    await run(() => (isPlaying ? pausePlayback() : resumePlayback()), isPlaying ? "已暂停" : "已继续播放");
  }

  async function commitProgress(nextProgress: number) {
    if (duration <= 0) return;
    await run(() => seekPlayback((nextProgress / 100) * duration), "已调整播放进度");
  }

  async function commitVolume(values: number[]) {
    const value = Math.max(0, Math.min(100, Math.round(values[0] ?? volume)));
    setLocalVolume(value);
    await run(() => setVolume(value), `音量已调整到 ${value}%`);
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
    await run(() => testCocoConnection(cocoBase), "coco 服务连接正常");
  }

  async function logoutAccount() {
    setAccount("");
    setPasswordValue("");
    await run(() => saveAccount("", "", hostname), "账号已退出");
  }

  async function addCurrentDeviceAsTarget() {
    if (!targetDevice) {
      setToast("当前没有可添加的设备，请先刷新设备");
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
    setToast("验证链接已复制");
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
                    {item.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="border-t border-border px-4 py-3">
          <div className="mb-2 flex items-center gap-2">
            <div className={cn("h-2 w-2 rounded-full", status.sidecar_ready ? "bg-emerald-500 pulse-dot" : "bg-amber-500")} />
            <span className="text-[12px] text-zinc-500">后台服务{status.sidecar_ready ? "已连接" : "连接中"}</span>
          </div>
          <div className="text-[11px] text-zinc-600">XiaoMusic: {readyLabel}</div>
        </div>
      </aside>

      <div className="relative flex flex-1 flex-col overflow-hidden">
        <header className="flex h-12 items-center justify-between border-b border-border px-5">
          <div className="flex items-center gap-3">
            <span className="text-[13px] font-medium">{readyLabel}</span>
            {busy && <Loader2 className="h-4 w-4 animate-spin text-violet-500" />}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 items-center rounded-full bg-muted p-0.5 text-[12px] font-medium">
              <button
                onClick={() => setLanguage("zh")}
                className={cn("h-7 rounded-full px-2.5", language === "zh" ? "bg-violet-500 text-white" : "text-zinc-500")}
              >
                中
              </button>
              <button
                onClick={() => setLanguage("en")}
                className={cn("h-7 rounded-full px-2.5", language === "en" ? "bg-violet-500 text-white" : "text-zinc-500")}
              >
                EN
              </button>
            </div>
            <Button variant="secondary" size="sm" onClick={() => refresh(true)}>
              <RefreshCw className="h-3.5 w-3.5" />
              刷新
            </Button>
            <Button variant="secondary" size="icon-sm" onClick={() => setTheme(isDark ? "light" : "dark")}>
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6 pb-24">
          {activeNav === "overview" && (
            <div className="space-y-5">
              <section className="flex items-center justify-between rounded-[10px] border border-border bg-card px-4 py-3">
                <div className="flex min-w-0 items-center gap-3">
                  <Speaker className="h-5 w-5 shrink-0 text-zinc-400" />
                  <span className="truncate text-[13px] font-medium">{targetDevice?.name || "未选择设备"}</span>
                  <Badge variant="secondary" className="gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    {selectedDids.size > 0 ? "监听中" : "未监听"}
                  </Badge>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setActiveNav("devices")}>
                  切换设备
                </Button>
              </section>

              <section className="grid grid-cols-4 gap-3">
                <Metric title="XiaoMusic" value={readyLabel} icon={<Speaker />} />
                <Metric title="设备" value={`${devices.length} 台`} icon={<Radio />} />
                <Metric title="coco 服务" value={status.coco_base || cocoBase || "--"} icon={<Music2 />} />
                <Metric title="最近口令" value={status.last_keyword || "暂无"} icon={<Send />} />
              </section>

              <section className="grid grid-cols-[minmax(0,1fr)_360px] gap-4">
                <Card className="gap-0 rounded-[10px] py-0">
                  <CardHeader className="px-4 py-4">
                    <CardTitle className="text-[15px]">最近推送</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <div className="grid grid-cols-2 gap-3">
                      {recentSongs.map((song, index) => (
                        <div key={`${song.title}-${index}`} className="group flex min-w-0 items-center gap-3 rounded-lg border border-border p-3 transition-colors hover:border-violet-500/30">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-violet-500/15">
                            <Music2 className="h-4 w-4 text-violet-500" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-[13px] font-medium">{song.title}</p>
                            <p className="truncate text-[12px] text-zinc-500">{song.artist || "--"}</p>
                          </div>
                        </div>
                      ))}
                      {recentSongs.length === 0 && <Empty className="col-span-2">暂无推送记录</Empty>}
                    </div>
                  </CardContent>
                </Card>

                <Card className="gap-0 rounded-[10px] py-0">
                  <CardHeader className="px-4 py-4">
                    <CardTitle className="text-[15px]">最近活动</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <div className="space-y-2">
                      {events.slice(0, 5).map((event, index) => (
                        <LogLine key={`${event.at}-${index}`} event={event} compact />
                      ))}
                      {events.length === 0 && <Empty>暂无活动</Empty>}
                    </div>
                  </CardContent>
                </Card>
              </section>

              <section className="grid grid-cols-3 gap-3">
                <Metric title="今日推送次数" value={String(todayPushes)} icon={<Send />} />
                <Metric title="语音命中次数" value={String(voiceHits)} icon={<Activity />} />
                <Metric title="服务运行时长" value={serviceUptime} icon={<Clock />} />
              </section>
            </div>
          )}

          {activeNav === "search" && (
            <div>
              <div className="relative mb-4">
                <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && doSearch()}
                  placeholder="搜索歌曲、歌手或语音口令"
                  className="h-11 rounded-[10px] pl-11 pr-48 text-[13px]"
                />
                <div className="absolute right-2 top-1/2 flex -translate-y-1/2 gap-2">
                  <Button onClick={doPlayKeyword} disabled={busy || !query.trim()} size="sm">
                    播放首选
                  </Button>
                  <Button onClick={doSearch} disabled={busy || !query.trim()} variant="secondary" size="sm">
                    搜索
                  </Button>
                </div>
              </div>

              <div className="overflow-hidden rounded-[10px] border border-border bg-card">
                {results.length === 0 && <Empty className="p-8">暂无搜索结果</Empty>}
                {results.map((result, index) => (
                  <button
                    key={`${result.item.provider}-${result.item.id}-${index}`}
                    onClick={() => setSelectedIndex(index)}
                    onDoubleClick={() => run(() => playSelected(result.item), "已推送选中歌曲")}
                    className={cn(
                      "group flex h-[56px] w-full items-center gap-4 border-b border-border px-4 text-left transition-colors last:border-0 hover:bg-muted/60",
                      selectedIndex === index && "bg-violet-500/10"
                    )}
                  >
                    <span className="w-6 text-right font-mono text-[12px] text-zinc-500">{String(index + 1).padStart(2, "0")}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium">{result.item.title || "--"}</p>
                      <p className="truncate text-[12px] text-zinc-500">{result.item.artist || "--"}</p>
                    </div>
                    <Badge variant="secondary">{durationText(result.item.duration)}</Badge>
                    <Badge variant="outline">{result.item.provider || "coco"}</Badge>
                    <Button
                      size="sm"
                      onClick={(event) => {
                        event.stopPropagation();
                        run(() => playSelected(result.item), "已推送选中歌曲");
                      }}
                      className="opacity-0 group-hover:opacity-100"
                    >
                      推送
                    </Button>
                  </button>
                ))}
              </div>
            </div>
          )}

          {activeNav === "devices" && (
            <div>
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h2 className="text-[15px] font-semibold">已发现设备</h2>
                  <Badge variant="secondary">{devices.length}</Badge>
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => run(() => refreshDevices(), "已刷新设备")} disabled={busy}>
                    <RefreshCw className="h-3.5 w-3.5" />
                    刷新设备
                  </Button>
                  <Button onClick={() => run(() => saveDevices([...selectedDids], [...manualTargetDids]), "设备设置已保存")} disabled={busy || devices.length === 0}>
                    <Save className="h-3.5 w-3.5" />
                    保存设备
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
                  />
                ))}
                <button
                  onClick={addCurrentDeviceAsTarget}
                  className="flex h-16 w-full items-center justify-center gap-2 rounded-[10px] border border-dashed border-border text-[13px] text-zinc-500 transition-colors hover:border-violet-500/30 hover:text-violet-500"
                >
                  <Plus className="h-4 w-4" />
                  添加设备
                </button>
                {devices.length === 0 && <Empty className="rounded-[10px] border border-dashed border-border p-8">暂无设备。完成小米安全验证后点击“刷新设备”。</Empty>}
              </div>
            </div>
          )}

          {activeNav === "logs" && (
            <div className="flex h-full flex-col">
              <div className="mb-3 flex items-center justify-between">
                <div className="flex gap-1">
                  {(["all", "info", "ok", "warn", "error"] as LogFilter[]).map((level) => (
                    <Button key={level} variant={logFilter === level ? "default" : "ghost"} size="sm" onClick={() => setLogFilter(level)}>
                      {level === "all" ? "全部" : level.toUpperCase()}
                    </Button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Button variant={autoScroll ? "secondary" : "ghost"} size="sm" onClick={() => setAutoScroll(!autoScroll)}>
                    <ArrowDown className="h-3.5 w-3.5" />
                    自动滚动
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => run(async () => { await clearEvents(); setEvents([]); return { success: true }; }, "日志已清空")}>
                    <Trash2 className="h-3.5 w-3.5" />
                    清空
                  </Button>
                </div>
              </div>
              <div ref={logContainerRef} className="scanlines flex-1 overflow-y-auto rounded-[10px] bg-zinc-950 p-4 font-mono text-[12px] text-zinc-200">
                {filteredLogs.map((event, index) => (
                  <LogLine key={`${event.at}-${index}`} event={event} terminal />
                ))}
                {filteredLogs.length === 0 && <span className="text-zinc-500">暂无日志</span>}
              </div>
            </div>
          )}

          {activeNav === "settings" && (
            <div className="mx-auto w-full max-w-[760px] space-y-4">
              <Panel title="服务配置">
                <Label title="coco 服务地址">
                  <div className="flex gap-2">
                    <Input value={cocoBase} onChange={(event) => setCocoBase(event.target.value)} />
                    <Button variant="secondary" onClick={testCoco} disabled={busy}>
                      测试连接
                    </Button>
                  </div>
                </Label>
                <Label title="MP3 流服务端口">
                  <Input value={adminPort} onChange={(event) => setAdminPort(event.target.value)} inputMode="numeric" className="max-w-[220px]" />
                </Label>
                <Label title="官方回答延迟秒数">
                  <Input value={delay} onChange={(event) => setDelay(event.target.value)} inputMode="decimal" className="max-w-[220px]" />
                </Label>
              </Panel>

              <Panel title="语音接管">
                <Label title="接管策略">
                  <Select value={takeoverMode} onValueChange={(value) => setTakeoverMode(value as TakeoverMode)}>
                    <SelectTrigger className="w-[220px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="keyword">仅关键词接管</SelectItem>
                      <SelectItem value="all">全部口令接管</SelectItem>
                      <SelectItem value="off">关闭接管</SelectItem>
                    </SelectContent>
                  </Select>
                </Label>
                <Label title="接管关键词">
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
                    <Input value={keywordDraft} onChange={(event) => setKeywordDraft(event.target.value)} onKeyDown={(event) => event.key === "Enter" && addKeyword()} placeholder="新增关键词" />
                    <Button type="button" variant="secondary" onClick={addKeyword}>
                      <Plus className="h-3.5 w-3.5" />
                      添加
                    </Button>
                  </div>
                </Label>
                <Label title="搜索提示话术">
                  <Textarea value={searchTts} onChange={(event) => setSearchTts(event.target.value)} rows={2} />
                </Label>
                <Label title="命中提示话术">
                  <Textarea value={foundTts} onChange={(event) => setFoundTts(event.target.value)} rows={2} />
                </Label>
                <Label title="失败提示话术">
                  <Textarea value={errorTts} onChange={(event) => setErrorTts(event.target.value)} rows={2} />
                </Label>
                <div className="flex justify-end">
                  <Button onClick={submitStrategy} disabled={busy}>保存策略</Button>
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
                    小米账号需要安全验证
                  </div>
                  <Input value={verificationUrl} readOnly className="mb-3 font-mono text-[12px]" />
                  <div className="flex flex-wrap gap-2">
                    <Button asChild>
                      <a href={verificationUrl} target="_blank" rel="noreferrer">
                        <ExternalLink className="h-3.5 w-3.5" />
                        打开验证链接
                      </a>
                    </Button>
                    <Button variant="secondary" onClick={copyVerificationUrl}>
                      <Copy className="h-3.5 w-3.5" />
                      复制链接
                    </Button>
                    <Button variant="secondary" onClick={() => run(() => refreshDevices(), "已刷新设备")} disabled={busy}>
                      <RefreshCw className="h-3.5 w-3.5" />
                      我已验证，刷新设备
                    </Button>
                  </div>
                </section>
              )}

              <Panel title="小米账号">
                <Label title="账号">
                  <Input value={account} onChange={(event) => setAccount(event.target.value)} autoComplete="username" />
                </Label>
                <Label title="密码">
                  <Input value={password} onChange={(event) => setPasswordValue(event.target.value)} type="text" autoComplete="current-password" />
                </Label>
                <Label title="本机访问地址">
                  <Input value={hostname} readOnly />
                </Label>
                <div className="flex justify-between">
                  <Button variant="outline" onClick={logoutAccount} disabled={busy} className="border-red-500/30 text-red-500 hover:bg-red-500/10">
                    <LogOut className="h-3.5 w-3.5" />
                    退出登录
                  </Button>
                  <Button onClick={() => run(() => saveAccount(account, password, hostname), "账号已保存，正在重新登录")} disabled={busy}>
                    保存并登录
                  </Button>
                </div>
              </Panel>
            </div>
          )}
        </main>

        <footer className="absolute bottom-0 left-0 right-0 flex h-16 items-center border-t border-border bg-card px-4">
          <div className="flex w-[30%] min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-500/20">
              <Headphones className="h-4 w-4 text-violet-500" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium">{songTitle(currentSong)}</p>
              <p className="truncate text-[12px] text-zinc-500">{songArtist(currentSong)}</p>
            </div>
          </div>

          <div className="flex w-[40%] flex-col items-center">
            <div className="mb-1.5 flex items-center gap-3">
              <Button variant="ghost" size="icon-sm" disabled><SkipBack className="h-4 w-4" /></Button>
              <Button onClick={togglePlayback} disabled={busy} size="icon-sm" className="rounded-full">
                {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="ml-0.5 h-4 w-4" />}
              </Button>
              <Button onClick={() => run(stopPlayback, "已停止")} disabled={busy} variant="ghost" size="icon-sm"><Square className="h-3.5 w-3.5" /></Button>
              <Button variant="ghost" size="icon-sm" disabled><SkipForward className="h-4 w-4" /></Button>
            </div>
            <div className="flex w-full max-w-md items-center gap-2">
              <span className="w-10 text-right text-[11px] text-zinc-500">{formatTime(position)}</span>
              <Slider value={[progress]} min={0} max={100} onValueChange={(value) => setProgress(value[0] ?? 0)} onValueCommit={(value) => commitProgress(value[0] ?? progress)} />
              <span className="w-10 text-[11px] text-zinc-500">{duration ? formatTime(duration) : "--:--"}</span>
            </div>
          </div>

          <div className="flex w-[30%] items-center justify-end gap-4">
            <div className="flex w-[168px] items-center gap-2">
              <Volume2 className="h-4 w-4 shrink-0 text-zinc-400" />
              <Slider value={[volume]} min={0} max={100} onValueChange={(value) => setLocalVolume(value[0] ?? volume)} onValueCommit={commitVolume} />
              <span className="w-9 text-right font-mono text-[11px] text-zinc-500">{volume}%</span>
            </div>
            <div className="flex max-w-[190px] items-center gap-1.5 rounded-md bg-muted px-2 py-1">
              <Speaker className="h-3 w-3 shrink-0 text-zinc-500" />
              <span className="truncate text-[11px] text-zinc-500">推送至: {activeDeviceName}</span>
            </div>
          </div>
        </footer>

        <div className="absolute bottom-20 right-5 max-w-[520px] rounded-[10px] border border-border bg-card px-3 py-2 text-[12px] shadow-2xl">
          {toast}
        </div>
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

function DeviceRow({
  device,
  listening,
  target,
  alias,
  onListen,
  onTarget,
  onAlias,
  onSave,
  onMakeDefault
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
}) {
  return (
    <div className="grid grid-cols-[42px_minmax(0,1fr)_104px_104px_190px_72px_36px] items-center gap-3 rounded-[10px] border border-border bg-card px-4 py-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
        <Speaker className="h-5 w-5 text-zinc-400" />
      </div>
      <div className="min-w-0">
        <p className="truncate text-[13px] font-medium">{device.name || device.raw_name || "未命名设备"}</p>
        <p className="truncate text-[11px] text-zinc-500">DID: {device.did} · {device.hardware || "--"}</p>
      </div>
      <div className="flex items-center gap-2">
        <Switch checked={listening} onCheckedChange={onListen} />
        <span className="text-[12px] text-zinc-500">监听</span>
      </div>
      <div className="flex items-center gap-2">
        <Switch checked={target} onCheckedChange={onTarget} />
        <span className="text-[12px] text-zinc-500">推送</span>
      </div>
      <Input value={alias} onChange={(event) => onAlias(event.target.value)} placeholder="本地别名" className="h-9 text-[12px]" />
      <Button onClick={onSave} variant="secondary" size="sm">命名</Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={onMakeDefault}>
            <Check className="h-4 w-4" />
            设为默认推送
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onSave}>
            <Save className="h-4 w-4" />
            保存别名
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
      <div className="grid grid-cols-[58px_44px_minmax(0,1fr)] items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted">
        <span className="text-[11px] text-zinc-500">{String(event.at).slice(-8)}</span>
        <span className={cn("rounded border px-1.5 py-0.5 text-center text-[10px]", levelTone(event.level))}>{label}</span>
        <span className="truncate text-[12px]">{event.message}</span>
      </div>
    );
  }
  return (
    <div className={cn("flex gap-3 py-1", terminal ? "" : "text-zinc-700 dark:text-zinc-300")}>
      <span className="w-20 shrink-0 text-zinc-500">{terminal ? String(event.at).slice(-8) : event.at}</span>
      <span className={cn("w-12 shrink-0 rounded border px-1 text-center text-[10px]", levelTone(event.level))}>{label}</span>
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
