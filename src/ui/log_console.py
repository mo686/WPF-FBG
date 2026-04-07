"""LogConsole — 日志控制台组件

继承 QTextEdit，只读模式，自动滚动。
提供 append_log 方法和自定义 logging.Handler 将 Python logging 重定向到 GUI。
"""

import logging
from datetime import datetime

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit


# 日志级别对应颜色
_LEVEL_COLORS = {
    "INFO": QColor(Qt.black),
    "WARNING": QColor("orange"),
    "ERROR": QColor(Qt.red),
    "DEBUG": QColor(Qt.gray),
}


class LogConsole(QTextEdit):
    """日志控制台，接收 Python logging 输出并以彩色显示。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    # ------------------------------------------------------------------
    @Slot(str, str)
    def append_log(self, message: str, level: str = "INFO") -> None:
        """追加一条日志，不同级别使用不同颜色。"""
        color = _LEVEL_COLORS.get(level.upper(), QColor(Qt.black))
        timestamp = datetime.now().strftime("%H:%M:%S")
        text = f"[{timestamp}] [{level.upper()}] {message}"

        fmt = QTextCharFormat()
        fmt.setForeground(color)

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n", fmt)

        # 自动滚动到底部
        self.setTextCursor(cursor)
        self.ensureCursorVisible()


# ------------------------------------------------------------------
# 自定义 logging.Handler，将 Python logging 重定向到 LogConsole
# ------------------------------------------------------------------

class LogConsoleHandler(logging.Handler):
    """将 logging 记录转发到 LogConsole 控件。"""

    def __init__(self, console: LogConsole):
        super().__init__()
        self._console = console

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._console.append_log(msg, record.levelname)
        except Exception:
            self.handleError(record)
