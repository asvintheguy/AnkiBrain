import copy
import json

from aqt import mw
from aqt.qt import *

import ChatGPTAuth
from AIProviders import API_PRESETS, CONFIG_PATH, load_config, run_provider, save_config, validate_config
from InstallDialog import show_install_dialog
from util import has_ankibrain_completed_install


class AIProviderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = load_config(allow_legacy=True)
        self.inputs = {}
        self.login = None
        self.closed = False
        self.setWindowTitle('AnkiBrain — Connect AI')
        self.resize(640, 620)
        layout = QVBoxLayout(self)
        note = QLabel('Connect ChatGPT, then start studying. No AnkiBrain account or balance top-up needed. '
                      'Your sign-in stays private on this computer.')
        note.setWordWrap(True)
        layout.addWidget(note)
        if not has_ankibrain_completed_install():
            setup = QPushButton('One-time setup: install the study engine…')
            setup.clicked.connect(show_install_dialog)
            layout.addWidget(setup)

        common = QFormLayout()
        self.provider = QComboBox()
        for name, label in [('chatgpt', 'ChatGPT — sign in (recommended)'),
                            ('openai', 'OpenAI-compatible API — Gemini, Grok, and custom endpoints')]:
            self.provider.addItem(label, name)
        common.addRow('Connect using', self.provider)
        layout.addLayout(common)
        self.more_options = QWidget()
        options_form = QFormLayout(self.more_options)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 3600)
        self.timeout.setValue(self.config['timeout_seconds'])
        self.timeout.setSuffix(' seconds')
        options_form.addRow('Socket-operation timeout', self.timeout)
        self.chunk_size = QSpinBox()
        self.chunk_size.setRange(100, 100000)
        self.chunk_size.setValue(self.config['document_chunk_size'])
        self.chunk_size.setSuffix(' characters')
        options_form.addRow('Document-to-cards chunk size', self.chunk_size)

        self.pages = QStackedWidget()
        page = QWidget()
        form = QFormLayout(page)
        model = QComboBox()
        model.setEditable(True)
        model.setCurrentText(self.config['providers']['chatgpt']['model'])
        self.inputs['chatgpt'] = {'model': model}
        form.addRow('Model ID', model)
        self._line(options_form, 'chatgpt', 'auth_dir', 'Private ChatGPT sign-in directory', 'Blank = default private location')
        self.inputs['chatgpt']['auth_dir'].textChanged.connect(self._update_auth_state)
        effort = QComboBox()
        for level in ('', 'minimal', 'low', 'medium', 'high', 'xhigh'):
            effort.addItem(level or 'Provider default', level)
        effort.setCurrentIndex(effort.findData(self.config['providers']['chatgpt']['effort']))
        self.inputs['chatgpt']['effort'] = effort
        options_form.addRow('ChatGPT reasoning effort', effort)
        self.auth_state = QLabel()
        form.addRow(self.auth_state)
        for label, action in [('Sign in with ChatGPT…', self._login_chatgpt),
                              ('Sign out locally…', self._logout_chatgpt),
                              ('Load account models', self._load_models)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            form.addRow(button)
            if action == self._login_chatgpt:
                self.login_button = button
                button.setMinimumHeight(44)
        help_text = QLabel('1. Sign in in your browser.\n2. Review your account model above.\n3. Save & start studying.\n\n'
                           'Experimental ChatGPT-backed Codex connection; plan/model limits apply. '
                           'Prompts and document excerpts go to your selected provider. '
                           'No API-key fallback. Sign-in/out takes effect immediately, independently of Save.')
        help_text.setWordWrap(True)
        form.addRow(help_text)
        self.pages.addWidget(page)
        self._update_auth_state()

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
        self.preset = QComboBox()
        self.preset.addItems(list(API_PRESETS))
        form.addRow('API preset (not subscription login)', self.preset)
        apply_preset = QPushButton('Apply selected API preset…')
        apply_preset.clicked.connect(self._apply_preset)
        form.addRow(apply_preset)
        help_text = QLabel('POSTs to BASE_URL/chat/completions. Headers can use ${ENV_VAR} values from '
                           'user_files/.env. A custom Authorization header overrides the API key. '
                           'API presets do not unlock ChatGPT, Claude, Google AI, SuperGrok, or Kimi chat subscriptions. '
                           'Extra body supports provider options such as reasoning_effort or max_completion_tokens. '
                           'API usage may be billed; no automatic provider fallback or retry.')
        help_text.setWordWrap(True)
        form.addRow(help_text)
        self.pages.addWidget(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.pages)
        layout.addWidget(scroll)
        more = QCheckBox('More connection options')
        more.toggled.connect(self.more_options.setVisible)
        layout.addWidget(more)
        layout.addWidget(self.more_options)
        self.more_options.hide()
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
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setText('Save & start studying')
        self.test_button = buttons.addButton('Test (uses quota)', QDialogButtonBox.ButtonRole.ActionRole)
        self.test_button.clicked.connect(self._test)
        layout.addWidget(buttons)
        self.finished.connect(self._closed)

    def _line(self, form, provider, field, label, placeholder):
        widget = QLineEdit()
        value = self.config['providers'][provider][field]
        widget.setText('' if value is None else str(value))
        widget.setPlaceholderText(placeholder)
        self.inputs.setdefault(provider, {})[field] = widget
        form.addRow(label, widget)
        return widget

    def _collect(self):
        config = copy.deepcopy(self.config)
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
                    value = widget.currentText().strip() if widget.isEditable() else widget.currentData()
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

    def _background(self, work, success):
        widgets = (self.provider, self.pages, self.more_options, self.save_button, self.test_button)
        for widget in widgets:
            widget.setEnabled(False)

        def finished(future):
            self.login = None
            try:
                result = future.result()
            except Exception as error:
                if not self.closed:
                    QMessageBox.warning(self, 'AI provider action failed', str(error))
            else:
                if not self.closed:
                    success(result)
            finally:
                if not self.closed:
                    for widget in widgets:
                        widget.setEnabled(True)
                    self._update_auth_state()

        mw.taskman.run_in_background(work, finished)

    def _test(self):
        try:
            config = self._collect()
        except ValueError as error:
            QMessageBox.warning(self, 'Invalid AI settings', str(error))
            return
        self._background(lambda: run_provider('Reply with exactly OK.', config=config),
                         lambda _: QMessageBox.information(self, 'Provider test passed',
                                                           'Received a text response. Settings are not saved until you click Save.'))

    def _auth_options(self):
        return {'auth_dir': self.inputs['chatgpt']['auth_dir'].text().strip()}

    def _update_auth_state(self):
        try:
            present = ChatGPTAuth.signed_in(self._auth_options())
        except (ValueError, OSError):
            self.auth_state.setText('Check the private sign-in directory.')
        else:
            self.auth_state.setText('Signed in on this computer. Test to verify model access.' if present else 'Sign in to connect your ChatGPT account.')

    def _login_chatgpt(self):
        try:
            self.login = ChatGPTAuth.Login(self._auth_options())
        except (ValueError, RuntimeError, OSError) as error:
            QMessageBox.warning(self, 'Cannot start ChatGPT sign-in', str(error))
            return
        flow = self.login
        if not QDesktopServices.openUrl(QUrl(flow.url)):
            flow.cancel()
        self.auth_state.setText('Waiting for browser sign-in (up to five minutes)…')
        options = self._auth_options()

        def connect():
            flow.finish()
            try:
                return ChatGPTAuth.models(options), ''
            except (ValueError, RuntimeError, OSError) as error:
                return [], str(error)

        def connected(result):
            names, error = result
            if names:
                self._set_models(names, choose_available=True)
                QMessageBox.information(self, 'ChatGPT connected', 'Your account models are ready. Review the selected model, then click Save & start studying.')
            else:
                QMessageBox.warning(self, 'Signed in; model list unavailable',
                                    error + '\nUse Load account models to retry, or enter a known model ID.')

        self._background(connect, connected)

    def _logout_chatgpt(self):
        if QMessageBox.question(self, 'Sign out locally',
                                'Remove this app’s stored sign-in? This does not revoke other sessions or stop an in-flight response.') != QMessageBox.StandardButton.Yes:
            return
        options = self._auth_options()
        self._background(lambda: ChatGPTAuth.logout(options), lambda _: None)

    def _load_models(self):
        options = self._auth_options()

        self._background(lambda: ChatGPTAuth.models(options), self._set_models)

    def _set_models(self, names, choose_available=False):
        widget = self.inputs['chatgpt']['model']
        selected = widget.currentText()
        widget.clear()
        widget.addItems(names)
        # On login, offer an available model for review; it is not used until Save.
        widget.setCurrentText(names[0] if choose_available and selected not in names else selected)

    def _apply_preset(self):
        label = self.preset.currentText()
        if QMessageBox.question(self, 'Replace API settings',
                                f'Apply {label}? This replaces the API endpoint, credentials, headers, and options. '
                                'Check the provider’s model access and billing before testing.') != QMessageBox.StandardButton.Yes:
            return
        base, variable, model = API_PRESETS[label]
        fields = self.inputs['openai']
        fields['base_url'].setText(base)
        fields['api_key'].setText('${' + variable + '}')
        fields['model'].setText(model)
        for field in ('temperature', 'max_tokens'):
            fields[field].clear()
        for field in ('headers', 'extra_body'):
            fields[field].setPlainText('{}')
        fields['allow_insecure_http'].setChecked(False)

    def _closed(self):
        self.closed = True
        if self.login is not None:
            self.login.cancel()
