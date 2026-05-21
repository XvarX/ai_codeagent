"""LLM configuration dialog — reads/writes config.yaml."""

import yaml

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QPushButton, QDialogButtonBox,
    QLabel,
)


PROVIDER_DEFAULTS = {
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "model": "claude-sonnet-4-6-20250514",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.7",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
}


class ConfigDialog(QDialog):
    """Dialog for editing LLM provider settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Configuration")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Load current config
        self._config = self._load_config()
        provider = self._config.get("provider", "anthropic")
        api_keys = self._config.get("api_keys", {})
        base_urls = self._config.get("base_urls", {})

        form = QFormLayout()
        form.setSpacing(10)

        # Provider dropdown
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["anthropic", "openai", "glm", "deepseek"])
        self._provider_combo.setCurrentText(provider)
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        form.addRow("Provider", self._provider_combo)

        # API URL
        self._url_edit = QLineEdit()
        self._url_edit.setText(
            base_urls.get(provider, "")
            or self._config.get("base_url", "")
            or PROVIDER_DEFAULTS.get(provider, {}).get("base_url", "")
        )
        form.addRow("API URL", self._url_edit)

        # API Key with show/hide toggle
        key_row = QHBoxLayout()
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setText(
            api_keys.get(provider, "")
            or self._config.get("api_key", "")
            or ""
        )
        self._key_toggle = QPushButton("Show")
        self._key_toggle.setFixedWidth(60)
        self._key_toggle.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self._key_edit)
        key_row.addWidget(self._key_toggle)
        form.addRow("API Key", key_row)

        # Model
        self._model_edit = QLineEdit()
        self._model_edit.setText(
            self._config.get("model", "")
            or PROVIDER_DEFAULTS.get(provider, {}).get("model", "")
        )
        form.addRow("Model", self._model_edit)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_config(self) -> dict:
        import sys
        if getattr(sys, 'frozen', False):
            from pathlib import Path
            path = Path(sys.executable).parent / "config.yaml"
        else:
            from pathlib import Path
            path = Path("config.yaml")
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _on_provider_changed(self, provider: str):
        """Switch all fields to the selected provider's saved values."""
        api_keys = self._config.get("api_keys", {})
        base_urls = self._config.get("base_urls", {})
        defaults = PROVIDER_DEFAULTS.get(provider, {})

        # URL: per-provider saved > single base_url > default
        self._url_edit.setText(
            base_urls.get(provider, "")
            or self._config.get("base_url", "")
            or defaults.get("base_url", "")
        )
        # Key: per-provider saved > single api_key > empty
        self._key_edit.setText(
            api_keys.get(provider, "")
            or self._config.get("api_key", "")
            or ""
        )
        # Model: config.yaml has single model, use default for the switched provider
        self._model_edit.setText(defaults.get("model", ""))

    def _toggle_key_visibility(self):
        if self._key_edit.echoMode() == QLineEdit.Password:
            self._key_edit.setEchoMode(QLineEdit.Normal)
            self._key_toggle.setText("Hide")
        else:
            self._key_edit.setEchoMode(QLineEdit.Password)
            self._key_toggle.setText("Show")

    def _save(self):
        """Write settings back to config.yaml."""
        provider = self._provider_combo.currentText()

        self._config["provider"] = provider
        self._config["model"] = self._model_edit.text()

        if "api_keys" not in self._config:
            self._config["api_keys"] = {}
        self._config["api_keys"][provider] = self._key_edit.text()

        if "base_urls" not in self._config:
            self._config["base_urls"] = {}
        self._config["base_urls"][provider] = self._url_edit.text()

        import sys
        if getattr(sys, 'frozen', False):
            from pathlib import Path
            path = Path(sys.executable).parent / "config.yaml"
        else:
            from pathlib import Path
            path = Path("config.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)

        self.accept()
