"""Windows 图形界面入口（PySide6）。"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from analyzer.duplicates import detect_duplicates
from analyzer.exporter import write_csv
from analyzer.models import FileInfo, ScanResult
from analyzer.scanner import DEFAULT_IGNORED_DIRS, scan_directory
from analyzer.statistics import build_scan_result, extension_statistics, largest_files
from analyzer.utils import format_size


class NumericItem(QTableWidgetItem):
    """按原始数值排序、按格式化文本显示的表格项。"""

    def __init__(self, text: str, value: int | float) -> None:
        super().__init__(text)
        self.value = value
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, NumericItem):
            return self.value < other.value
        return super().__lt__(other)


class ScanWorker(QObject):
    progress = Signal(str, int, int, str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, root: Path, find_duplicates: bool) -> None:
        super().__init__()
        self.root = root
        self.find_duplicates = find_duplicates
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        errors: list[str] = []

        def on_error(path: Path, error: OSError) -> None:
            errors.append(f"{path}：{error}")

        def on_scan_progress(count: int, path: Path) -> None:
            # 大目录中逐文件跨线程发信号会淹没 GUI 事件队列。
            if count == 1 or count % 50 == 0:
                self.progress.emit("scan", count, 0, str(path))

        def on_duplicate_progress(current: int, total: int, path: Path) -> None:
            if current == 1 or current == total or current % 10 == 0:
                self.progress.emit("duplicates", current, total, str(path))

        try:
            files, skipped = scan_directory(
                self.root,
                DEFAULT_IGNORED_DIRS,
                progress_callback=on_scan_progress,
                error_callback=on_error,
                cancel_callback=self._cancel_event.is_set,
            )
            if self._cancel_event.is_set():
                self.cancelled.emit()
                return

            result = build_scan_result(self.root, files, skipped, errors)
            if self.find_duplicates:
                groups, duplicate_skipped = detect_duplicates(
                    files,
                    progress_callback=on_duplicate_progress,
                    error_callback=on_error,
                    cancel_callback=self._cancel_event.is_set,
                )
                if self._cancel_event.is_set():
                    self.cancelled.emit()
                    return
                result.duplicate_groups = groups
                result.skipped += duplicate_skipped
                result.errors = errors
            self.finished.emit(result)
        except ValueError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # GUI 边界：避免后台异常终止整个应用
            self.failed.emit(f"扫描发生意外错误：{exc}")


class StatCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        title_label = QLabel(title)
        title_label.setObjectName("muted")
        self.value_label = QLabel("—")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self.value_label.setFont(font)
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("文件分析工具")
        self.resize(1120, 760)
        self.setMinimumSize(900, 620)
        self.settings = QSettings("PythonFileAnalyzer", "FileAnalyzer")
        self.result: ScanResult | None = None
        self.thread: QThread | None = None
        self.worker: ScanWorker | None = None
        self._closing = False
        self._build_ui()
        self._apply_style()
        self._restore_settings()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(22, 20, 22, 18)
        root_layout.setSpacing(14)

        title = QLabel("文件分析工具")
        title.setObjectName("title")
        subtitle = QLabel("安全扫描文件元数据，分析类型、体积与潜在重复文件")
        subtitle.setObjectName("muted")
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        path_panel = QFrame()
        path_panel.setObjectName("panel")
        path_layout = QGridLayout(path_panel)
        path_layout.setContentsMargins(16, 14, 16, 14)
        path_layout.setHorizontalSpacing(10)
        path_layout.setVerticalSpacing(10)
        path_layout.addWidget(QLabel("扫描目录"), 0, 0)
        self.scan_path = QLineEdit()
        self.scan_path.setPlaceholderText("选择要递归扫描的文件夹")
        path_layout.addWidget(self.scan_path, 0, 1)
        browse_scan = QPushButton("选择…")
        browse_scan.clicked.connect(self._choose_scan_directory)
        path_layout.addWidget(browse_scan, 0, 2)
        path_layout.addWidget(QLabel("CSV 位置"), 1, 0)
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("选择导出位置（扫描后可导出）")
        path_layout.addWidget(self.output_path, 1, 1)
        browse_output = QPushButton("选择…")
        browse_output.clicked.connect(self._choose_output_file)
        path_layout.addWidget(browse_output, 1, 2)
        root_layout.addWidget(path_panel)

        action_layout = QHBoxLayout()
        self.duplicate_checkbox = QCheckBox("检测重复文件（同大小文件会读取内容计算哈希）")
        self.duplicate_checkbox.setChecked(True)
        action_layout.addWidget(self.duplicate_checkbox)
        action_layout.addStretch()
        self.export_button = QPushButton("导出 CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_csv)
        action_layout.addWidget(self.export_button)
        self.start_button = QPushButton("开始扫描")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self._start_or_cancel)
        action_layout.addWidget(self.start_button)
        root_layout.addLayout(action_layout)

        progress_layout = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        progress_layout.addWidget(self.progress, 1)
        self.status_label = QLabel("等待扫描")
        self.status_label.setMinimumWidth(220)
        self.status_label.setObjectName("muted")
        progress_layout.addWidget(self.status_label)
        root_layout.addLayout(progress_layout)

        cards = QHBoxLayout()
        self.file_card = StatCard("文件总数")
        self.size_card = StatCard("总大小")
        self.type_card = StatCard("文件类型")
        self.duplicate_card = StatCard("重复文件组")
        for card in (self.file_card, self.size_card, self.type_card, self.duplicate_card):
            cards.addWidget(card)
        root_layout.addLayout(cards)

        self.tabs = QTabWidget()
        self.file_table = self._make_table(["文件名", "完整路径", "扩展名", "大小", "字节"])
        self.extension_table = self._make_table(["扩展名", "数量", "占比", "总大小", "字节"])
        self.largest_table = self._make_table(["排名", "文件名", "完整路径", "大小", "字节"])
        largest_page = QWidget()
        largest_layout = QVBoxLayout(largest_page)
        largest_controls = QHBoxLayout()
        largest_controls.addWidget(QLabel("显示数量"))
        self.top_combo = QComboBox()
        self.top_combo.addItems(["Top 10", "Top 20", "Top 50"])
        self.top_combo.currentIndexChanged.connect(self._populate_largest_table)
        largest_controls.addWidget(self.top_combo)
        largest_controls.addStretch()
        largest_layout.addLayout(largest_controls)
        largest_layout.addWidget(self.largest_table)
        self.duplicate_tree = QTreeWidget()
        self.duplicate_tree.setHeaderLabels(["重复组 / 文件路径", "大小", "哈希（SHA-256）"])
        self.duplicate_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.duplicate_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.duplicate_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tabs.addTab(self.file_table, "全部文件")
        self.tabs.addTab(self.extension_table, "文件类型")
        self.tabs.addTab(largest_page, "最大文件")
        self.tabs.addTab(self.duplicate_tree, "重复文件")
        root_layout.addWidget(self.tabs, 1)

        safety = QLabel("只读扫描 · 不删除、不移动、不重命名原文件 · 默认忽略 .git 和 __pycache__")
        safety.setObjectName("footer")
        root_layout.addWidget(safety)

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(False)
        for index in range(len(headers)):
            mode = QHeaderView.ResizeMode.Stretch if index == 1 else QHeaderView.ResizeMode.ResizeToContents
            table.horizontalHeader().setSectionResizeMode(index, mode)
        return table

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f4f6f9; color: #1f2937; font-size: 13px; }
            QLabel#title { font-size: 25px; font-weight: 700; color: #111827; }
            QLabel#muted { color: #667085; }
            QLabel#footer { color: #667085; padding-top: 2px; }
            QFrame#panel, QFrame#statCard { background: white; border: 1px solid #e4e7ec; border-radius: 9px; }
            QLineEdit, QComboBox { background: white; border: 1px solid #d0d5dd; border-radius: 6px; padding: 7px; }
            QPushButton { background: white; border: 1px solid #d0d5dd; border-radius: 6px; padding: 7px 15px; }
            QPushButton:hover { background: #f9fafb; border-color: #98a2b3; }
            QPushButton:disabled { color: #98a2b3; background: #f2f4f7; }
            QPushButton#primaryButton { background: #2563eb; color: white; border-color: #2563eb; font-weight: 600; }
            QPushButton#primaryButton:hover { background: #1d4ed8; }
            QProgressBar { background: white; border: 1px solid #d0d5dd; border-radius: 5px; text-align: center; height: 17px; }
            QProgressBar::chunk { background: #2563eb; border-radius: 4px; }
            QTabWidget::pane { background: white; border: 1px solid #e4e7ec; }
            QTabBar::tab { background: #eaecf0; padding: 8px 16px; margin-right: 2px; }
            QTabBar::tab:selected { background: white; color: #1d4ed8; font-weight: 600; }
            QTableWidget, QTreeWidget { background: white; border: none; gridline-color: #eaecf0; alternate-background-color: #f9fafb; }
            QHeaderView::section { background: #f2f4f7; border: none; border-right: 1px solid #e4e7ec; padding: 7px; font-weight: 600; }
            """
        )

    def _restore_settings(self) -> None:
        scan_dir = self.settings.value("lastScanDirectory", "")
        output = self.settings.value("lastOutputPath", "")
        self.scan_path.setText(str(scan_dir))
        self.output_path.setText(str(output))
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    @Slot()
    def _choose_scan_directory(self) -> None:
        initial = self.scan_path.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "选择扫描目录", initial)
        if selected:
            self.scan_path.setText(selected)
            if not self.output_path.text().strip():
                self.output_path.setText(str(Path(selected) / "file_list.csv"))

    @Slot()
    def _choose_output_file(self) -> None:
        initial = self.output_path.text().strip() or str(Path.home() / "file_list.csv")
        selected, _ = QFileDialog.getSaveFileName(
            self, "选择 CSV 保存位置", initial, "CSV 文件 (*.csv)"
        )
        if selected:
            if not selected.lower().endswith(".csv"):
                selected += ".csv"
            self.output_path.setText(selected)

    @Slot()
    def _start_or_cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.start_button.setEnabled(False)
            self.status_label.setText("正在停止…")
            return

        root_text = self.scan_path.text().strip()
        if not root_text:
            QMessageBox.warning(self, "缺少扫描目录", "请先选择要扫描的文件夹。")
            return
        root = Path(root_text).expanduser()
        self.result = None
        self._clear_results()
        self.export_button.setEnabled(False)
        self.start_button.setText("停止扫描")
        self.progress.setRange(0, 0)
        self.status_label.setText("正在准备扫描…")
        self.settings.setValue("lastScanDirectory", str(root))

        self.thread = QThread(self)
        self.worker = ScanWorker(root, self.duplicate_checkbox.isChecked())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.worker.cancelled.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    @Slot(str, int, int, str)
    def _on_progress(self, stage: str, current: int, total: int, path: str) -> None:
        if stage == "scan":
            self.progress.setRange(0, 0)
            self.status_label.setText(f"已发现 {current:,} 个文件")
        else:
            self.progress.setRange(0, max(1, total))
            self.progress.setValue(current)
            self.status_label.setText(f"正在确认重复文件 {current:,}/{total:,}")
        self.status_label.setToolTip(path)

    @Slot(object)
    def _on_finished(self, result: ScanResult) -> None:
        self.result = result
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        status = f"扫描完成：{result.total_files:,} 个文件"
        if result.skipped:
            status += f"，跳过 {result.skipped} 个项目"
        self.status_label.setText(status)
        self._populate_results()
        self.export_button.setEnabled(True)
        if result.errors:
            details = "\n".join(result.errors[:20])
            if len(result.errors) > 20:
                details += f"\n…另有 {len(result.errors) - 20} 条"
            message = QMessageBox(self)
            message.setIcon(QMessageBox.Icon.Warning)
            message.setWindowTitle("扫描完成，但有项目被跳过")
            message.setText(f"有 {result.skipped} 个项目无法读取，已安全跳过。")
            message.setDetailedText(details)
            message.exec()

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("扫描失败")
        QMessageBox.critical(self, "扫描失败", message)

    @Slot()
    def _on_cancelled(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("扫描已停止")

    @Slot()
    def _thread_finished(self) -> None:
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self.start_button.setText("开始扫描")
        self.start_button.setEnabled(True)
        if self._closing:
            self.close()

    def _clear_results(self) -> None:
        for table in (self.file_table, self.extension_table, self.largest_table):
            table.setRowCount(0)
        self.duplicate_tree.clear()
        for card in (self.file_card, self.size_card, self.type_card, self.duplicate_card):
            card.set_value("—")

    def _populate_results(self) -> None:
        if self.result is None:
            return
        result = self.result
        self.file_card.set_value(f"{result.total_files:,}")
        self.size_card.set_value(format_size(result.total_size))
        self.type_card.set_value(f"{result.file_type_count:,}")
        self.duplicate_card.set_value(f"{len(result.duplicate_groups):,}")

        self.file_table.setSortingEnabled(False)
        self.file_table.setRowCount(len(result.files))
        for row, file in enumerate(result.files):
            self.file_table.setItem(row, 0, QTableWidgetItem(file.name))
            self.file_table.setItem(row, 1, QTableWidgetItem(str(file.path)))
            self.file_table.setItem(row, 2, QTableWidgetItem(file.extension))
            self.file_table.setItem(row, 3, NumericItem(format_size(file.size), file.size))
            self.file_table.setItem(row, 4, NumericItem(f"{file.size:,}", file.size))
        self.file_table.setSortingEnabled(True)

        stats = extension_statistics(result.files)
        self.extension_table.setSortingEnabled(False)
        self.extension_table.setRowCount(len(stats))
        for row, stat in enumerate(stats):
            self.extension_table.setItem(row, 0, QTableWidgetItem(stat.extension))
            self.extension_table.setItem(row, 1, NumericItem(f"{stat.count:,}", stat.count))
            self.extension_table.setItem(row, 2, NumericItem(f"{stat.percentage:.2f}%", stat.percentage))
            self.extension_table.setItem(row, 3, NumericItem(format_size(stat.total_size), stat.total_size))
            self.extension_table.setItem(row, 4, NumericItem(f"{stat.total_size:,}", stat.total_size))
        self.extension_table.setSortingEnabled(True)
        self._populate_largest_table()

        self.duplicate_tree.clear()
        for index, group in enumerate(result.duplicate_groups, start=1):
            parent = QTreeWidgetItem(
                [f"第 {index} 组（{len(group.files)} 个文件）", format_size(group.size), group.digest]
            )
            parent.setForeground(0, QColor("#1d4ed8"))
            self.duplicate_tree.addTopLevelItem(parent)
            for file in group.files:
                parent.addChild(QTreeWidgetItem([str(file.path), format_size(file.size), ""]))
            parent.setExpanded(index <= 5)

    @Slot()
    def _populate_largest_table(self) -> None:
        if self.result is None:
            return
        limits = (10, 20, 50)
        files = largest_files(self.result.files, limits[self.top_combo.currentIndex()])
        self.largest_table.setSortingEnabled(False)
        self.largest_table.setRowCount(len(files))
        for row, file in enumerate(files):
            self.largest_table.setItem(row, 0, NumericItem(str(row + 1), row + 1))
            self.largest_table.setItem(row, 1, QTableWidgetItem(file.name))
            self.largest_table.setItem(row, 2, QTableWidgetItem(str(file.path)))
            self.largest_table.setItem(row, 3, NumericItem(format_size(file.size), file.size))
            self.largest_table.setItem(row, 4, NumericItem(f"{file.size:,}", file.size))
        self.largest_table.setSortingEnabled(True)

    @Slot()
    def _export_csv(self) -> None:
        if self.result is None:
            return
        path_text = self.output_path.text().strip()
        if not path_text:
            self._choose_output_file()
            path_text = self.output_path.text().strip()
            if not path_text:
                return
        output = Path(path_text).expanduser()
        overwrite = False
        if output.exists():
            answer = QMessageBox.question(
                self,
                "确认覆盖",
                f"文件已存在：\n{output}\n\n是否覆盖该 CSV？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        try:
            write_csv(output, self.result.files, overwrite=overwrite)
        except ValueError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self.output_path.setText(str(output))
        self.settings.setValue("lastOutputPath", str(output))
        self.status_label.setText(f"CSV 已导出：{output}")
        QMessageBox.information(self, "导出成功", f"CSV 已保存到：\n{output}")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("lastOutputPath", self.output_path.text().strip())
        if self.worker is not None and self.thread is not None and self.thread.isRunning():
            self._closing = True
            self.worker.cancel()
            self.start_button.setEnabled(False)
            self.status_label.setText("正在安全停止扫描后退出…")
            event.ignore()
            return
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("文件分析工具")
    app.setOrganizationName("PythonFileAnalyzer")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
