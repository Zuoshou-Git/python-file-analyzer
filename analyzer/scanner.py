"""容错的递归文件元数据扫描。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Collection

from .models import FileInfo

DEFAULT_IGNORED_DIRS = frozenset({".git", "__pycache__"})
ErrorCallback = Callable[[Path, OSError], None]
ProgressCallback = Callable[[int, Path], None]
CancelCallback = Callable[[], bool]


def validate_scan_directory(scan_dir: Path) -> None:
    """确认扫描目标存在、是目录且顶层可读取。"""
    try:
        if not scan_dir.exists():
            raise ValueError(f"扫描目录不存在：{scan_dir}")
        if not scan_dir.is_dir():
            raise ValueError(f"扫描路径不是有效目录：{scan_dir}")
        with os.scandir(scan_dir):
            pass
    except PermissionError as exc:
        raise ValueError(f"没有权限读取扫描目录：{scan_dir}") from exc
    except OSError as exc:
        raise ValueError(f"无法访问扫描目录：{scan_dir}（{exc}）") from exc


def _read_size(file_path: Path) -> int:
    return file_path.stat().st_size


def scan_directory(
    scan_dir: Path,
    ignored_dirs: Collection[str] | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
    error_callback: ErrorCallback | None = None,
    cancel_callback: CancelCallback | None = None,
) -> tuple[list[FileInfo], int]:
    """递归收集文件元数据，返回文件和跳过项目数量。

    ``ignored_dirs`` 为目录名集合，匹配任意层级，便于调用方扩展。
    扫描不跟随目录符号链接，不会修改任何被扫描文件。
    """
    validate_scan_directory(scan_dir)
    ignored = set(DEFAULT_IGNORED_DIRS if ignored_dirs is None else ignored_dirs)
    files: list[FileInfo] = []
    skipped = 0

    def record_error(path: Path, error: OSError) -> None:
        nonlocal skipped
        skipped += 1
        if error_callback is not None:
            error_callback(path, error)

    def on_walk_error(error: OSError) -> None:
        record_error(Path(error.filename) if error.filename else scan_dir, error)

    for root, directories, filenames in os.walk(
        scan_dir, topdown=True, onerror=on_walk_error, followlinks=False
    ):
        if cancel_callback is not None and cancel_callback():
            break

        directories[:] = sorted(
            directory for directory in directories if directory not in ignored
        )
        filenames.sort()
        root_path = Path(root)

        for filename in filenames:
            if cancel_callback is not None and cancel_callback():
                return files, skipped
            file_path = root_path / filename
            try:
                size = _read_size(file_path)
            except (PermissionError, OSError) as exc:
                record_error(file_path, exc)
                continue

            files.append(
                FileInfo(
                    name=filename,
                    path=Path(os.path.abspath(file_path)),
                    extension=file_path.suffix.lower() or "[无扩展名]",
                    size=size,
                )
            )
            if progress_callback is not None:
                progress_callback(len(files), file_path)

    return files, skipped
