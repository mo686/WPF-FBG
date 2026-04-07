"""ChartWidget — 基于 matplotlib 的嵌入式图表组件

提供 plot / clear / add_annotation / set_labels / save_figure 方法，
内置 NavigationToolbar2QT（缩放、平移、重置），
通过 motion_notify_event 实现鼠标悬停坐标显示。
"""

from typing import Optional

import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

# 设置 matplotlib 中文字体支持
matplotlib.rcParams['font.family'] = ['SimHei']  # 使用黑体
matplotlib.rcParams['axes.unicode_minus'] = False  # 正确显示负号


class ChartWidget(QWidget):
    """嵌入式 matplotlib 图表组件。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.figure = Figure(tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)

        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        # 坐标显示标签
        self._coord_label = QLabel("")
        self._coord_label.setStyleSheet("color: gray; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self._coord_label)

        # 鼠标悬停坐标显示
        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

    # ------------------------------------------------------------------
    def plot(self, x, y, **kwargs):
        """在当前 Axes 上绘制一条曲线。"""
        self.ax.plot(x, y, **kwargs)
        self.canvas.draw_idle()

    def clear(self):
        """清除图表内容。"""
        self.ax.cla()
        self.canvas.draw_idle()

    def add_annotation(self, x: float, y: float, text: str):
        """在指定坐标添加标注。"""
        self.ax.annotate(
            text,
            xy=(x, y),
            textcoords="offset points",
            xytext=(5, 5),
            fontsize=8,
        )
        self.canvas.draw_idle()

    def set_labels(
        self,
        xlabel: str = "",
        ylabel: str = "",
        title: str = "",
    ):
        """设置坐标轴标签和标题。"""
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.set_title(title)
        self.canvas.draw_idle()

    def save_figure(self, filepath: str, dpi: int = 300):
        """将当前图表保存到文件。"""
        self.figure.savefig(filepath, dpi=dpi, bbox_inches="tight")

    # ------------------------------------------------------------------
    def _on_mouse_move(self, event):
        """鼠标悬停时更新坐标显示。"""
        if event.inaxes is self.ax:
            self._coord_label.setText(f"x={event.xdata:.4g}  y={event.ydata:.4g}")
        else:
            self._coord_label.setText("")