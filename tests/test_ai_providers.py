"""Run: python3 tests/test_ai_providers.py [--runtime] (no live provider calls).

--runtime additionally checks the pinned LangChain and Qt integration when installed.
"""
import asyncio
import copy
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
# Match Anki's bootstrap: ChatAI precedes the root; both must share one IPC enum.
sys.path[:0] = [str(ROOT / 'ChatAI'), str(ROOT), str(ROOT / 'user_files' / 'bundled_dependencies')]
import AIProviders as ai
from ExternalScriptManager import ExternalScriptManager
from InterprocessCommand import InterprocessCommand as IC


def fails(callback, text=''):
    try:
        callback()
    except (ValueError, RuntimeError) as error:
        assert text in str(error), str(error)
        assert 'SECRET' not in str(error), 'Secret leaked in an error'
    else:
        raise AssertionError('Expected an error')


def main():
    assert IC.OPEN_AI_SETTINGS.value == 'OPEN_AI_SETTINGS'
    assert IC.DID_OPEN_AI_SETTINGS.value == 'DID_OPEN_AI_SETTINGS'
    config = copy.deepcopy(ai.DEFAULT_CONFIG)
    ai.validate_config(config)
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        config_file = folder / 'ai_providers.json'
        missing = subprocess.run([sys.executable, str(ROOT / 'ChatAI/AIProviders.py'), '--config', str(config_file)],
                                 capture_output=True, text=True, timeout=5)
        assert missing.returncode != 0 and 'does not exist' in missing.stderr
        with patch.object(ai, 'USER_FILES', folder), patch.dict(os.environ, {'ANKIBRAIN_CODEX_TIMEOUT': '91'}):
            assert ai.load_config(config_file)['timeout_seconds'] == 600  # Removed CLI environment settings are ignored.
            ai.save_config(config, config_file)
            assert ai.load_config(config_file) == config
            if os.name != 'nt':
                assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
            previous = config_file.read_bytes()
            invalid = copy.deepcopy(config)
            invalid['timeout_seconds'] = 0
            fails(lambda: ai.save_config(invalid, config_file), 'timeout_seconds')
            assert config_file.read_bytes() == previous
            config_file.write_text('{', encoding='utf-8')
            fails(lambda: ai.load_config(config_file), 'Cannot read')
            for removed in ('codex', 'claude'):
                legacy = {'provider': removed, 'providers': {removed: {'model': 'old-model', 'cli_path': '/unused'},
                                                            'openai': {'model': 'api-model', 'api_key': 'SECRET'}}}
                config_file.write_text(json.dumps(legacy), encoding='utf-8')
                before = config_file.read_bytes()
                fails(lambda: ai.load_config(config_file), 'CLI providers were removed')
                loaded = ai.load_config(config_file, allow_legacy=True)
                assert loaded['provider'] == 'chatgpt' and set(loaded['providers']) == {'chatgpt', 'openai'}
                assert loaded['providers']['openai']['api_key'] == 'SECRET'
                assert loaded['providers']['chatgpt']['model'] == ('old-model' if removed == 'codex' else config['providers']['chatgpt']['model'])
                assert config_file.read_bytes() == before  # Migration requires an explicit Save.
                ai.save_config(loaded, config_file)
                assert ai.load_config(config_file) == loaded
            legacy['provider'] = 'openai'
            config_file.write_text(json.dumps(legacy), encoding='utf-8')
            assert ai.load_config(config_file)['provider'] == 'openai'

        for key, bad in [('provider', 'bogus'), ('provider', []), ('timeout_seconds', True),
                         ('document_chunk_size', 0)]:
            invalid = copy.deepcopy(config)
            invalid[key] = bad
            fails(lambda: ai.validate_config(invalid))
        for key, bad in [('base_url', 'http://example.com/v1'), ('base_url', 'https://user:SECRET@example.com'),
                         ('base_url', 'https://example.com/v1?key=SECRET'), ('base_url', 'https://example.com:bad'),
                         ('headers', {'X-Test': 'SECRET\r\nInjected: yes'}),
                         ('headers', {'Authorization': 'a', 'authorization': 'b'}),
                         ('headers', {'Host': 'example.com'}), ('headers', {'Bad Name': 'a'}),
                         ('headers', {'X-Test': 10}), ('extra_body', {'stream': True}),
                         ('extra_body', {'messages': []}), ('extra_body', {'tools': []}),
                         ('temperature', float('nan')), ('max_tokens', -1)]:
            invalid = copy.deepcopy(config)
            invalid['providers']['openai'][key] = bad
            fails(lambda: ai.validate_config(invalid))
        fails(lambda: ai.run_provider('', config=config), 'prompt')
        fails(lambda: ai.run_provider('hi', stop=[''], config=config), 'Stop')
        assert set(ai.DEFAULT_CONFIG['providers']) == {'chatgpt', 'openai'}
        assert not hasattr(ai, 'run_codex') and not hasattr(ai, 'run_claude') and not hasattr(ai, '_run_cli')

        calls = []
        reply = {'choices': [{'message': {'content': 'answer STOP later END'}, 'finish_reason': 'stop'}]}
        status = [200]

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((self.path, self.headers, body))
                self.send_response(status[0])
                if status[0] == 302:
                    self.send_header('Location', f'http://127.0.0.1:{self.server.server_port}/redirected')
                self.end_headers()
                self.wfile.write(json.dumps(reply).encode())

            do_GET = do_POST

        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config['provider'] = 'openai'
            api = config['providers']['openai']
            api.update(base_url=f'http://127.0.0.1:{server.server_port}/custom/v1/', model='test/model',
                       api_key='${TEST_AI_KEY}', headers={'X-Test': '${TEST_HEADER}'},
                       temperature=0, max_tokens=77, extra_body={'reasoning_effort': 'low'})
            (folder / '.env').write_text("TEST_AI_KEY=SECRET-file\nTEST_HEADER=SECRET-header\n", encoding='utf-8')
            with patch.object(ai, 'USER_FILES', folder), patch.dict(os.environ, {'TEST_AI_KEY': 'SECRET-env', 'NO_PROXY': '127.0.0.1'}):
                assert ai.run_provider('hello λ', stop=['END', 'STOP'], config=config) == 'answer'
                url, headers, body = calls[-1]
                assert url == '/custom/v1/chat/completions'
                assert headers['Authorization'] == 'Bearer SECRET-file'
                assert headers['X-Test'] == 'SECRET-header'
                assert body == {'model': 'test/model', 'messages': [{'role': 'user', 'content': 'hello λ'}],
                                'stream': False, 'temperature': 0, 'max_tokens': 77, 'reasoning_effort': 'low'}
                # Header auth can intentionally replace Bearer auth, even with an unset API key reference.
                api['headers']['authorization'] = 'Custom SECRET'
                api['api_key'] = '${MISSING_TEST_KEY}'
                assert ai.run_provider('hi', config=config).startswith('answer')
                assert calls[-1][1]['Authorization'] == 'Custom SECRET'
                api['headers'] = {}
                fails(lambda: ai.run_provider('hi', config=config), 'MISSING_TEST_KEY')
                api['api_key'] = ''
                ai.run_provider('hi', config=config)
                assert 'Authorization' not in calls[-1][1]
                api['headers'] = {'X-Test': '${INJECTED_TEST_HEADER}'}
                with patch.dict(os.environ, {'INJECTED_TEST_HEADER': 'SECRET\r\nX-Injected: yes'}):
                    fails(lambda: ai.run_provider('hi', config=config), 'header')
                api['headers'] = {}
                for code in (401, 403, 404, 429, 500, 302):
                    status[0] = code
                    before = len(calls)
                    fails(lambda: ai.run_provider('hi', config=config), f'HTTP {code}')
                    assert len(calls) == before + 1, 'Unexpected retry or redirect'
                status[0] = 200
                reply['choices'][0]['finish_reason'] = 'length'
                fails(lambda: ai.run_provider('hi', config=config), 'truncated')
                reply['choices'][0]['finish_reason'] = 'stop'
                reply['choices'][0]['message']['content'] = None
                fails(lambda: ai.run_provider('hi', config=config), 'no text')
                reply['choices'][0]['message']['content'] = 'runtime OK'

                if '--runtime' in sys.argv:
                    import ProviderLLM
                    from langchain import ConversationChain
                    with patch.object(ai, 'load_config', return_value=config), patch.object(ProviderLLM, 'load_config', return_value=config):
                        chain = ConversationChain(llm=ProviderLLM.ProviderLLM())
                        assert chain.predict(input='Hello') == 'runtime OK'
                        chain.predict(input='Follow up')
                        assert 'Hello' in calls[-1][2]['messages'][0]['content']

        finally:
            server.shutdown()
            server.server_close()
            thread.join()

        from test_chatgpt_auth import check_auth
        check_auth()

        # Exercise the shared IPC serialization path with concurrent, slow requests.
        worker = folder / 'worker.py'
        worker.write_text('import json, sys, time\nprint(json.dumps({"status":"success"}), flush=True)\n'
                          'for line in sys.stdin:\n time.sleep(0.03)\n print(line.strip(), flush=True)\n', encoding='utf-8')

        async def check_ipc():
            manager = ExternalScriptManager(sys.executable, str(worker))
            await manager.start()
            try:
                replies = await asyncio.gather(*(manager.call({'cmd': 'ECHO', 'data': n}) for n in range(5)))
                assert [reply['data'] for reply in replies] == list(range(5))
            finally:
                await manager.stop()
        asyncio.run(check_ipc())

        if '--runtime' in sys.argv:
            # Real Qt widgets with a minimal Anki host, no Anki collection needed.
            import types
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
            from PyQt6 import QtCore, QtGui, QtWidgets
            qt = types.ModuleType('aqt.qt')
            for module in (QtCore, QtGui, QtWidgets):
                qt.__dict__.update({name: getattr(module, name) for name in dir(module) if not name.startswith('_')})
            aqt = types.ModuleType('aqt')
            aqt.mw = None
            with patch.dict(sys.modules, {'aqt': aqt, 'aqt.qt': qt}):
                import AIProviderDialog as dialog_module
                app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
                config['provider'] = 'openai'
                with patch.object(dialog_module, 'load_config', return_value=copy.deepcopy(config)), patch.object(dialog_module, 'save_config') as save:
                    dialog = dialog_module.AIProviderDialog()
                    assert dialog._collect() == config
                    assert dialog.inputs['openai']['api_key'].echoMode() == QtWidgets.QLineEdit.EchoMode.Password
                    assert dialog.provider.count() == 2 and dialog.provider.findData('claude') == -1
                    dialog.provider.setCurrentIndex(dialog.provider.findData('chatgpt'))
                    dialog.inputs['chatgpt']['model'].setCurrentText('new-model')
                    dialog._save()
                    saved = save.call_args[0][0]
                    assert saved['provider'] == 'chatgpt' and saved['providers']['chatgpt']['model'] == 'new-model'
                    assert saved['providers']['openai'] == config['providers']['openai']
                    dialog.close()
                    dialog = dialog_module.AIProviderDialog()
                    with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.StandardButton.Yes):
                        for label, (base, variable, model) in ai.API_PRESETS.items():
                            dialog.preset.setCurrentText(label)
                            dialog._apply_preset()
                            fields = dialog.inputs['openai']
                            assert fields['base_url'].text() == base and fields['api_key'].text() == '${' + variable + '}'
                            assert fields['model'].text() == model
                            assert fields['headers'].toPlainText() == '{}' and not fields['allow_insecure_http'].isChecked()
                    dialog.close()

                    # Exercise native sign-in/model actions and cancellation without a browser/account.
                    from concurrent.futures import Future
                    from unittest.mock import Mock
                    pending = []
                    taskman = types.SimpleNamespace(run_in_background=lambda work, done: pending.append((work, done)))
                    flow = Mock(url='https://auth.openai.com/oauth/authorize', finish=Mock(return_value=None))
                    with patch.object(dialog_module, 'mw', types.SimpleNamespace(taskman=taskman)), \
                            patch.object(dialog_module.ChatGPTAuth, 'Login', return_value=flow), \
                            patch.object(dialog_module.ChatGPTAuth, 'models', return_value=['account-model']), \
                            patch.object(QtGui.QDesktopServices, 'openUrl', return_value=True), \
                            patch.object(QtWidgets.QMessageBox, 'information') as info:
                        dialog = dialog_module.AIProviderDialog()
                        dialog._login_chatgpt()
                        assert not dialog.save_button.isEnabled()
                        work, done = pending.pop()
                        future = Future()
                        future.set_result(work())
                        done(future)
                        assert info.called and dialog.save_button.isEnabled()
                        assert dialog.inputs['chatgpt']['model'].currentText() == 'account-model'
                        assert dialog.more_options.isHidden()
                        assert dialog.save_button.text() == 'Save & start studying'
                        dialog.inputs['chatgpt']['model'].setCurrentText('keep-my-model')
                        dialog._load_models()
                        work, done = pending.pop()
                        future = Future()
                        future.set_result(work())
                        done(future)
                        assert dialog.inputs['chatgpt']['model'].currentText() == 'keep-my-model'
                        assert dialog.inputs['chatgpt']['model'].findText('account-model') >= 0
                        dialog._login_chatgpt()
                        dialog.reject()
                        flow.cancel.assert_called_once()
                        work, done = pending.pop()
                        future = Future()
                        future.set_result(None)
                        info.reset_mock()
                        done(future)
                        info.assert_not_called()

                # First-run and old SERVER settings use the same app; failed engine setup still exposes sign-in.
                from unittest.mock import AsyncMock, Mock
                aqt.mw = types.SimpleNamespace(CURRENT_VERSION='test-version')
                aqt.gui_hooks = types.SimpleNamespace()
                hooks = types.ModuleType('anki.hooks')
                hooks.addHook = Mock()
                utils = types.ModuleType('aqt.utils')
                utils.showInfo = Mock()
                placeholders = {
                    'anki': types.ModuleType('anki'), 'anki.hooks': hooks, 'aqt.utils': utils,
                    'SidePanel': types.SimpleNamespace(SidePanel=Mock()),
                    'ExplainTalkButtons': types.SimpleNamespace(ExplainTalkButtons=Mock()),
                    'card_injection': types.SimpleNamespace(handle_card_will_show=Mock()),
                    'changelog': types.SimpleNamespace(ChangelogDialog=Mock()),
                    'cards': types.SimpleNamespace(add_basic_card=Mock(), add_cloze_card=Mock()),
                }
                with patch.dict(sys.modules, placeholders):
                    import AnkiBrainModule as host
                    import settings
                    import project_paths
                    import boot
                    legacy_path = folder / 'legacy-settings.json'
                    legacy = {'user_mode': 'SERVER', 'user': {'accessToken': 'SECRET'},
                              'tempCards': [{'front': 'Keep this card', 'back': 'Saved'}]}
                    legacy_path.write_text(json.dumps(legacy), encoding='utf-8')
                    with patch.object(project_paths, 'settings_path', str(legacy_path)), patch.object(host, 'AnkiBrain') as constructor:
                        boot.load_ankibrain()
                        constructor.assert_called_once_with()
                    assert aqt.mw.settingsManager.get('tempCards') == legacy['tempCards']
                    assert 'user_mode' not in settings.default_settings and 'user' not in settings.default_settings
                    state = types.SimpleNamespace(webview_loaded=True, chatReady=False, startup_error='',
                                                  chatAI=types.SimpleNamespace(start=AsyncMock(), stop=AsyncMock()), reactBridge=Mock())
                    state.notify_ai_settings_changed = lambda: host.AnkiBrain.notify_ai_settings_changed(state)
                    state.load_user_settings = lambda: host.AnkiBrain.load_user_settings(state)
                    with patch.object(host, 'load_config', return_value=copy.deepcopy(ai.DEFAULT_CONFIG)), patch.object(host, 'signed_in', return_value=False):
                        for error in (FileNotFoundError(), None):
                            state.chatAI.start.side_effect = error
                            state.reactBridge.reset_mock()
                            asyncio.run(host.AnkiBrain._start_async_members(state))
                            assert state.chatReady == (error is None)
                            state.reactBridge.send_cmd.assert_any_call(IC.DID_FINISH_STARTUP)
                            public = state.reactBridge.send_to_js.call_args[0][0]['data']
                            assert public['provider'] == 'chatgpt' and not public['configured']
                            assert public['engineReady'] == (error is None)
                            assert 'SECRET' not in str(state.reactBridge.mock_calls)
                    from ReactBridge import ReactBridge
                    bridge = ReactBridge.__new__(ReactBridge)
                    bridge.app = types.SimpleNamespace(chatAI=types.SimpleNamespace(
                        ask_conversation_no_documents=AsyncMock(side_effect=RuntimeError('No completed answer'))))
                    bridge.send_cmd = Mock()
                    asyncio.run(bridge.a_handle_react_data_received({'cmd': 'ASK_CONVERSATION_NO_DOCUMENTS', 'query': 'hello', 'commandId': 27}))
                    assert bridge.send_cmd.call_args[0][0] == IC.ERROR
                    assert bridge.send_cmd.call_args[1] == {'commandId': 27, 'error': 'No completed answer'}

    print('AI provider checks passed' + (' (including LangChain + Qt)' if '--runtime' in sys.argv else ''))


if __name__ == '__main__':
    main()
