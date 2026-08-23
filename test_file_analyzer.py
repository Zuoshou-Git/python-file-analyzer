"""file_analyzer 的基础自动化测试。"""

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import file_analyzer


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
