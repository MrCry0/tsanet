"""Screenshot capture viewer (brief 6.1, 10)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tsanet.controller.rpc_client import RpcClient


class CaptureViewer(QWidget):
    def __init__(self, rpc: RpcClient, parent=None):
        super().__init__(parent)
        self._rpc = rpc
        self._png: bytes | None = None

        self._label = QLabel("Click Fetch to capture a screenshot")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(480, 320)

        scroll = QScrollArea()
        scroll.setWidget(self._label)
        scroll.setWidgetResizable(True)

        fetch_btn = QPushButton("Fetch")
        fetch_btn.clicked.connect(self.fetch)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_file)

        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self.copy_to_clipboard)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        btn_layout = QVBoxLayout()
        btn_layout.addWidget(fetch_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(copy_btn)
        layout.addLayout(btn_layout)

    def fetch(self):
        try:
            self._png = self._rpc.call("capture", "fetch")
            pix = QPixmap()
            pix.loadFromData(self._png)
            self._label.setPixmap(
                pix.scaled(
                    self._label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        except Exception as exc:
            self._label.setText(f"Error: {exc}")

    def save_file(self):
        if self._png is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Screenshot", "SA.png", "PNG (*.png)")
        if path:
            with open(path, "wb") as f:
                f.write(self._png)

    def copy_to_clipboard(self):
        if self._png is None:
            return
        pix = QPixmap()
        pix.loadFromData(self._png)
        QApplication.clipboard().setPixmap(pix)
