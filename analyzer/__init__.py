"""文件分析器的可复用核心 API。"""

from .duplicates import detect_duplicates
from .exporter import write_csv
from .models import DuplicateGroup, ExtensionStat, FileInfo, ScanResult
from .scanner import DEFAULT_IGNORED_DIRS, scan_directory, validate_scan_directory
from .statistics import build_scan_result, largest_files, summarize
from .utils import format_size

__all__ = [
    "DEFAULT_IGNORED_DIRS",
    "DuplicateGroup",
    "ExtensionStat",
    "FileInfo",
    "ScanResult",
    "build_scan_result",
    "detect_duplicates",
    "format_size",
    "largest_files",
    "scan_directory",
    "summarize",
    "validate_scan_directory",
    "write_csv",
]
