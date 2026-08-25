"""file_analyzer 的基础自动化测试。"""

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import file_analyzer
from analyzer.duplicates import detect_duplicates
from analyzer.exporter import write_csv
from analyzer.models import FileInfo
from analyzer.scanner import scan_directory
from analyzer.statistics import extension_statistics, largest_files
from analyzer.utils import format_size


class FileAnalyzerTests(unittest.TestCase):
    SCRIPT_PATH = Path(__file__).with_name("file_analyzer.py")

    def test_scan_summarize_and_write_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            nested = root / "nested"
            nested.mkdir()
            (root / "readme").write_bytes(b"abc")
            (root / "first.TXT").write_bytes(b"12345")
            (nested / "second.txt").write_bytes(b"1234567")

            files, skipped = file_analyzer.scan_directory(root)
            counts, total_size, largest = file_analyzer.summarize(files)
            output = root / "list.csv"
            file_analyzer.write_csv(output, files)

            self.assertEqual(skipped, 0)
            self.assertEqual(len(files), 3)
            self.assertEqual(counts[".txt"], 2)
            self.assertEqual(counts["[无扩展名]"], 1)
            self.assertEqual(total_size, 15)
            self.assertEqual(largest[0].name, "second.txt")

            with output.open("r", encoding="utf-8-sig", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["文件扩展名"], ".txt")
            self.assertEqual(rows[0]["可读大小"], "5 B")

    def test_scan_ignores_git_directory_and_its_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            git_directory = root / ".git"
            git_directory.mkdir()
            (git_directory / "config").write_text("private metadata", encoding="utf-8")
            (root / "visible.txt").write_text("visible", encoding="utf-8")

            files, skipped = file_analyzer.scan_directory(root)

            self.assertEqual(skipped, 0)
            self.assertEqual([file.name for file in files], ["visible.txt"])

    def test_scan_ignores_pycache_and_supports_extra_ignored_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            for name in ("__pycache__", "custom-cache"):
                directory = root / name
                directory.mkdir()
                (directory / "hidden.pyc").write_bytes(b"hidden")
            (root / "visible.py").write_bytes(b"ok")

            files, skipped = scan_directory(
                root, {".git", "__pycache__", "custom-cache"}
            )

            self.assertEqual(skipped, 0)
            self.assertEqual([file.name for file in files], ["visible.py"])

    def test_empty_directory_returns_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            files, skipped = scan_directory(Path(temp_directory))
            counts, total_size, largest = file_analyzer.summarize(files)

            self.assertEqual(files, [])
            self.assertEqual(skipped, 0)
            self.assertEqual(counts, {})
            self.assertEqual(total_size, 0)
            self.assertEqual(largest, [])

    def test_permission_or_disappearing_file_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            inaccessible = root / "blocked.txt"
            inaccessible.write_bytes(b"data")
            errors: list[tuple[Path, OSError]] = []

            with mock.patch(
                "analyzer.scanner._read_size",
                side_effect=PermissionError("access denied"),
            ):
                files, skipped = scan_directory(
                    root, error_callback=lambda path, error: errors.append((path, error))
                )

            self.assertEqual(files, [])
            self.assertEqual(skipped, 1)
            self.assertEqual(errors[0][0], inaccessible)
            self.assertIsInstance(errors[0][1], PermissionError)

    def test_extension_statistics_include_count_percentage_and_size(self) -> None:
        files = [
            FileInfo("a.txt", Path("a.txt"), ".txt", 10),
            FileInfo("b.txt", Path("b.txt"), ".txt", 30),
            FileInfo("image.png", Path("image.png"), ".png", 60),
        ]

        stats = {stat.extension: stat for stat in extension_statistics(files)}

        self.assertEqual(stats[".txt"].count, 2)
        self.assertEqual(stats[".txt"].total_size, 40)
        self.assertAlmostEqual(stats[".txt"].percentage, 66.666, places=2)
        self.assertEqual(stats[".png"].total_size, 60)

    def test_largest_file_rankings_support_10_20_and_50(self) -> None:
        files = [
            FileInfo(f"{index}.bin", Path(f"{index}.bin"), ".bin", index)
            for index in range(60)
        ]

        self.assertEqual(len(largest_files(files, 10)), 10)
        self.assertEqual(len(largest_files(files, 20)), 20)
        self.assertEqual(len(largest_files(files, 50)), 50)
        self.assertEqual(largest_files(files, 10)[0].size, 59)

    def test_duplicate_detection_hashes_only_same_size_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            first = root / "first.bin"
            second = root / "second.bin"
            same_size_different = root / "different.bin"
            unique_size = root / "unique.bin"
            first.write_bytes(b"duplicate")
            second.write_bytes(b"duplicate")
            same_size_different.write_bytes(b"DIFFERENT")
            unique_size.write_bytes(b"x")
            files, _ = scan_directory(root)

            with mock.patch(
                "analyzer.duplicates.hash_file",
                wraps=__import__("analyzer.duplicates", fromlist=["hash_file"]).hash_file,
            ) as hash_mock:
                groups, skipped = detect_duplicates(files)

            self.assertEqual(skipped, 0)
            self.assertEqual(hash_mock.call_count, 3)
            self.assertEqual(len(groups), 1)
            self.assertEqual({file.name for file in groups[0].files}, {"first.bin", "second.bin"})

    def test_duplicate_hash_error_is_isolated(self) -> None:
        files = [
            FileInfo("a.bin", Path("a.bin"), ".bin", 4),
            FileInfo("b.bin", Path("b.bin"), ".bin", 4),
        ]
        errors: list[Path] = []
        with mock.patch(
            "analyzer.duplicates.hash_file", side_effect=PermissionError("denied")
        ):
            groups, skipped = detect_duplicates(
                files, error_callback=lambda path, error: errors.append(path)
            )

        self.assertEqual(groups, [])
        self.assertEqual(skipped, 2)
        self.assertEqual(errors, [Path("a.bin"), Path("b.bin")])

    def test_format_size_uses_consistent_units(self) -> None:
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(1024), "1.00 KB")
        self.assertEqual(format_size(1024 * 1024), "1.00 MB")
        self.assertEqual(format_size(1024**3), "1.00 GB")

    def test_csv_export_uses_bom_and_all_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            output = Path(temp_directory) / "中文清单.csv"
            files = [FileInfo("中文.txt", Path("C:/测试/中文.txt"), ".txt", 2048)]

            write_csv(output, files)

            self.assertTrue(output.read_bytes().startswith(b"\xef\xbb\xbf"))
            with output.open("r", encoding="utf-8-sig", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(rows[0]["文件名"], "中文.txt")
            self.assertEqual(rows[0]["文件大小（字节）"], "2048")
            self.assertEqual(rows[0]["可读大小"], "2.00 KB")

    def test_csv_overwrite_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            output = Path(temp_directory) / "existing.csv"
            output.write_text("original", encoding="utf-8")
            files = [FileInfo("safe.txt", Path("safe.txt"), ".txt", 1)]

            with self.assertRaisesRegex(ValueError, "不会写入"):
                write_csv(output, files)
            self.assertEqual(output.read_text(encoding="utf-8"), "original")

            write_csv(output, files, overwrite=True)
            self.assertIn("safe.txt", output.read_text(encoding="utf-8-sig"))

    def test_validation_rejects_missing_scan_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            missing = Path(temp_directory) / "does-not-exist"
            with self.assertRaisesRegex(ValueError, "扫描目录不存在"):
                file_analyzer.validate_scan_directory(missing)

    def test_validation_rejects_missing_output_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            output = Path(temp_directory) / "missing" / "list.csv"
            with self.assertRaisesRegex(ValueError, "输出目录不存在"):
                file_analyzer.validate_output_path(output)

    def test_validation_rejects_existing_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            output = Path(temp_directory) / "existing.csv"
            output.write_text("已有内容", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "输出文件已存在"):
                file_analyzer.validate_output_path(output)

    def test_interactive_mode_prompts_for_both_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            (root / "sample.txt").write_text("sample", encoding="utf-8")
            output = root / "interactive.csv"

            result = subprocess.run(
                [sys.executable, "-X", "utf8", "-B", str(self.SCRIPT_PATH)],
                input=f"{root}\n{output}\n",
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("请输入要扫描的文件夹路径：", result.stdout)
            self.assertIn("请输入 CSV 文件保存路径：", result.stdout)
            self.assertTrue(output.exists())

    def test_command_line_mode_does_not_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            (root / "sample.txt").write_text("sample", encoding="utf-8")
            output = root / "command-line.csv"

            result = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    "-B",
                    str(self.SCRIPT_PATH),
                    "--scan-dir",
                    str(root),
                    "--output",
                    str(output),
                ],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("请输入要扫描的文件夹路径：", result.stdout)
            self.assertNotIn("请输入 CSV 文件保存路径：", result.stdout)
            self.assertTrue(output.exists())

    def test_invalid_path_still_returns_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            missing = Path(temp_directory) / "missing"
            output = Path(temp_directory) / "list.csv"

            result = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    "-B",
                    str(self.SCRIPT_PATH),
                    "--scan-dir",
                    str(missing),
                    "--output",
                    str(output),
                ],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("扫描目录不存在", result.stderr)


if __name__ == "__main__":
    unittest.main()
