"""Connection settings dialog."""

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
        self.setMinimumWidth(360)

        self._mode = QComboBox()
        self._mode.addItems(["dial", "listen"])
        self._mode.setToolTip(
            "dial — connect to a listening hub (default)\n"
            "listen — wait for a hub to dial in (reverse-connect)"
        )

        self._transport = QComboBox()
        self._transport.addItems(["tcp", "unix"])
        self._transport.currentTextChanged.connect(self._on_transport_changed)
        self._transport.setToolTip(
            "tcp — network connection\nunix — local socket (same machine only)"
        )

        self._address = QLineEdit("127.0.0.1")
        self._address.setToolTip("Hub address: hostname or IP for TCP, socket path for Unix")

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(7777)
        self._port.setToolTip("TCP port (ignored for Unix transport)")

        self._token = QLineEdit()
        self._token.setToolTip("Shared secret for token authentication (leave empty if not used)")
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        self._token.setPlaceholderText("(none)")

        form = QFormLayout()
        form.addRow("Mode:", self._mode)
        form.addRow("Transport:", self._transport)
        form.addRow("Address:", self._address)
        form.addRow("Port:", self._port)
        form.addRow("Token:", self._token)

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
        token = self._token.text().strip() or None
        return ControllerConfig(
            network=NetworkConfig(
                mode=self._mode.currentText(),  # type: ignore[arg-type]
                transport=self._transport.currentText(),  # type: ignore[arg-type]
                address=self._address.text(),
                port=self._port.value() if self._transport.currentText() == "tcp" else None,
            ),
            security=SecurityConfig(
                mode="token" if token else "none",
                token=token,
            ),
        )
