from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    home: Path
    data: Path
    conf: Path
    music: Path
    tmp: Path
    cache: Path
    logs: Path


def runtime_home() -> Path:
    configured = os.environ.get("COCO_XIAOMUSIC_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / "AppData" / "Roaming" / "coco-xiaomusic").resolve()


def prepare_runtime() -> RuntimePaths:
    home = runtime_home()
    paths = RuntimePaths(
        home=home,
        data=home / "data",
        conf=home / "conf",
        music=home / "music",
        tmp=home / "music" / "tmp",
        cache=home / "music" / "cache",
        logs=home / "logs",
    )
    for path in (paths.home, paths.data, paths.conf, paths.music, paths.tmp, paths.cache, paths.logs):
        path.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("COCO_XIAOMUSIC_HOME", str(home))
    os.chdir(home)
    return paths
