"""扫描结果统计。"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from .models import ExtensionStat, FileInfo, ScanResult


def largest_files(files: Iterable[FileInfo], limit: int = 10) -> list[FileInfo]:
    """返回按体积降序排列的前 N 个文件。"""
    if limit < 0:
        raise ValueError("排行数量不能为负数")
    return sorted(files, key=lambda file: (-file.size, str(file.path).lower()))[:limit]


def summarize(files: Iterable[FileInfo]) -> tuple[Counter[str], int, list[FileInfo]]:
    """兼容原 CLI API：扩展名计数、总大小、最大 10 个文件。"""
    file_list = list(files)
    return (
        Counter(file.extension for file in file_list),
        sum(file.size for file in file_list),
        largest_files(file_list, 10),
    )


def extension_statistics(files: Iterable[FileInfo]) -> list[ExtensionStat]:
    """按扩展名计算数量、文件数占比和总大小。"""
    file_list = list(files)
    counts: Counter[str] = Counter()
    sizes: defaultdict[str, int] = defaultdict(int)
    for file in file_list:
        counts[file.extension] += 1
        sizes[file.extension] += file.size
    total = len(file_list)
    return [
        ExtensionStat(
            extension=extension,
            count=count,
            total_size=sizes[extension],
            percentage=(count / total * 100) if total else 0.0,
        )
        for extension, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def build_scan_result(
    root: Path,
    files: list[FileInfo],
    skipped: int = 0,
    errors: list[str] | None = None,
) -> ScanResult:
    return ScanResult(
        root=root.absolute(), files=files, skipped=skipped, errors=list(errors or [])
    )
