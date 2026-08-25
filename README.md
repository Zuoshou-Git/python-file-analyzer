# Windows 文件分析工具

一个面向普通 Windows 用户的图形化文件分析软件，同时保留命令行模式。它会递归读取文件元数据，展示文件类型、最大文件和潜在重复文件，并可导出适合 Windows Excel 打开的 CSV 清单。

## 功能

- PySide6 图形界面：选择目录、后台扫描、实时状态、结果表格和错误提示。
- 统计文件总数、总大小、文件类型数量，以及各扩展名的数量、占比和总大小。
- 查看全部文件及 Top 10、Top 20、Top 50 最大文件排行。
- 重复文件检测：先用大小筛选候选，再以分块 SHA-256 哈希确认，避免无意义地读取全部文件。
- UTF-8 BOM CSV 导出，包含文件名、完整路径、扩展名、原始字节数和可读大小。
- 默认忽略任意层级的 `.git` 和 `__pycache__`；核心 API 与 CLI 可方便地增加其他忽略目录。
- 文件无权限、扫描中消失或读取失败时，安全跳过并继续扫描。
- 保留原有交互式和参数式 CLI。

## 安全边界

本工具只会：

- 读取文件和目录元数据；
- 在启用重复检测时读取“大小相同”的候选文件内容以计算哈希；
- 创建或在用户明确确认后覆盖指定的 CSV 结果文件。

本工具不提供删除、移动、修改、重命名或自动清理原文件的功能。重复文件页面只展示检测结果，理论可重复不等于建议删除，请用户自行判断。

## 运行要求与安装

- Windows 10/11；
- 从源码运行需要 Python 3.10 或更高版本；
- GUI 依赖官方的 PySide6 Essentials（提供 PySide6 的 QtCore/QtGui/QtWidgets）；构建 EXE 还需要 PyInstaller。

建议在虚拟环境中安装：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

开发和打包依赖：

```powershell
python -m pip install -r requirements-dev.txt
```

## 使用 GUI

源码运行：

```powershell
python analyzer_gui.py
```

操作流程：

1. 点击“扫描目录”右侧的“选择…”；
2. 根据需要保留或取消“检测重复文件”；
3. 点击“开始扫描”，进度区会持续显示发现的文件数，哈希阶段会显示确定进度；
4. 在“全部文件”“文件类型”“最大文件”“重复文件”四个页签中查看结果；
5. 选择 CSV 位置并点击“导出 CSV”。如果目标已存在，GUI 会先询问是否覆盖。

扫描在后台线程执行，界面不会因大目录遍历而冻结。“停止扫描”可请求安全停止当前任务。

## 使用 CLI

不传参数时保留原来的交互模式：

```powershell
python file_analyzer.py
```

直接传入路径：

```powershell
python file_analyzer.py --scan-dir "D:\待扫描目录" --output "D:\输出目录\file_list.csv"
```

检测重复文件、显示 Top 20，并额外忽略名为 `node_modules` 的目录：

```powershell
python file_analyzer.py --scan-dir "D:\待扫描目录" --output "D:\输出目录\file_list.csv" --duplicates --top 20 --ignore-dir node_modules
```

可用参数：

- `--scan-dir`：扫描目录；省略时交互询问。
- `--output`：CSV 位置；省略时交互询问。CLI 为安全起见不会覆盖已有文件。
- `--top {10,20,50}`：终端最大文件排行数量。
- `--duplicates`：启用重复文件检测。
- `--ignore-dir NAME`：增加一个忽略目录名，可重复传入。

## CSV 格式

CSV 使用 `utf-8-sig`（UTF-8 BOM）编码，包含：

| 列 | 内容 |
| --- | --- |
| 文件名 | 文件名称 |
| 文件路径 | 绝对路径 |
| 文件扩展名 | 小写扩展名；没有扩展名时为 `[无扩展名]` |
| 文件大小（字节） | 原始整数大小 |
| 可读大小 | B、KB、MB、GB 等统一格式 |

## 运行测试

测试全部使用临时目录，不读取个人文件：

```powershell
python -B -m unittest -v
```

测试覆盖普通与嵌套目录、空目录、无扩展名、默认和扩展忽略规则、不存在目录、权限异常隔离、大小与类型统计、大文件排行、CSV 编码与字段、重复文件检测和 GUI 无屏幕启动。

## 构建 Windows EXE

先安装开发依赖，再运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

等价的直接命令：

```powershell
python -m PyInstaller --noconfirm --clean FileAnalyzer.spec
```

产物位于：

```text
dist\FileAnalyzer.exe
```

这是 `--onefile --windowed` 风格的单文件 GUI 程序（由 spec 配置）；目标电脑不需要单独安装 Python。`build/` 和 `dist/` 已加入 `.gitignore`，不会误提交大型构建产物。

## 项目结构

```text
python-file-analyzer/
├─ analyzer/
│  ├─ models.py       # 文件、统计和重复组数据模型
│  ├─ scanner.py      # 容错递归扫描与忽略规则
│  ├─ statistics.py   # 类型、总量和大文件统计
│  ├─ duplicates.py   # 大小初筛与分块哈希
│  ├─ exporter.py     # Excel 友好的 CSV 导出
│  └─ utils.py        # 统一大小格式化
├─ analyzer_gui.py    # PySide6 GUI 与后台 worker
├─ file_analyzer.py   # 兼容 CLI 入口
├─ test_file_analyzer.py
├─ test_gui.py
├─ requirements.txt
├─ requirements-dev.txt
├─ FileAnalyzer.spec
├─ file_version_info.txt
└─ build_exe.ps1
```

## 当前限制

- 扫描阶段无法预先知道文件总数，因此使用活动进度和“已发现文件数”；重复检测阶段才显示确定百分比。
- 重复检测依据当前读取到的 SHA-256 内容；扫描期间正在变化的文件可能被跳过或不进入预期分组。
- 超大目录的完整文件表仍会占用与文件数量成正比的内存；哈希读取采用固定大小分块，不会一次载入整个大文件。
- EXE 未做代码签名，Windows SmartScreen 可能显示未知发布者提示。
