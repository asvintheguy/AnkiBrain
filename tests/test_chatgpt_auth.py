"""Offline native OAuth/HTTP checks; also run by test_ai_providers.py. No real accounts."""
import base64
import copy
import hashlib
import io
import json
import os
import stat
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.client import BadStatusLine
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import ProxyHandler, build_opener

from test_ai_providers import ai, fails
import ChatGPTAuth as auth


def check_auth():
    claims = {'https://api.openai.com/auth': {'chatgpt_account_id': 'test-account'}}
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b'=').decode()
    payload = {'id_token': 'header.' + encoded + '.signature', 'access_token': 'SECRET-access',
               'refresh_token': 'SECRET-refresh', 'expires_in': 3600}
    for invalid in ({}, [], {**payload, 'expires_in': float('nan')}, {**payload, 'access_token': 'SECRET\r\nx: y'},
                    {**payload, 'access_token': 'SECRET-é'}, {**payload, 'id_token': 'bad'}):
        fails(lambda: auth._session(invalid), 'valid ChatGPT session')
    expires = int(time.time()) + 3600
    jwt = base64.urlsafe_b64encode(json.dumps({**claims, 'exp': expires}).encode()).rstrip(b'=').decode()
    assert auth._session({'access_token': 'header.' + jwt + '.sig', 'refresh_token': 'SECRET'})['expires_at'] == expires
    assert auth._session({'access_token': 'SECRET', 'refresh_token': 'SECRET', 'account_id': 'test-account',
                          'expires_at': expires})['expires_at'] == expires
    fails(lambda: auth._folder({'auth_dir': 'relative/path'}), 'absolute')

    calls, grants = [], []
    status = [200]
    reply = [{'type': 'response.output_text.delta', 'delta': 'NOT THE FINAL ANSWER'},
             {'type': 'response.completed', 'response': {'status': 'completed', 'output': [
                 {'type': 'reasoning'}, {'type': 'message', 'role': 'assistant', 'phase': 'commentary',
                                         'content': [{'type': 'output_text', 'text': 'NOT FINAL'}]},
                 {'type': 'message', 'role': 'assistant', 'phase': 'final_answer',
                                         'content': [{'type': 'output_text', 'text': 'OK STOP later'}]}]}}]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            if self.path == '/oauth/token':
                is_json = self.headers['Content-Type'] == 'application/json'
                fields = {key: [value] for key, value in json.loads(raw).items()} if is_json else parse_qs(raw.decode())
                assert is_json == (fields['grant_type'] == ['refresh_token'])
                grants.append(fields)
                time.sleep(0.02)  # Expose refresh races.
                response = {**payload, 'access_token': 'SECRET-access-' + str(len(grants))}
                if fields['grant_type'] == ['refresh_token']:
                    response.pop('id_token')  # Refresh may omit both the ID token and refresh token.
                    response.pop('refresh_token')
                body = json.dumps(response).encode()
                self.send_response(200)
            else:
                calls.append((self.path, dict(self.headers), json.loads(raw)))
                self.send_response(status[0])
                if status[0] == 302:
                    self.send_header('Location', base + '/must-not-follow')
                if status[0] == 401:
                    status[0] = 200  # Exactly one refresh + replay of an unauthorized request.
                body = b''.join(b'event: update\r\ndata: ' + json.dumps(event).encode() + b'\r\n\r\n' for event in reply)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append((self.path, dict(self.headers), None))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'models': [{'slug': 'available-model'}, {'slug': 'hidden', 'visibility': 'hide'}]}).encode())

    server = HTTPServer(('127.0.0.1', 0), Handler)
    base = f'http://127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as directory, patch.object(auth, 'ISSUER', base), \
                patch.object(auth, 'RESPONSES_URL', base + '/responses'), patch.object(auth, 'MODELS_URL', base + '/models'), \
                patch.object(auth, 'CALLBACK_PORTS', (0,)), patch.dict(os.environ, {'NO_PROXY': '127.0.0.1,localhost'}):
            config = copy.deepcopy(ai.DEFAULT_CONFIG)
            options = config['providers']['chatgpt']
            options.update(auth_dir=directory, model='chosen-model', effort='low')
            session_file = Path(directory) / 'session.json'
            assert not auth.signed_in(options)
            fails(lambda: auth._get_session(options), 'not signed in')
            with ThreadPoolExecutor(max_workers=3) as pool:
                flow = auth.Login(options)
                params = parse_qs(urlsplit(flow.url).query)
                challenge = base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest()).rstrip(b'=').decode()
                assert params['code_challenge'] == [challenge] and params['code_challenge_method'] == ['S256']
                assert params['state'] == [flow.state] and 'api.connectors.invoke' not in params['scope'][0]
                assert {server.server_address[0] for server in flow.servers} <= {'127.0.0.1', '::1'}
                future = pool.submit(flow.finish)
                direct = build_opener(ProxyHandler({}))
                for query in ({'code': 'SECRET-code', 'state': 'wrong'},
                              {'code': 'SECRET-code', 'state': [flow.state, flow.state]},
                              {'code': 'SECRET-code', 'error': 'denied', 'state': flow.state}):
                    try:
                        direct.open(flow.redirect_uri + '?' + urlencode(query, doseq=True), timeout=3)
                    except HTTPError as error:
                        assert error.code == 400
                        error.close()
                    else:
                        raise AssertionError('Invalid callback accepted')
                    assert not flow.received.is_set() and not session_file.exists()
                with direct.open(flow.redirect_uri + '?' + urlencode({'code': 'SECRET-code', 'state': flow.state}), timeout=3) as response:
                    assert response.status == 200 and b'SECRET' not in response.read()
                future.result(timeout=5)
                assert all(server.fileno() == -1 for server in flow.servers)
                assert grants[-1]['code_verifier'] == [flow.verifier]
                assert grants[-1]['redirect_uri'] == [flow.redirect_uri]
                assert auth.signed_in(options) and auth._read(session_file)['account_id'] == 'test-account'
                if os.name != 'nt':
                    assert stat.S_IMODE(session_file.stat().st_mode) == 0o600

                data = auth._read(session_file)
                data['expires_at'] = time.time() - 1
                ai._atomic_json(data, session_file)
                before = len(grants)
                futures = [pool.submit(auth._get_session, options) for _ in range(2)]
                renewed = [future.result(timeout=5) for future in futures]
                assert len(grants) == before + 1 and renewed[0] == renewed[1]
                assert renewed[0]['refresh_token'] == 'SECRET-refresh'

                with patch('subprocess.Popen', side_effect=AssertionError('Native auth must not launch a CLI')):
                    assert ai.run_provider('hello λ', stop=['STOP'], config=config) == 'OK'
                path, headers, body = calls[-1]
                assert path == '/responses' and headers['Authorization'] == 'Bearer ' + renewed[0]['access_token']
                assert headers['Chatgpt-Account-Id'] == 'test-account'
                assert body['model'] == 'chosen-model' and body['input'][0]['content'][0]['text'] == 'hello λ'
                assert body['stream'] is True and body['store'] is False and body['tools'] == [] and body['tool_choice'] == 'none'
                assert body['reasoning'] == {'effort': 'low'}
                assert auth.models(options) == ['available-model']

                before = len(grants)
                status[0] = 401
                assert ai.run_provider('hello', config=config).startswith('OK')
                assert len(grants) == before + 1
                assert calls[-1][1]['Authorization'] != calls[-2][1]['Authorization']
                old_session = auth._read(session_file)
                status[0] = 401
                with patch.object(auth, '_get_session', side_effect=[old_session, {**old_session, 'account_id': 'another-account'}]):
                    fails(lambda: ai.run_provider('hello', config=config), 'account changed')
                for code in (403, 429, 500, 302):
                    status[0] = code
                    before = len(calls)
                    fails(lambda: ai.run_provider('hello', config=config), 'HTTP ' + str(code))
                    assert len(calls) == before + 1
                status[0] = 200
                complete = copy.deepcopy(reply)
                for bad in ([{'type': 'response.incomplete'}], [{'type': 'error', 'message': 'SECRET'}],
                            [{'type': 'response.output_text.delta', 'delta': 'partial'}],
                            [dict(type='response.completed', response={'status': 'completed', 'output': [{'type': 'function_call'}]})]):
                    reply[:] = bad
                    fails(lambda: ai.run_provider('hello', config=config))
                reply[:] = complete
                fails(lambda: list(auth._events(io.BytesIO(b'data: ' + b'x' * (1024 * 1024)))), 'size limit')
                with patch.object(auth, 'build_opener') as opener:
                    opener.return_value.open.side_effect = BadStatusLine('SECRET')
                    fails(lambda: ai.run_provider('hello', config=config), 'Cannot reach')
                    fails(lambda: auth._token_request({}), 'could not complete')

                previous = session_file.read_bytes()
                for cancelled in (True, False):
                    pending = auth.Login(options)
                    if cancelled:
                        pending.cancel()
                    else:
                        pending.deadline = 0
                    fails(pending.finish, 'cancelled' if cancelled else 'timed out')
                    assert all(server.fileno() == -1 for server in pending.servers)
                    assert session_file.read_bytes() == previous
                auth.logout(options)
                assert not auth.signed_in(options)
                fails(lambda: ai.run_provider('hello', config=config), 'not signed in')
                session_file.write_text('SECRET-not-json', encoding='utf-8')
                fails(lambda: auth._read(session_file), 'Cannot read')
                auth.logout(options)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    check_auth()
    print('Native ChatGPT checks passed (offline)')
