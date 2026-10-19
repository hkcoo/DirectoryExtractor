"""GitHub 发布版自动更新检查。

设计目标（仅提示 + 跳转下载）：
- 用 GitHub 官方 REST API 查询最新 Release；
- 比较当前版本与线上版本（语义化版本比较）；
- 后台线程执行网络请求，结果通过信号回到主线程（必须 QueuedConnection），
  避免跨线程操作 GUI；网络失败/限流/无网络一律静默处理，不弹错误打扰用户。
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal, Slot

API_BASE = "https://api.github.com/repos"


@dataclass
class UpdateInfo:
    has_update: bool = False
    current: str = ""
    latest: str = ""
    html_url: str = ""
    body: str = ""
    error: str | None = None


def normalize_tag(tag: str) -> str:
    """去掉前缀 v/V，统一成 '1.2.3' 形式。"""
    return tag.lstrip("vV").strip()


def parse_version(version: str) -> tuple[int, ...]:
    """把 '1.2.3' 解析成整数元组；非数字段视为 0，缺失段补 0。"""
    parts: list[int] = []
    for piece in normalize_tag(version).split("."):
        num = ""
        for ch in piece:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def compare_versions(current: str, latest: str) -> int:
    """返回 -1（有新版本）/ 0（相同）/ 1（当前更新）。"""
    a = parse_version(current)
    b = parse_version(latest)
    length = max(len(a), len(b))
    a = a + (0,) * (length - len(a))
    b = b + (0,) * (length - len(b))
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def fetch_latest_release(repo: str, timeout: float = 6.0) -> dict:
    """请求仓库最新 Release 的 JSON 数据。"""
    url = f"{API_BASE}/{repo}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DirectoryExtractor-Updater",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class UpdateChecker(QObject):
    """在子线程里查询 GitHub 最新版本，结束时发出 finished 信号。"""

    finished = Signal(object)  # UpdateInfo

    def __init__(self, repo: str, current_version: str) -> None:
        super().__init__()
        self.repo = repo
        self.current_version = current_version

    @Slot()
    def run(self) -> None:
        info = UpdateInfo(current=self.current_version)
        try:
            data = fetch_latest_release(self.repo)
            info.latest = normalize_tag(data.get("tag_name", ""))
            info.html_url = data.get("html_url", "")
            info.body = (data.get("body") or "").strip()
            info.has_update = (
                bool(info.latest)
                and compare_versions(self.current_version, info.latest) < 0
            )
        except Exception as exc:  # 网络失败/限流/无网络都静默
            info.error = str(exc)
        self.finished.emit(info)
