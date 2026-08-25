"""无界面依赖的通用工具。"""


def format_size(size: int) -> str:
    """以统一的二进制进位、易读单位显示非负字节数。"""
    if size < 0:
        raise ValueError("文件大小不能为负数")

    units = ("B", "KB", "MB", "GB", "TB", "PB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{size} B" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"
