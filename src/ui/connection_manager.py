"""ConnectionManager — 集中管理所有仪器连接状态

继承 QObject，通过 Signal 通知 UI 层状态变化。
"""

import logging
from enum import Enum
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class InstrumentStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


class _InstrumentEntry:
    """内部记录：保存单个仪器的连接/断开回调和当前状态。"""

    def __init__(
        self,
        connect_fn: Callable[[], bool],
        disconnect_fn: Callable[[], bool],
    ):
        self.connect_fn = connect_fn
        self.disconnect_fn = disconnect_fn
        self.status = InstrumentStatus.DISCONNECTED


class ConnectionManager(QObject):
    """集中管理所有仪器连接状态。"""

    # (instrument_name, new_status_value)
    status_changed = Signal(str, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._instruments: Dict[str, _InstrumentEntry] = {}

    # ------------------------------------------------------------------
    def register_instrument(
        self,
        name: str,
        connect_fn: Callable[[], bool],
        disconnect_fn: Callable[[], bool],
    ) -> None:
        """注册一个仪器及其连接/断开回调。"""
        self._instruments[name] = _InstrumentEntry(connect_fn, disconnect_fn)

    # ------------------------------------------------------------------
    def connect_instrument(self, name: str) -> bool:
        """连接指定仪器，返回是否成功。"""
        entry = self._instruments.get(name)
        if entry is None:
            logger.warning("未注册的仪器: %s", name)
            return False
        try:
            success = entry.connect_fn()
            if success:
                entry.status = InstrumentStatus.CONNECTED
            else:
                entry.status = InstrumentStatus.ERROR
        except Exception as exc:
            logger.error("连接仪器 %s 失败: %s", name, exc)
            entry.status = InstrumentStatus.ERROR
            success = False
        self.status_changed.emit(name, entry.status.value)
        return success

    # ------------------------------------------------------------------
    def disconnect_instrument(self, name: str) -> bool:
        """断开指定仪器，返回是否成功。"""
        entry = self._instruments.get(name)
        if entry is None:
            logger.warning("未注册的仪器: %s", name)
            return False
        try:
            success = entry.disconnect_fn()
        except Exception as exc:
            logger.error("断开仪器 %s 失败: %s", name, exc)
            success = False
        entry.status = InstrumentStatus.DISCONNECTED
        self.status_changed.emit(name, entry.status.value)
        return success

    # ------------------------------------------------------------------
    def disconnect_all(self) -> None:
        """安全断开所有已连接的仪器。"""
        for name in list(self._instruments.keys()):
            entry = self._instruments[name]
            if entry.status == InstrumentStatus.CONNECTED:
                self.disconnect_instrument(name)

    # ------------------------------------------------------------------
    def get_status(self, name: str) -> str:
        """获取指定仪器的状态字符串。"""
        entry = self._instruments.get(name)
        if entry is None:
            return InstrumentStatus.DISCONNECTED.value
        return entry.status.value

    # ------------------------------------------------------------------
    def get_all_statuses(self) -> Dict[str, str]:
        """获取所有仪器的状态字典。"""
        return {name: e.status.value for name, e in self._instruments.items()}
