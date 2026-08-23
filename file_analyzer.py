"""递归统计目录中的文件信息，并导出 CSV 清单。

本工具仅读取扫描目录中各文件的元数据；只会写入 --output 明确指定的 CSV 文件。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class FileInfo:
    """单个文件的元数据。"""

    name: str
    path: Path
    extension: str
    size: int


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="递归扫描目录，统计文件信息并导出 CSV 清单。"
    )
    parser.add_argument(
        "--scan-dir",
        help="要递归扫描的目录路径。",
    )
    parser.add_argument(
        "--output",
        help="要生成的 CSV 文件路径（父目录必须已存在）。",
    )
    return parser.parse_args(arguments)


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    """从命令行参数或交互输入中取得扫描目录和输出 CSV 路径。"""
    scan_dir_value = args.scan_dir
    if scan_dir_value is None:
        scan_dir_value = input("请输入要扫描的文件夹路径：").strip()

    output_value = args.output
    if output_value is None:
        output_value = input("请输入 CSV 文件保存路径：").strip()

    if not scan_dir_value:
        raise ValueError("未提供要扫描的文件夹路径")
    if not output_value:
        raise ValueError("未提供 CSV 文件保存路径")

    return Path(scan_dir_value).expanduser(), Path(output_value).expanduser()


def validate_scan_directory(scan_dir: Path) -> None:
    """确认扫描目标存在、是目录且可以列出内容。"""
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


def validate_output_path(output_path: Path) -> None:
    """确认 CSV 的目标路径合理；实际写入错误会在写入时再次报告。"""
    try:
        if output_path.exists() and output_path.is_dir():
            raise ValueError(f"输出路径是目录，不是 CSV 文件：{output_path}")
        if output_path.exists():
            raise ValueError(
                f"输出文件已存在，为避免覆盖现有文件，程序不会写入：{output_path}"
            )

        parent = output_path.parent
        if not parent.exists():
            raise ValueError(f"输出目录不存在：{parent}")
        if not parent.is_dir():
            raise ValueError(f"输出路径的父路径不是目录：{parent}")
    except PermissionError as exc:
        raise ValueError(f"没有权限访问输出路径：{output_path}") from exc
    except OSError as exc:
        raise ValueError(f"无法检查输出路径：{output_path}（{exc}）") from exc


def report_skip(path: Path | str, error: OSError) -> None:
    print(f"提示：跳过无法读取的项目：{path}（{error}）", file=sys.stderr)


def scan_directory(scan_dir: Path) -> tuple[list[FileInfo], int]:
    """递归收集文件元数据，返回记录和因读取错误跳过的项目数量。"""
    files: list[FileInfo] = []
    skipped = 0

    def on_walk_error(error: OSError) -> None:
        nonlocal skipped
        skipped += 1
        report_skip(error.filename or scan_dir, error)

    for root, directories, filenames in os.walk(
        scan_dir, topdown=True, onerror=on_walk_error, followlinks=False
    ):
        # 原地修改 os.walk 的目录列表，阻止进入任意层级的 .git 目录。
        directories[:] = sorted(directory for directory in directories if directory != ".git")
        filenames.sort()
        root_path = Path(root)

        for filename in filenames:
            file_path = root_path / filename
            try:
                # stat 只读取元数据；不打开或修改文件内容。
                size = file_path.stat().st_size
            except (PermissionError, OSError) as exc:
                skipped += 1
                report_skip(file_path, exc)
                continue

            extension = file_path.suffix.lower() or "[无扩展名]"
            files.append(
                FileInfo(
                    name=filename,
                    path=file_path.absolute(),
                    extension=extension,
                    size=size,
                )
            )

    return files, skipped


def summarize(files: Iterable[FileInfo]) -> tuple[Counter[str], int, list[FileInfo]]:
    """计算扩展名数量、总大小及最大的十个文件。"""
    file_list = list(files)
    extension_counts = Counter(file.extension for file in file_list)
    total_size = sum(file.size for file in file_list)
    largest_files = sorted(file_list, key=lambda file: file.size, reverse=True)[:10]
    return extension_counts, total_size, largest_files


def write_csv(output_path: Path, files: Iterable[FileInfo]) -> None:
    """以 UTF-8 with BOM 格式写出文件清单。"""
    try:
        with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["文件名", "文件路径", "文件扩展名", "文件大小（字节）"],
            )
            writer.writeheader()
            for file in files:
                writer.writerow(
                    {
                        "文件名": file.name,
                        "文件路径": str(file.path),
                        "文件扩展名": file.extension,
                        "文件大小（字节）": file.size,
                    }
                )
    except PermissionError as exc:
        raise ValueError(f"没有权限写入 CSV 文件：{output_path}") from exc
    except OSError as exc:
        raise ValueError(f"无法写入 CSV 文件：{output_path}（{exc}）") from exc


def format_size(size: int) -> str:
    """以易读的二进制单位显示文件大小。"""
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{size} B"
        value /= 1024
    return f"{size} B"


def print_report(
    files: list[FileInfo], extension_counts: Counter[str], total_size: int,
    largest_files: list[FileInfo], skipped: int
) -> None:
    print("\n扫描完成")
    print(f"文件总数量：{len(files)}")
    print(f"不同文件类型数量：{len(extension_counts)}")
    print(f"文件总大小：{total_size} 字节（{format_size(total_size)}）")
    print("\n各文件类型数量：")
    for extension, count in sorted(extension_counts.items()):
        print(f"  {extension}: {count}")

    print("\n体积最大的 10 个文件：")
    if not largest_files:
        print("  （未找到文件）")
    for index, file in enumerate(largest_files, start=1):
        print(f"  {index}. {file.path} — {file.size} 字节（{format_size(file.size)}）")

    if skipped:
        print(f"\n已跳过无法读取的项目：{skipped} 个（详情见上方提示）", file=sys.stderr)


def main() -> int:
    args = parse_arguments()

    try:
        scan_dir, output_path = resolve_paths(args)
        validate_scan_directory(scan_dir)
        validate_output_path(output_path)
        files, skipped = scan_directory(scan_dir)
        extension_counts, total_size, largest_files = summarize(files)
        write_csv(output_path, files)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print_report(files, extension_counts, total_size, largest_files, skipped)
    print(f"\nCSV 文件已生成：{output_path.absolute()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
