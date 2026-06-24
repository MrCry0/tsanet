"""Device list and selection widget (brief 10)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QListWidget, QPushButton, QVBoxLayout

from tsanet.controller.rpc_client import RpcClient


class DevicePanel(QGroupBox):
    def __init__(self, rpc: RpcClient, parent=None):
        super().__init__("Devices", parent)
        self._rpc = rpc

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select)

        self._info = QLabel("No device selected")
        self._info.setWordWrap(True)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        layout.addWidget(refresh)
        layout.addWidget(self._info)

        self.refresh()

    def refresh(self):
        self._list.clear()
        try:
            devices = self._rpc.call("devices", "list")
        except Exception:
            return
        for d in devices:
            status = "[BUSY]" if d["busy"] else "[free]"
            label = f"{d['device_id']}  {d['model']}  {status}"
            item = self._list.addItem(label)
            item.setData(Qt.ItemDataRole.UserRole, d["device_id"])

    def _on_select(self, current, _previous):
        if current is None:
            return
        device_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            self._rpc.call("devices", "select", device_id=device_id)
            self._info.setText(f"Selected: {device_id}")
        except Exception as exc:
            self._info.setText(f"Error: {exc}")
