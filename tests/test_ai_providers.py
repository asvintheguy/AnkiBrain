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
            assert ai.load_config(config_file)['timeout_seconds'] == 91
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
            config_file.write_text('{"provider":"claude","providers":{"claude":{"model":"opus"}}}', encoding='utf-8')
            loaded = ai.load_config(config_file)
            assert loaded['providers']['claude']['model'] == 'opus'
            assert loaded['providers']['codex'] == config['providers']['codex']

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
        fails(lambda: ai.run_provider(''), 'prompt')
        fails(lambda: ai.run_provider('hi', stop=['']), 'Stop')

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

        cli_calls = []

        def fake_cli(command, prompt, workdir, environment, timeout):
            cli_calls.append((command, environment, timeout))
            assert prompt == 'hello'
            assert not any(key in environment for key in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'NODE_OPTIONS'))
            assert not Path(workdir).samefile(ROOT)
            if '--output-last-message' in command:
                Path(command[command.index('--output-last-message') + 1]).write_text('hello STOP secret', encoding='utf-8')
                return ''
            return '{"subtype":"success","is_error":false,"result":"hello STOP secret"}'

        with patch.object(ai, '_run_cli', side_effect=fake_cli), patch.object(ai, '_resolve_cli', return_value=sys.executable):
            for provider in ('codex', 'claude'):
                config['provider'] = provider
                config['providers'][provider].update(model='chosen-model', config_dir=str(folder), effort='low')
                with patch.dict(os.environ, {'OPENAI_API_KEY': 'SECRET', 'ANTHROPIC_API_KEY': 'SECRET', 'NODE_OPTIONS': 'SECRET'}):
                    assert ai.run_provider('hello', stop=['STOP'], config=config) == 'hello'
                command, env, timeout = cli_calls[-1]
                assert command[command.index('--model') + 1] == 'chosen-model'
                assert timeout == config['timeout_seconds']
                if provider == 'codex':
                    assert '--ignore-user-config' in command and 'forced_login_method="chatgpt"' in command
                    assert 'features.apps=false' in command and 'web_search="disabled"' in command
                    assert '"deny"' in ai._permission_profile(sys.executable)
                    assert env['CODEX_HOME'] == str(folder)
                else:
                    assert '--safe-mode' in command and '--restricted' in command and '--bare' not in command
                    assert command[command.index('--tools') + 1] == ''
                    assert command[command.index('--disallowedTools') + 1] == '*'
                    assert '--strict-mcp-config' in command and 'disableAllHooks' in ' '.join(command)
                    assert env['CLAUDE_CONFIG_DIR'] == str(folder)
        assert ai._run_cli([sys.executable, '-c', 'import sys; print(sys.stdin.read())'],
                           'hello λ', directory, dict(os.environ), 5).strip() == 'hello λ'
        fails(lambda: ai._run_cli([sys.executable, '-c', 'import time; time.sleep(10)'],
                                 '', directory, dict(os.environ), 0.1), 'timed out')
        fails(lambda: ai._run_cli([sys.executable, '-c', 'import sys; print("SECRET", file=sys.stderr); sys.exit(3)'],
                                 '', directory, dict(os.environ), 5), 'code 3')

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
                    dialog.provider.setCurrentIndex(dialog.provider.findData('codex'))
                    dialog.inputs['codex']['model'].setText('new-model')
                    dialog._save()
                    saved = save.call_args[0][0]
                    assert saved['provider'] == 'codex' and saved['providers']['codex']['model'] == 'new-model'
                    assert saved['providers']['openai'] == config['providers']['openai']
                    dialog.close()

    print('AI provider checks passed' + (' (including LangChain + Qt)' if '--runtime' in sys.argv else ''))


if __name__ == '__main__':
    main()
