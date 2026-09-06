"""Experimental ChatGPT OAuth + Codex Responses compatibility, without a CLI.

Own token store only: never import ~/.codex or browser cookies. Protocol references:
https://github.com/HKUDS/DeepTutor/tree/main/deeptutor/services/codex_auth
"""
import base64
import hashlib
import errno
import json
import os
import secrets
import selectors
import socket
import threading
import time
from contextlib import contextmanager
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener

from AIProviders import USER_FILES, TEXT_INSTRUCTIONS, _atomic_json, _NoRedirect, validate_headers

ISSUER = 'https://auth.openai.com'
CLIENT_ID = 'app_EMoamEEZ73f0CkXaXp7hrann'  # Public Codex OAuth client; not a secret.
SCOPE = 'openid profile email offline_access'  # Text generation needs no connector access.
RESPONSES_URL = 'https://chatgpt.com/backend-api/codex/responses'
MODELS_URL = 'https://chatgpt.com/backend-api/codex/models?client_version=0.153.4'
CALLBACK_PORTS = (1455, 1457)


def _folder(options):
    if not options.get('auth_dir'):
        return USER_FILES / 'provider_auth' / 'chatgpt'
    folder = Path(options['auth_dir']).expanduser()
    if not folder.is_absolute():
        raise ValueError('Private sign-in directory must be absolute, or blank for the default.')
    return folder.resolve()


@contextmanager
def _locked(options):
    folder = _folder(options)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (folder / 'session.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            if lock.tell() == 0:
                lock.write(b'\0')
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield folder / 'session.json'
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _read(path):
    try:
        with path.open(encoding='utf-8') as stream:
            raw = stream.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError()
        data = json.loads(raw)
        for key in ('access_token', 'refresh_token', 'account_id'):
            if not isinstance(data[key], str) or not data[key] or not data[key].isascii():
                raise ValueError()
        validate_headers({'Authorization': data['access_token'], 'Account': data['account_id']})
        if type(data['expires_at']) not in (int, float) or not 0 < data['expires_at'] < 10**12:
            raise ValueError()
        return data
    except FileNotFoundError:
        raise RuntimeError('ChatGPT is not signed in. Use Sign in with ChatGPT, or AnkiBrain → Connect AI.') from None
    except (OSError, ValueError, TypeError, KeyError):
        raise RuntimeError('Cannot read the private ChatGPT session. Sign out locally and sign in again.') from None


def signed_in(options):
    return (_folder(options) / 'session.json').is_file()


def logout(options):
    # Local sign-out only. This does not log out Codex CLI or revoke other app sessions.
    with _locked(options) as path:
        path.unlink(missing_ok=True)


def _token_request(fields):
    refreshing = fields.get('grant_type') == 'refresh_token'
    data = json.dumps(fields) if refreshing else urlencode(fields)
    content_type = 'application/json' if refreshing else 'application/x-www-form-urlencoded'
    request = Request(ISSUER + '/oauth/token', data=data.encode(),
                      headers={'Content-Type': content_type, 'User-Agent': 'AnkiBrain/1.0'})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=30) as response:
            raw = response.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except HTTPError as error:
        error.close()
        raise RuntimeError(f'ChatGPT OAuth returned HTTP {error.code}. Sign in again; no API fallback was attempted.') from None
    except (URLError, OSError, HTTPException, ValueError, UnicodeError):
        raise RuntimeError('ChatGPT OAuth could not complete. Check your connection and try signing in again.') from None


def _session(payload, previous=None):
    previous = previous or {}
    try:
        account = payload.get('account_id') or payload.get('chatgpt_account_id') or ''
        expires_at = payload.get('expires_at')
        if payload.get('expires_in') is not None:
            seconds = payload['expires_in']
            if type(seconds) not in (int, float) or not 0 < seconds <= 365 * 86400:
                raise ValueError()
            expires_at = time.time() + seconds
        # Issuer-returned JWT claims are routing/expiry metadata, NOT local authorization.
        for key in ('access_token', 'id_token'):
            token = payload.get(key, '')
            if not isinstance(token, str):
                raise ValueError()
            if token.count('.') == 2:
                encoded = token.split('.')[1]
                claims = json.loads(base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True))
                account = account or (claims.get('https://api.openai.com/auth') or {}).get('chatgpt_account_id', '')
                if expires_at is None:
                    expires_at = claims.get('exp')
                if account and expires_at is not None:
                    break
        account = account or previous.get('account_id', '')
        if type(expires_at) not in (int, float) or not 0 < expires_at < 10**12:
            raise ValueError()
        data = {'access_token': payload['access_token'],
                'refresh_token': payload.get('refresh_token') or previous.get('refresh_token'),
                'account_id': account, 'expires_at': expires_at}
        for key in ('access_token', 'refresh_token', 'account_id'):
            if not isinstance(data[key], str) or not data[key] or not data[key].isascii():
                raise ValueError()
        validate_headers({'Authorization': data['access_token'], 'Account': data['account_id']})
        if previous and data['account_id'] != previous['account_id']:
            raise ValueError()
        return data
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RuntimeError('OAuth did not return a valid ChatGPT session/account. Sign in again.') from None


def _get_session(options, rejected_token=None):
    # A process-wide threading lock is insufficient: Anki and ChatAI are separate processes.
    with _locked(options) as path:
        data = _read(path)
        rejected = rejected_token is not None and secrets.compare_digest(data['access_token'], rejected_token)
        if data['expires_at'] > time.time() + 60 and not rejected:
            return data
        updated = _session(_token_request({'client_id': CLIENT_ID, 'grant_type': 'refresh_token',
                                          'refresh_token': data['refresh_token']}), data)
        _atomic_json(updated, path)
        return updated


class Login:
    """One cancellable, bounded browser login with PKCE and a loopback callback."""
    def __init__(self, options):
        _folder(options)  # Fail invalid directory input before opening the browser/listener.
        self.options = dict(options)
        self.state = secrets.token_urlsafe(32)
        self.verifier = secrets.token_urlsafe(64)
        self.cancelled = threading.Event()
        self.received = threading.Event()
        self.callback_lock = threading.Lock()
        self.code = None
        self.error = False
        self.deadline = time.monotonic() + 300
        flow = self

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(2)
                return connection, address

            def handle_error(self, request, client_address):
                pass  # Never log a callback URL containing an authorization code.

        class IPv6Server(Server):
            address_family = socket.AF_INET6

            def server_bind(self):
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                super().server_bind()

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                try:
                    url = urlsplit(self.path)
                    query = parse_qs(url.query, keep_blank_values=True, max_num_fields=20)
                except ValueError:
                    url, query = urlsplit('/invalid'), {}
                state = query.get('state', [])
                hosts = {f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}',
                         f'[::1]:{self.server.server_port}'}
                with flow.callback_lock:
                    valid = (url.path == '/auth/callback' and self.headers.get('Host') in hosts
                             and len(state) == 1 and len(state[0]) == len(flow.state)
                             and secrets.compare_digest(state[0].encode(), flow.state.encode())
                             and not flow.cancelled.is_set() and not flow.received.is_set()
                             and time.monotonic() < flow.deadline)
                    code, error = query.get('code', []), query.get('error', [])
                    valid = valid and ((len(code) == 1 and bool(code[0]) and not error)
                                       or (len(error) == 1 and not code))
                    if valid:
                        flow.code = code[0] if code else None
                        flow.error = bool(error)
                        flow.received.set()
                text = b'Return to AnkiBrain to finish sign-in.' if valid else b'Invalid or expired sign-in callback.'
                self.send_response(200 if valid else 400)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(len(text)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(text)

        self.servers = []
        for port in CALLBACK_PORTS:
            try:
                self.servers.append(Server(('127.0.0.1', port), Callback))
                port = self.servers[0].server_port
                try:
                    self.servers.append(IPv6Server(('::1', port), Callback))
                except OSError as error:
                    if error.errno not in (errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL, errno.EPROTONOSUPPORT):
                        raise  # An occupied IPv6 callback must not receive our authorization code.
                break
            except OSError:
                for server in self.servers:
                    server.server_close()
                self.servers.clear()
        if not self.servers:
            raise RuntimeError('Cannot bind ChatGPT login on localhost:1455 or :1457. Close another pending sign-in and retry.')
        self.selector = selectors.DefaultSelector()
        for server in self.servers:
            server.timeout = 0.2
            self.selector.register(server, selectors.EVENT_READ)
        self.redirect_uri = f'http://localhost:{port}/auth/callback'
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b'=').decode()
        self.url = ISSUER + '/oauth/authorize?' + urlencode({
            'response_type': 'code', 'client_id': CLIENT_ID, 'redirect_uri': self.redirect_uri,
            'scope': SCOPE, 'state': self.state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
            'originator': 'codex_cli_rs', 'id_token_add_organizations': 'true', 'codex_cli_simplified_flow': 'true',
        })

    def cancel(self):
        self.cancelled.set()

    def finish(self):
        try:
            while not self.received.is_set() and not self.cancelled.is_set() and time.monotonic() < self.deadline:
                for key, _ in self.selector.select(timeout=0.2):
                    key.fileobj.handle_request()
            if self.cancelled.is_set():
                raise RuntimeError('ChatGPT sign-in cancelled.')
            if not self.received.is_set():
                raise RuntimeError('ChatGPT sign-in timed out after five minutes.')
            if self.error:
                raise RuntimeError('ChatGPT sign-in was declined or failed.')
            data = _session(_token_request({'client_id': CLIENT_ID, 'grant_type': 'authorization_code',
                                           'code': self.code, 'redirect_uri': self.redirect_uri,
                                           'code_verifier': self.verifier}))
            with _locked(self.options) as path:
                if self.cancelled.is_set():
                    raise RuntimeError('ChatGPT sign-in cancelled.')
                _atomic_json(data, path)
        finally:
            self.selector.close()
            for server in self.servers:
                server.server_close()


def _open(options, url, timeout, body=None):
    session = _get_session(options)
    for attempt in range(2):
        headers = {'Authorization': 'Bearer ' + session['access_token'], 'chatgpt-account-id': session['account_id'],
                   'User-Agent': 'AnkiBrain/1.0', 'originator': 'AnkiBrain', 'OpenAI-Beta': 'responses=experimental',
                   'Content-Type': 'application/json', 'Accept': 'text/event-stream' if body else 'application/json'}
        request = Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            return build_opener(_NoRedirect()).open(request, timeout=timeout)
        except HTTPError as error:
            error.close()
            if error.code == 401 and attempt == 0:
                renewed = _get_session(options, rejected_token=session['access_token'])
                if renewed['account_id'] != session['account_id']:
                    raise RuntimeError('ChatGPT account changed during the request. Retry only if you intend to use the new account.')
                session = renewed
                continue
            hint = 'Usage quota/rate limit reached.' if error.code == 429 else 'Check sign-in, model access, and provider status.'
            raise RuntimeError(f'ChatGPT returned HTTP {error.code}. {hint}') from None
        except (URLError, OSError, HTTPException):
            raise RuntimeError('Cannot reach ChatGPT. Check TLS, proxy, connection, and timeout.') from None


def models(options):
    try:
        with _open(options, MODELS_URL, 30) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError()
        result = json.loads(raw)['models']
        if not isinstance(result, list):
            raise ValueError()
        names = sorted({item['slug'] for item in result if item.get('visibility', 'list') == 'list'})
        if not names or any(not isinstance(name, str) or not name or len(name) > 200 or any(ord(c) < 32 for c in name) for name in names):
            raise ValueError()
        return names
    except (ValueError, TypeError, KeyError, AttributeError, OSError, HTTPException):
        raise RuntimeError('ChatGPT returned an invalid model catalog. Enter a known model ID manually.') from None


def _events(response):
    data, total = [], 0
    while True:
        raw = response.readline(1024 * 1024 + 1)
        total += len(raw)
        if len(raw) > 1024 * 1024 or total > 16 * 1024 * 1024:
            raise RuntimeError('ChatGPT response exceeded the safety size limit. Reduce the prompt/document chunk size.')
        line = raw.decode('utf-8').rstrip('\r\n')
        if line.startswith('data:'):
            data.append(line[5:].lstrip(' '))
        if (not line or not raw) and data:
            text = '\n'.join(data)
            data = []
            if text != '[DONE]':
                yield json.loads(text)
        if not raw:
            break


def _message_text(item):
    if item['type'] == 'reasoning':
        return None
    if item['type'] != 'message' or item.get('role') != 'assistant':
        raise RuntimeError('ChatGPT requested unsupported output/tools; nothing was executed.')
    if item.get('phase') not in (None, 'commentary', 'final_answer'):
        raise RuntimeError('ChatGPT returned an unsupported message phase.')
    content = item.get('content', [])
    if not isinstance(content, list):
        raise ValueError()
    for part in content:
        if part['type'] != 'output_text' or not isinstance(part['text'], str):
            raise RuntimeError('ChatGPT declined or returned non-text output.')
    return None if item.get('phase') == 'commentary' else '\n'.join(part['text'] for part in content)


def run_chatgpt(prompt, options, timeout, environment):
    body = {'model': options['model'], 'instructions': TEXT_INSTRUCTIONS, 'store': False, 'stream': True,
            'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': prompt}]}], 'tools': [], 'tool_choice': 'none'}
    if options['effort']:
        body['reasoning'] = {'effort': options['effort']}
    try:
        items, parts = {}, {}
        # ponytail: urllib socket timeout, not a total streaming deadline; add one for slow-drip endpoints.
        with _open(options, RESPONSES_URL, timeout, body) as response:
            for event in _events(response):
                kind = event.get('type')
                if kind in ('error', 'response.failed', 'response.incomplete', 'response.cancelled'):
                    raise RuntimeError('ChatGPT failed or returned incomplete output. No partial cards were accepted.')
                if isinstance(kind, str) and kind.startswith('response.refusal.'):
                    raise RuntimeError('ChatGPT declined the request. No partial cards were accepted.')
                if kind in ('response.output_item.added', 'response.output_item.done',
                            'response.output_text.delta', 'response.output_text.done'):
                    index = event.get('output_index', 0)
                    if type(index) is not int or index < 0:
                        raise ValueError()
                    if kind.startswith('response.output_item.'):
                        _message_text(event['item'])  # Reject tools/refusals even without a final snapshot.
                        items[index] = event['item'] if kind.endswith('.done') else {**event['item'], 'content': []}
                    else:
                        content_index = event.get('content_index', 0)
                        value = event['delta' if kind.endswith('.delta') else 'text']
                        if type(content_index) is not int or content_index < 0 or not isinstance(value, str):
                            raise ValueError()
                        key = (index, content_index)
                        if kind.endswith('.done'):
                            parts[key] = [value]  # A snapshot replaces its deltas, never duplicates them.
                        else:
                            parts.setdefault(key, []).append(value)
                if kind == 'response.completed':
                    result = event['response']
                    if result.get('status') != 'completed':
                        raise RuntimeError('ChatGPT did not complete the response.')
                    output = result.get('output', [])
                    if not isinstance(output, list):
                        raise ValueError()
                    if output:
                        texts = [_message_text(item) for item in output]
                    else:
                        # Codex streams can omit output from the terminal event. Keep the earlier
                        # answer, but release it ONLY after an explicit successful completion.
                        texts = []
                        for index in sorted(set(items) | {key[0] for key in parts}):
                            text = _message_text(items[index]) if index in items else ''
                            if text is not None:
                                texts.append(text or '\n'.join(''.join(parts[key]) for key in sorted(parts) if key[0] == index))
                    answer = '\n'.join(text for text in texts if text is not None)
                    if not answer.strip():
                        raise RuntimeError('ChatGPT completed without an answer. Retry or select another account model; no cards were accepted.')
                    return answer
    except (ValueError, UnicodeError, KeyError, TypeError, AttributeError, OSError, HTTPException):
        raise RuntimeError('ChatGPT returned an invalid or interrupted stream. No partial output was accepted.') from None
    raise RuntimeError('ChatGPT stream ended without a completed response.')
