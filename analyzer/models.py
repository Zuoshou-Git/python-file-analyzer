"""核心数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileInfo:
    """单个文件的只读元数据。"""

    name: str
    path: Path
    extension: str
    size: int


@dataclass(frozen=True, slots=True)
class ExtensionStat:
    """一种扩展名的聚合统计。"""

    extension: str
    count: int
    total_size: int
    percentage: float


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """内容哈希相同的一组文件。"""

    digest: str
    size: int
    files: tuple[FileInfo, ...]

    @property
    def reclaimable_size(self) -> int:
        """仅用于展示的理论可节省空间，不会触发删除。"""
        return self.size * max(0, len(self.files) - 1)


@dataclass(slots=True)
class ScanResult:
    """一次扫描的完整结果。"""

    root: Path
    files: list[FileInfo]
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    duplicate_groups: list[DuplicateGroup] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_size(self) -> int:
        return sum(file.size for file in self.files)

    @property
    def file_type_count(self) -> int:
        return len({file.extension for file in self.files})
