"""CSV 导出。"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .models import FileInfo
from .utils import format_size


CSV_FIELDS = [
    "文件名",
    "文件路径",
    "文件扩展名",
    "文件大小（字节）",
    "可读大小",
]


def validate_output_path(output_path: Path, *, overwrite: bool = False) -> None:
    """验证目标；默认延续旧行为，不覆盖已有文件。"""
    try:
        if output_path.exists() and output_path.is_dir():
            raise ValueError(f"输出路径是目录，不是 CSV 文件：{output_path}")
        if output_path.exists() and not overwrite:
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


def write_csv(
    output_path: Path, files: Iterable[FileInfo], *, overwrite: bool = False
) -> None:
    """用适合 Windows Excel 的 UTF-8 BOM 编码导出文件清单。"""
    validate_output_path(output_path, overwrite=overwrite)
    try:
        mode = "w" if overwrite else "x"
        with output_path.open(mode, encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for file in files:
                writer.writerow(
                    {
                        "文件名": file.name,
                        "文件路径": str(file.path),
                        "文件扩展名": file.extension,
                        "文件大小（字节）": file.size,
                        "可读大小": format_size(file.size),
                    }
                )
    except FileExistsError as exc:
        raise ValueError(
            f"输出文件已存在，为避免覆盖现有文件，程序不会写入：{output_path}"
        ) from exc
    except PermissionError as exc:
        raise ValueError(f"没有权限写入 CSV 文件：{output_path}") from exc
    except OSError as exc:
        raise ValueError(f"无法写入 CSV 文件：{output_path}（{exc}）") from exc
