"""Connection settings dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from tsanet.common.config import NetworkConfig, SecurityConfig
from tsanet.controller.config import ControllerConfig, DEFAULT_CONFIG_PATH


class ConnectionDialog(QDialog):
    def __init__(self, config_path: str | Path | None = None, parent=None):
        super().__init__(parent)
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
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

        self._sec_mode = QComboBox()
        self._sec_mode.addItems(["none", "token", "tls-token"])
        self._sec_mode.currentTextChanged.connect(self._on_sec_mode_changed)
        self._sec_mode.setToolTip(
            "none — no authentication\n"
            "token — shared secret (authenticates, does not encrypt)\n"
            "tls-token — TLS + token (not yet implemented)"
        )

        self._token = QLineEdit()
        self._token.setToolTip("Shared secret for token authentication")
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        self._token.setPlaceholderText("(none)")

        self._form = QFormLayout()
        self._form.addRow("Mode:", self._mode)
        self._form.addRow("Transport:", self._transport)
        self._form.addRow("Address:", self._address)
        self._form.addRow("Port:", self._port)
        self._form.addRow("Security:", self._sec_mode)
        self._token_label = QLabel("Token:")
        self._form.addRow(self._token_label, self._token)
        self._on_sec_mode_changed(self._sec_mode.currentText())

        # Save / Save As
        save_btn = QPushButton("Save")
        save_btn.setToolTip(
            f"Save to {'existing' if self._config_path.exists() else 'new'} config file:\n"
            f"{self._config_path}"
        )
        save_btn.clicked.connect(self._save)

        save_as_btn = QPushButton("Save As…")
        save_as_btn.setToolTip("Save to a different config file")
        save_as_btn.clicked.connect(self._save_as)

        btn_row = QHBoxLayout()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(save_as_btn)
        btn_row.addStretch()

        # OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Network settings"))
        layout.addLayout(self._form)
        layout.addLayout(btn_row)
        layout.addStretch()
        layout.addWidget(buttons)

    def _on_transport_changed(self, text):
        self._port.setEnabled(text == "tcp")
        if text == "unix":
            self._address.setPlaceholderText("/tmp/tsanet.sock")
        else:
            self._address.setPlaceholderText("127.0.0.1")

    def _on_sec_mode_changed(self, mode: str) -> None:
        visible = mode in ("token", "tls-token")
        self._token_label.setVisible(visible)
        self._token.setVisible(visible)

    def config(self) -> ControllerConfig:
        sec_mode = self._sec_mode.currentText()
        token = self._token.text().strip() or None if sec_mode != "none" else None
        return ControllerConfig(
            network=NetworkConfig(
                mode=self._mode.currentText(),  # type: ignore[arg-type]
                transport=self._transport.currentText(),  # type: ignore[arg-type]
                address=self._address.text(),
                port=self._port.value() if self._transport.currentText() == "tcp" else None,
            ),
            security=SecurityConfig(
                mode=sec_mode,  # type: ignore[arg-type]
                token=token,
            ),
        )

    def _save(self) -> None:
        self.config().save(self._config_path)

    def _save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Config As",
            str(self._config_path),
            "YAML (*.yaml *.yml)",
            options=QFileDialog.DontUseNativeDialog,
        )
        if path:
            self._config_path = Path(path)
            self.config().save(self._config_path)
