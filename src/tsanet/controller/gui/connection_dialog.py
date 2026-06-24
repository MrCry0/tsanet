"""Connection settings dialog (brief 10)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from tsanet.common.config import NetworkConfig, SecurityConfig
from tsanet.controller.config import ControllerConfig


class ConnectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Hub")
        self.setMinimumWidth(320)

        self._mode = QComboBox()
        self._mode.addItems(["dial", "listen"])

        self._transport = QComboBox()
        self._transport.addItems(["tcp", "unix"])
        self._transport.currentTextChanged.connect(self._on_transport_changed)

        self._address = QLineEdit("127.0.0.1")

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(7777)

        form = QFormLayout()
        form.addRow("Mode:", self._mode)
        form.addRow("Transport:", self._transport)
        form.addRow("Address:", self._address)
        form.addRow("Port:", self._port)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Network settings"))
        layout.addLayout(form)
        layout.addStretch()
        layout.addWidget(buttons)

    def _on_transport_changed(self, text):
        self._port.setEnabled(text == "tcp")
        if text == "unix":
            self._address.setPlaceholderText("/tmp/tsanet.sock")
        else:
            self._address.setPlaceholderText("127.0.0.1")

    def config(self) -> ControllerConfig:
        return ControllerConfig(
            network=NetworkConfig(
                mode=self._mode.currentText(),  # type: ignore[arg-type]
                transport=self._transport.currentText(),  # type: ignore[arg-type]
                address=self._address.text(),
                port=self._port.value() if self._transport.currentText() == "tcp" else None,
            ),
            security=SecurityConfig(),
        )
