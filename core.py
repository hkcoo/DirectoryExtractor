from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileRecord:
    full_path: str
    file_name: str

    def display_name(self, hide_extension: bool = False) -> str:
        if not hide_extension:
            return self.file_name
        return os.path.splitext(self.file_name)[0]


@dataclass(frozen=True, slots=True)
class ScanResult:
    records: list[FileRecord]
    skipped: int = 0
    cancelled: bool = False


def normalize_directory(path: str) -> str:
    """Return an absolute directory path or raise a useful error."""
    cleaned = os.path.expandvars(os.path.expanduser(path.strip()))
    if not cleaned:
        raise ValueError("请输入或选择一个目标目录。")
    absolute = os.path.abspath(cleaned)
    if not os.path.isdir(absolute):
        raise NotADirectoryError(f"目录不存在或无法访问：\n\n{absolute}")
    return absolute


def scan_directory(
    target_path: str,
    recursive: bool,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int], None] | None = None,
) -> ScanResult:
    """Scan files without touching UI objects; safe to call from a worker thread."""
    should_cancel = cancelled or (lambda: False)
    report_progress = progress or (lambda _count: None)
    records: list[FileRecord] = []
    skipped = 0

    if not recursive:
        with os.scandir(target_path) as entries:
            for entry in entries:
                if should_cancel():
                    break
                try:
                    if entry.is_file(follow_symlinks=False):
                        records.append(FileRecord(entry.path, entry.name))
                except (PermissionError, OSError):
                    skipped += 1
        records.sort(key=lambda item: item.file_name.casefold())
        return ScanResult(records, skipped, should_cancel())

    def on_walk_error(_error: OSError) -> None:
        nonlocal skipped
        skipped += 1

    for root_dir, dirs, files in os.walk(
        target_path, topdown=True, onerror=on_walk_error, followlinks=False
    ):
        if should_cancel():
            break
        dirs.sort(key=str.casefold)
        files.sort(key=str.casefold)
        for file_name in files:
            if should_cancel():
                break
            full_path = os.path.join(root_dir, file_name)
            try:
                if os.path.isfile(full_path):
                    records.append(FileRecord(full_path, file_name))
                    if len(records) % 250 == 0:
                        report_progress(len(records))
            except (PermissionError, OSError):
                skipped += 1

    records.sort(key=lambda item: item.full_path.casefold())
    return ScanResult(records, skipped, should_cancel())


def suggested_export_name(directory: str, suffix: str) -> str:
    folder_name = Path(directory).name or "扫描结果"
    return f"{folder_name}_文件清单.{suffix.lstrip('.')}"
