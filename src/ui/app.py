"""应用入口 — 创建 QApplication，实例化 MainWindow，启动事件循环。"""

import sys
import os

# 将项目根目录加入 sys.path，支持直接运行本文件
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # 加载全局样式表
    qss_path = os.path.join(os.path.dirname(__file__), "styles", "theme.qss")
    if os.path.isfile(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
