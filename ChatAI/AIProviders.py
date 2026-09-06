"""Local text providers. Credentials never pass through AnkiBrain's webview."""
import copy
import json
import math
import os
import re
import tempfile
from pathlib import Path
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

USER_FILES = Path(__file__).resolve().parent.parent / 'user_files'
CONFIG_PATH = USER_FILES / 'ai_providers.json'
DEFAULT_CONFIG = {
    'provider': 'chatgpt',
    'timeout_seconds': 600,
    'document_chunk_size': 6000,
    'providers': {
        'chatgpt': {'model': 'gpt-5.6-luna', 'auth_dir': '', 'effort': ''},
        'openai': {
            'model': '',
            'base_url': 'https://api.openai.com/v1',
            'api_key': '${OPENAI_API_KEY}',
            'headers': {},
            'temperature': None,
            'max_tokens': None,
            'extra_body': {},
            'allow_insecure_http': False,
        },
    },
}
# Presets select endpoints, not billing entitlements. No client impersonation headers.
API_PRESETS = {
    'Gemini API — eligible free tier / API billing': ('https://generativelanguage.googleapis.com/v1beta/openai', 'GEMINI_API_KEY', ''),
    'Grok / xAI API — separate API billing': ('https://api.x.ai/v1', 'XAI_API_KEY', ''),
    'OpenAI API — separate API billing': ('https://api.openai.com/v1', 'OPENAI_API_KEY', ''),
    'OpenRouter — endpoint billing': ('https://openrouter.ai/api/v1', 'OPENROUTER_API_KEY', ''),
    'DeepSeek API — endpoint billing': ('https://api.deepseek.com/v1', 'DEEPSEEK_API_KEY', 'deepseek-chat'),
    'Kimi Open Platform — API billing, not Kimi membership': ('https://api.moonshot.ai/v1', 'MOONSHOT_API_KEY', ''),
}
TEXT_INSTRUCTIONS = (
    "Act only as AnkiBrain's text-generation backend. Answer the supplied prompt directly. "
    'Do not inspect files, run commands, browse the web, or use tools.'
)


def load_config(config_path=CONFIG_PATH, *, allow_legacy=False):
    config = copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(config_path, encoding='utf-8') as stream:
            saved = json.load(stream)
    except FileNotFoundError:
        validate_config(config)
        return config
    except (ValueError, OSError):
        raise ValueError('Cannot read ai_providers.json. Fix the JSON or restore your backup.') from None
    if not isinstance(saved, dict) or not isinstance(saved.get('providers', {}), dict):
        raise ValueError('AI configuration and providers must be JSON objects.')
    if saved.get('provider') in ('codex', 'claude'):
        if not allow_legacy:
            raise ValueError('CLI providers were removed. Open AnkiBrain → Connect AI, choose a provider, sign in, and Save.')
        if saved['provider'] == 'codex' and 'chatgpt' not in saved.get('providers', {}):
            old = saved.get('providers', {}).get('codex', {})
            if not isinstance(old, dict):
                raise ValueError('Malformed old provider settings.')
            config['providers']['chatgpt'].update({key: old[key] for key in ('model', 'effort') if old.get(key)})
        saved['provider'] = 'chatgpt'  # Settings-dialog migration only; requests fail until explicitly saved.
    for removed in ('codex', 'claude'):
        saved.get('providers', {}).pop(removed, None)
    if set(saved) - set(config) or set(saved.get('providers', {})) - set(config['providers']):
        raise ValueError('Unknown AI configuration field or provider.')
    config.update({key: value for key, value in saved.items() if key != 'providers'})
    for name, options in saved.get('providers', {}).items():
        if not isinstance(options, dict) or set(options) - set(config['providers'][name]):
            raise ValueError('Unknown or malformed provider settings.')
        config['providers'][name].update(options)
    validate_config(config)
    return config


def validate_config(config):
    if not isinstance(config, dict) or set(config) != set(DEFAULT_CONFIG):
        raise ValueError('Invalid AI configuration fields.')
    if not isinstance(config['provider'], str) or config['provider'] not in DEFAULT_CONFIG['providers']:
        raise ValueError('Provider must be chatgpt or openai.')
    for key, low, high in [('timeout_seconds', 1, 3600), ('document_chunk_size', 100, 100000)]:
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError(f'{key} must be an integer between {low} and {high}.')
    providers = config['providers']
    if not isinstance(providers, dict) or set(providers) != set(DEFAULT_CONFIG['providers']):
        raise ValueError('Invalid provider settings.')
    for name, defaults in DEFAULT_CONFIG['providers'].items():
        options = providers[name]
        if not isinstance(options, dict) or set(options) != set(defaults):
            raise ValueError(f'Invalid {name} settings.')
        for key, default in defaults.items():
            if isinstance(default, str) and (
                not isinstance(options[key], str) or any(ord(c) < 32 for c in options[key])
            ):
                raise ValueError(f'{name}.{key} must be text without control characters.')
    if providers['chatgpt']['effort'] not in ('', 'minimal', 'low', 'medium', 'high', 'xhigh'):
        raise ValueError('Unsupported ChatGPT effort level.')
    auth_dir = providers['chatgpt']['auth_dir']
    if auth_dir and not Path(auth_dir).expanduser().is_absolute():
        raise ValueError('Private sign-in directory must be absolute, or blank for the default.')
    api = providers['openai']
    if type(api['allow_insecure_http']) is not bool:
        raise ValueError('allow_insecure_http must be true or false.')
    validate_base_url(api['base_url'], api['allow_insecure_http'])
    validate_headers(api['headers'])
    temperature = api['temperature']
    if temperature is not None and (type(temperature) not in (int, float)
                                   or not math.isfinite(temperature) or not 0 <= temperature <= 2):
        raise ValueError('Temperature must be null (provider default) or between 0 and 2.')
    if api['max_tokens'] is not None and (type(api['max_tokens']) is not int or api['max_tokens'] < 1):
        raise ValueError('max_tokens must be null or a positive integer.')
    extra = api['extra_body']
    if not isinstance(extra, dict):
        raise ValueError('Extra request body must be a JSON object.')
    if set(extra) & {'model', 'messages', 'stream', 'tools', 'tool_choice', 'functions', 'function_call', 'n', 'stop'}:
        raise ValueError('Extra body cannot override routing, messages, streaming, tools, n, or stop.')
    try:
        json.dumps(config, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError('Configuration must contain valid JSON values.') from None
    if config['provider'] in ('openai', 'chatgpt') and not providers[config['provider']]['model'].strip():
        raise ValueError('A model ID is required for this provider.')


def validate_base_url(base_url, allow_http=False):
    try:
        url = urlsplit(base_url)
        _ = url.port  # Validate a supplied port even though urllib performs the request.
        valid = (url.scheme in ('https', 'http') and url.hostname and url.username is None
                 and url.password is None and not url.query and not url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Base URL must be HTTP(S), without credentials, query parameters, or fragments.')
    if url.scheme == 'http' and url.hostname not in ('localhost', '127.0.0.1', '::1') and not allow_http:
        raise ValueError('Use HTTPS, or explicitly allow insecure HTTP for this endpoint.')


def validate_headers(headers):
    if not isinstance(headers, dict):
        raise ValueError('Headers must be a JSON object of string values.')
    names = set()
    for name, value in headers.items():
        if not isinstance(name, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
            raise ValueError('Invalid HTTP header name.')
        if name.lower() in names or name.lower() in {'host', 'content-length', 'transfer-encoding', 'connection'}:
            raise ValueError('Duplicate or transport-controlled HTTP header.')
        names.add(name.lower())
        if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 or ord(c) > 255 for c in value):
            raise ValueError('HTTP header values must be text without control characters.')


def save_config(config, config_path=CONFIG_PATH):
    validate_config(config)
    _atomic_json(config, config_path)


def _atomic_json(config, config_path):
    target = Path(config_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement prevents the worker from reading a half-written secret file.
    fd, temporary = tempfile.mkstemp(prefix='.ai-providers-', dir=str(target.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(config, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)  # mkstemp creates mode 0600 on POSIX.
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _environment():
    from dotenv import dotenv_values
    environment = dict(os.environ)
    environment.update({key: value for key, value in dotenv_values(USER_FILES / '.env').items()
                        if value is not None})
    return environment


def _expand_secret(value, environment):
    def replace(match):
        name = match.group(1)
        if not environment.get(name):
            raise ValueError(f'Missing environment variable {name}; set it in user_files/.env.')
        return environment[name]
    return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', replace, value)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward user-supplied authentication headers to a redirect target.


def run_openai(prompt, options, timeout, environment):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'AnkiBrain/1.0'}
    custom = {key: _expand_secret(value, environment) for key, value in options['headers'].items()}
    validate_headers(custom)
    if options['api_key'] and not any(key.lower() == 'authorization' for key in custom):
        headers['Authorization'] = 'Bearer ' + _expand_secret(options['api_key'], environment)
    # Case-insensitive overrides, including Authorization and Azure-style api-key.
    headers = {key: value for key, value in headers.items() if key.lower() not in {k.lower() for k in custom}}
    headers.update(custom)
    validate_headers(headers)
    body = {'model': options['model'], 'messages': [{'role': 'user', 'content': prompt}], 'stream': False}
    for key in ('temperature', 'max_tokens'):
        if options[key] is not None:
            body[key] = options[key]
    body.update(options['extra_body'])
    request = Request(options['base_url'].rstrip('/') + '/chat/completions',
                      data=json.dumps(body, allow_nan=False).encode('utf-8'), headers=headers, method='POST')
    try:
        # ponytail: socket timeout, not a total deadline; use a deadline-aware transport for slow-drip endpoints.
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as error:
        error.close()
        hints = {401: 'Check credentials.', 403: 'Check credentials and model access.',
                 404: 'Check base URL and model ID.', 429: 'Quota or rate limit reached; try later.'}
        raise RuntimeError(f'OpenAI-compatible endpoint returned HTTP {error.code}. '
                           + hints.get(error.code, 'Check endpoint configuration and provider status.')) from None
    except (URLError, TimeoutError, OSError, HTTPException):
        raise RuntimeError('Cannot reach OpenAI-compatible endpoint. Check URL, TLS certificates, connection, and timeout.') from None
    except (ValueError, UnicodeError):
        raise RuntimeError('OpenAI-compatible endpoint returned invalid JSON.') from None
    try:
        choice = result['choices'][0]
        if choice.get('finish_reason') not in (None, 'stop'):
            raise RuntimeError('AI response was truncated, filtered, or requested tools. Adjust output limits or prompt; no partial output was accepted.')
        if choice['message'].get('tool_calls') or choice['message'].get('function_call'):
            raise RuntimeError('AI requested tools, which AnkiBrain does not execute.')
        return choice['message']['content']
    except (KeyError, IndexError, TypeError, AttributeError):
        raise RuntimeError('Endpoint did not return a Chat Completions text response.') from None


def run_provider(prompt, stop=None, config=None):
    config = load_config() if config is None else config
    validate_config(config)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('AI prompt must be nonempty text.')
    if stop is not None and (not isinstance(stop, list) or any(not isinstance(s, str) or not s for s in stop)):
        raise ValueError('Stop sequences must be nonempty strings.')
    provider = config['provider']
    if provider == 'chatgpt':
        from ChatGPTAuth import run_chatgpt
        run = run_chatgpt
    else:
        run = run_openai
    response = run(prompt, config['providers'][provider], config['timeout_seconds'], _environment())
    if not isinstance(response, str) or not response.strip():
        raise RuntimeError('AI provider returned no text.')
    for sequence in stop or []:
        response = response.split(sequence, 1)[0]
    if not response.strip():
        raise RuntimeError('AI response was empty after applying stop sequences. Retry or choose another model.')
    return response.strip()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Test the configured provider (uses its quota/billing).')
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    if args.config is not None and not args.config.is_file():
        parser.error('The supplied configuration file does not exist.')
    try:
        answer = run_provider('Reply with exactly OK.', config=load_config(args.config or CONFIG_PATH))
        print(answer)
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f'{error}\n')
