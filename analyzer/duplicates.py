"""通过文件大小初筛、分块哈希确认重复文件。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

from .models import DuplicateGroup, FileInfo

HASH_CHUNK_SIZE = 1024 * 1024
DuplicateProgressCallback = Callable[[int, int, Path], None]
DuplicateErrorCallback = Callable[[Path, OSError], None]
CancelCallback = Callable[[], bool]


def hash_file(file_path: Path, chunk_size: int = HASH_CHUNK_SIZE) -> str:
    """分块读取文件并返回 SHA-256；不会将大文件整体载入内存。"""
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def detect_duplicates(
    files: Iterable[FileInfo],
    *,
    progress_callback: DuplicateProgressCallback | None = None,
    error_callback: DuplicateErrorCallback | None = None,
    cancel_callback: CancelCallback | None = None,
) -> tuple[list[DuplicateGroup], int]:
    """只对大小相同的候选文件计算哈希，返回已确认的重复组。"""
    by_size: defaultdict[int, list[FileInfo]] = defaultdict(list)
    for file in files:
        by_size[file.size].append(file)

    candidates = [
        file for group in by_size.values() if len(group) > 1 for file in group
    ]
    by_signature: defaultdict[tuple[int, str], list[FileInfo]] = defaultdict(list)
    skipped = 0

    for index, file in enumerate(candidates, start=1):
        if cancel_callback is not None and cancel_callback():
            break
        try:
            digest = hash_file(file.path)
        except (PermissionError, OSError) as exc:
            skipped += 1
            if error_callback is not None:
                error_callback(file.path, exc)
            continue
        by_signature[(file.size, digest)].append(file)
        if progress_callback is not None:
            progress_callback(index, len(candidates), file.path)

    groups = [
        DuplicateGroup(digest=digest, size=size, files=tuple(group))
        for (size, digest), group in by_signature.items()
        if len(group) > 1
    ]
    groups.sort(key=lambda group: (-group.reclaimable_size, -group.size, group.digest))
    return groups, skipped
