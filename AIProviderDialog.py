import json

from aqt import mw
from aqt.qt import *

from AIProviders import CONFIG_PATH, load_config, run_provider, save_config, validate_config


class AIProviderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = load_config()
        self.inputs = {}
        self.setWindowTitle('AnkiBrain — AI Provider Settings')
        self.resize(720, 730)
        layout = QVBoxLayout(self)
        note = QLabel('Local mode only. Settings apply to the next request. CLI logins stay with the official CLI. '
                      'API keys and headers are stored locally, not sent to the webview.')
        note.setWordWrap(True)
        layout.addWidget(note)

        common = QFormLayout()
        self.provider = QComboBox()
        for name, label in [('codex', 'ChatGPT subscription — Codex CLI'),
                            ('claude', 'Claude subscription — Claude Code'),
                            ('openai', 'OpenAI-compatible API — including Gemini free tier')]:
            self.provider.addItem(label, name)
        common.addRow('Provider', self.provider)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 3600)
        self.timeout.setValue(self.config['timeout_seconds'])
        self.timeout.setSuffix(' seconds')
        common.addRow('Request timeout', self.timeout)
        self.chunk_size = QSpinBox()
        self.chunk_size.setRange(100, 100000)
        self.chunk_size.setValue(self.config['document_chunk_size'])
        self.chunk_size.setSuffix(' characters')
        common.addRow('Document-to-cards chunk size', self.chunk_size)
        layout.addLayout(common)

        self.pages = QStackedWidget()
        for name in ('codex', 'claude'):
            page = QWidget()
            form = QFormLayout(page)
            self._line(form, name, 'model', 'Model ID', 'Blank = CLI default')
            self._line(form, name, 'cli_path', 'CLI executable path', 'Blank = find on PATH; otherwise full executable path')
            self._line(form, name, 'config_dir', 'CLI configuration directory',
                       'Blank = CODEX_HOME / ~/.codex' if name == 'codex' else 'Blank = CLAUDE_CONFIG_DIR / ~/.claude')
            effort = QComboBox()
            levels = ['', 'minimal', 'low', 'medium', 'high', 'xhigh'] if name == 'codex' else ['', 'low', 'medium', 'high', 'xhigh', 'max']
            for level in levels:
                effort.addItem(level or 'CLI default', level)
            effort.setCurrentIndex(effort.findData(self.config['providers'][name]['effort']))
            self.inputs[name]['effort'] = effort
            form.addRow('Reasoning effort', effort)
            help_text = QLabel(
                ('Install Codex 0.153.4 or newer, then run: codex login\n'
                 'Confirm: codex login status\n' if name == 'codex' else
                 'Install Claude Code 2.1.263 or newer, then run: claude auth login\n'
                 'Choose your Claude subscription, not Console API billing.\n')
                + 'Use the same OS account and configuration directory as Anki. '
                'No API-key fallback. Tools are restricted/disabled; no custom CLI flags. '
                'Model/effort availability and usage limits depend on your plan.'
            )
            help_text.setWordWrap(True)
            form.addRow(help_text)
            self.pages.addWidget(page)

        page = QWidget()
        form = QFormLayout(page)
        self._line(form, 'openai', 'base_url', 'Base URL', 'https://api.openai.com/v1')
        self._line(form, 'openai', 'model', 'Model ID', 'Exact model ID from your provider')
        key = self._line(form, 'openai', 'api_key', 'API key', 'Literal key, ${ENV_VAR}, or blank for no Bearer authentication')
        key.setEchoMode(QLineEdit.EchoMode.Password)
        self._line(form, 'openai', 'temperature', 'Temperature (optional)', 'Blank = provider default; otherwise 0–2')
        self._line(form, 'openai', 'max_tokens', 'Max output tokens (optional)', 'Blank = provider default')
        for field, label in [('headers', 'Custom headers (JSON)'), ('extra_body', 'Extra request body (JSON)')]:
            editor = QPlainTextEdit()
            editor.setPlainText(json.dumps(self.config['providers']['openai'][field], indent=2))
            editor.setMaximumHeight(95)
            editor.setAccessibleName(label)
            self.inputs['openai'][field] = editor
            form.addRow(label, editor)
        insecure = QCheckBox('Allow HTTP outside localhost (sends credentials unencrypted)')
        insecure.setChecked(self.config['providers']['openai']['allow_insecure_http'])
        self.inputs['openai']['allow_insecure_http'] = insecure
        form.addRow(insecure)
        preset = QPushButton('Use Gemini API preset…')
        preset.clicked.connect(self._gemini_preset)
        form.addRow(preset)
        help_text = QLabel('POSTs to BASE_URL/chat/completions. Headers can use ${ENV_VAR} values from '
                           'user_files/.env. A custom Authorization header overrides the API key. '
                           'Extra body supports provider options such as reasoning_effort or max_completion_tokens. '
                           'API usage may be billed; no automatic provider fallback or retry.')
        help_text.setWordWrap(True)
        form.addRow(help_text)
        self.pages.addWidget(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.pages)
        layout.addWidget(scroll)
        self.provider.currentIndexChanged.connect(self.pages.setCurrentIndex)
        self.provider.setCurrentIndex(self.provider.findData(self.config['provider']))
        self.pages.setCurrentIndex(self.provider.currentIndex())

        path_label = QLabel(f'Private configuration: {CONFIG_PATH}\nSetup guide: AI_PROVIDERS.md in the add-on folder.')
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self.test_button = buttons.addButton('Test (uses quota)', QDialogButtonBox.ButtonRole.ActionRole)
        self.test_button.clicked.connect(self._test)
        layout.addWidget(buttons)

    def _line(self, form, provider, field, label, placeholder):
        widget = QLineEdit()
        value = self.config['providers'][provider][field]
        widget.setText('' if value is None else str(value))
        widget.setPlaceholderText(placeholder)
        self.inputs.setdefault(provider, {})[field] = widget
        form.addRow(label, widget)
        return widget

    def _collect(self):
        config = load_config()
        config.update(provider=self.provider.currentData(), timeout_seconds=self.timeout.value(),
                      document_chunk_size=self.chunk_size.value())
        for provider, fields in self.inputs.items():
            for field, widget in fields.items():
                if isinstance(widget, QPlainTextEdit):
                    try:
                        value = json.loads(widget.toPlainText())
                    except ValueError:
                        raise ValueError(f'{field} must contain valid JSON.') from None
                elif isinstance(widget, QComboBox):
                    value = widget.currentData()
                elif isinstance(widget, QCheckBox):
                    value = widget.isChecked()
                else:
                    value = widget.text().strip()
                    if field in ('temperature', 'max_tokens'):
                        try:
                            value = (float(value) if field == 'temperature' else int(value)) if value else None
                        except ValueError:
                            raise ValueError(f'Invalid {field}. Enter a number or leave blank.') from None
                config['providers'][provider][field] = value
        validate_config(config)
        return config

    def _save(self):
        try:
            save_config(self._collect())
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, 'Could not save AI settings', str(error))
            return
        self.accept()

    def _test(self):
        try:
            config = self._collect()
        except ValueError as error:
            QMessageBox.warning(self, 'Invalid AI settings', str(error))
            return
        self.test_button.setEnabled(False)

        def finished(future):
            self.test_button.setEnabled(True)
            try:
                future.result()
            except Exception as error:
                QMessageBox.warning(self, 'Provider test failed', str(error))
            else:
                QMessageBox.information(self, 'Provider test passed', 'Received a text response. Settings are not saved until you click Save.')

        mw.taskman.run_in_background(lambda: run_provider('Reply with exactly OK.', config=config), finished)

    def _gemini_preset(self):
        if QMessageBox.question(self, 'Gemini API preset',
                                'Replace the current API endpoint, credentials, and options with the Gemini preset? '
                                'You will need an AI Studio API key and a free-tier-eligible model ID.') != QMessageBox.StandardButton.Yes:
            return
        fields = self.inputs['openai']
        fields['base_url'].setText('https://generativelanguage.googleapis.com/v1beta/openai')
        fields['api_key'].setText('${GEMINI_API_KEY}')
        for field in ('model', 'temperature', 'max_tokens'):
            fields[field].clear()
        for field in ('headers', 'extra_body'):
            fields[field].setPlainText('{}')
        fields['allow_insecure_http'].setChecked(False)
