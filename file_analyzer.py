"""文件分析器命令行入口。

保留原有交互式和参数式 CLI。图形界面请运行 ``analyzer_gui.py``。
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from analyzer.duplicates import detect_duplicates
from analyzer.exporter import validate_output_path, write_csv
from analyzer.models import FileInfo
from analyzer.scanner import (
    DEFAULT_IGNORED_DIRS,
    scan_directory as core_scan_directory,
    validate_scan_directory,
)
from analyzer.statistics import largest_files, summarize
from analyzer.utils import format_size

__all__ = [
    "FileInfo",
    "detect_duplicates",
    "format_size",
    "scan_directory",
    "summarize",
    "validate_output_path",
    "validate_scan_directory",
    "write_csv",
]


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="递归扫描目录，统计文件信息并导出 CSV 清单。"
    )
    parser.add_argument("--scan-dir", help="要递归扫描的目录路径。")
    parser.add_argument("--output", help="要生成的 CSV 文件路径。")
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        choices=(10, 20, 50),
        help="终端显示的大文件排行数量（默认：10）。",
    )
    parser.add_argument(
        "--duplicates",
        action="store_true",
        help="扫描后检测内容完全相同的文件（会读取候选文件内容）。",
    )
    parser.add_argument(
        "--ignore-dir",
        action="append",
        default=[],
        metavar="NAME",
        help="额外忽略的目录名；可重复使用。",
    )
    return parser.parse_args(arguments)


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    """从命令行参数或交互输入中取得扫描目录和输出路径。"""
    scan_value = args.scan_dir or input("请输入要扫描的文件夹路径：").strip()
    output_value = args.output or input("请输入 CSV 文件保存路径：").strip()
    if not scan_value:
        raise ValueError("未提供要扫描的文件夹路径")
    if not output_value:
        raise ValueError("未提供 CSV 文件保存路径")
    return Path(scan_value).expanduser(), Path(output_value).expanduser()


def report_skip(path: Path | str, error: OSError) -> None:
    print(f"提示：跳过无法读取的项目：{path}（{error}）", file=sys.stderr)


def scan_directory(
    scan_dir: Path, ignored_dirs: set[str] | None = None
) -> tuple[list[FileInfo], int]:
    """兼容原有 API，并将跳过信息输出到标准错误。"""
    return core_scan_directory(
        scan_dir,
        ignored_dirs,
        error_callback=lambda path, error: report_skip(path, error),
    )


def print_report(
    files: list[FileInfo],
    extension_counts: Counter[str],
    total_size: int,
    top_files: list[FileInfo],
    skipped: int,
    *,
    duplicate_groups: int = 0,
) -> None:
    print("\n扫描完成")
    print(f"文件总数量：{len(files)}")
    print(f"不同文件类型数量：{len(extension_counts)}")
    print(f"文件总大小：{total_size} 字节（{format_size(total_size)}）")
    print("\n各文件类型数量：")
    for extension, count in sorted(extension_counts.items()):
        print(f"  {extension}: {count}")

    print(f"\n体积最大的 {len(top_files)} 个文件：")
    if not top_files:
        print("  （未找到文件）")
    for index, file in enumerate(top_files, start=1):
        print(f"  {index}. {file.path} — {file.size} 字节（{format_size(file.size)}）")

    if duplicate_groups:
        print(f"\n已确认重复文件组：{duplicate_groups} 组")
    if skipped:
        print(f"\n已跳过无法读取的项目：{skipped} 个（详情见提示）", file=sys.stderr)


def main(arguments: list[str] | None = None) -> int:
    args = parse_arguments(arguments)
    try:
        scan_dir, output_path = resolve_paths(args)
        validate_scan_directory(scan_dir)
        validate_output_path(output_path)
        ignored_dirs = set(DEFAULT_IGNORED_DIRS) | set(args.ignore_dir)
        files, skipped = scan_directory(scan_dir, ignored_dirs)
        extension_counts, total_size, _ = summarize(files)
        top_files = largest_files(files, args.top)
        duplicate_groups = []
        if args.duplicates:
            duplicate_groups, duplicate_skipped = detect_duplicates(
                files,
                error_callback=lambda path, error: report_skip(path, error),
            )
            skipped += duplicate_skipped
        write_csv(output_path, files)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print_report(
        files,
        extension_counts,
        total_size,
        top_files,
        skipped,
        duplicate_groups=len(duplicate_groups),
    )
    print(f"\nCSV 文件已生成：{output_path.absolute()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
