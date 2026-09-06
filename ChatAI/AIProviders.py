"""Local text providers. Credentials never pass through AnkiBrain's webview."""
import copy
import json
import math
import os
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

USER_FILES = Path(__file__).resolve().parent.parent / 'user_files'
CONFIG_PATH = USER_FILES / 'ai_providers.json'
DEFAULT_CONFIG = {
    'provider': 'codex',
    'timeout_seconds': 600,
    'document_chunk_size': 6000,
    'providers': {
        'codex': {'model': '', 'cli_path': '', 'config_dir': '', 'effort': ''},
        'claude': {'model': 'sonnet', 'cli_path': '', 'config_dir': '', 'effort': ''},
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
TEXT_INSTRUCTIONS = (
    "Act only as AnkiBrain's text-generation backend. Answer the supplied prompt directly. "
    'Do not inspect files, run commands, browse the web, or use tools.'
)


def load_config(config_path=CONFIG_PATH):
    config = copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(config_path, encoding='utf-8') as stream:
            saved = json.load(stream)
    except FileNotFoundError:
        # Preserve settings from the initial Codex integration, without making the
        # server-mode model selector control other local providers.
        legacy = USER_FILES / 'settings.json'
        if legacy.is_file():
            with legacy.open(encoding='utf-8') as stream:
                config['providers']['codex']['model'] = json.load(stream).get('llmModel', '')
        environment = _environment()
        config['providers']['codex']['cli_path'] = environment.get('ANKIBRAIN_CODEX_CLI', '')
        try:
            config['timeout_seconds'] = int(environment.get('ANKIBRAIN_CODEX_TIMEOUT', '600'))
        except ValueError:
            raise ValueError('ANKIBRAIN_CODEX_TIMEOUT must be an integer.') from None
        validate_config(config)
        return config
    except (ValueError, OSError):
        raise ValueError('Cannot read ai_providers.json. Fix the JSON or restore your backup.') from None
    if not isinstance(saved, dict) or not isinstance(saved.get('providers', {}), dict):
        raise ValueError('AI configuration and providers must be JSON objects.')
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
        raise ValueError('Provider must be codex, claude, or openai.')
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
    for name, efforts in [('codex', ('', 'minimal', 'low', 'medium', 'high', 'xhigh')),
                          ('claude', ('', 'low', 'medium', 'high', 'xhigh', 'max'))]:
        if providers[name]['effort'] not in efforts:
            raise ValueError(f'Unsupported {name} effort level.')
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
    if config['provider'] == 'openai' and not api['model'].strip():
        raise ValueError('An OpenAI-compatible model ID is required.')


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


def _resolve_cli(name, configured):
    resolved = shutil.which(os.path.expanduser(configured or name))
    if resolved is None:
        raise RuntimeError(f'{name} CLI not found. Install it, sign in, then set its full CLI path in AI Provider Settings.')
    return resolved


def _cli_environment(cli, source):
    # Do not forward API keys, provider overrides, injected Node options, or tools' environment.
    allowed = ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'SYSTEMROOT', 'WINDIR',
               'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL', 'HTTP_PROXY', 'HTTPS_PROXY',
               'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
               'SSL_CERT_FILE', 'SSL_CERT_DIR', 'NODE_EXTRA_CA_CERTS')
    environment = {key: source[key] for key in allowed if source.get(key)}
    environment['PATH'] = os.pathsep.join((str(Path(cli).parent), os.defpath))
    return environment


def _run_cli(command, prompt, workdir, environment, timeout):
    try:
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, encoding='utf-8', cwd=workdir,
                              env=environment, start_new_session=os.name != 'nt',
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
            try:
                stdout, stderr = process.communicate(prompt, timeout=timeout)
            except BaseException as error:
                if process.poll() is None:
                    try:
                        if os.name == 'nt':
                            process.kill()
                        else:
                            os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.communicate()
                if isinstance(error, subprocess.TimeoutExpired):
                    raise RuntimeError(f'AI CLI timed out after {timeout} seconds.') from None
                raise
    except OSError:
        raise RuntimeError('Cannot launch AI CLI. Check the executable path and its runtime dependencies.') from None
    if process.returncode:
        # CLI diagnostics may echo prompts or credentials: never forward them into bridge logs.
        raise RuntimeError(f'AI CLI exited with code {process.returncode}. Check CLI version, login, model, and quota in your terminal.')
    return stdout


def _permission_profile(codex_cli):
    resolved = Path(codex_cli).resolve()
    codex_root = resolved.parents[1] if resolved.suffix == '.js' else resolved.parent
    return ('permissions.ankibrain={ filesystem = { ":root" = "deny", ":minimal" = "read", '
            f'{json.dumps(str(codex_root))} = "read", ":workspace_roots" = {{ "." = "read" }} }}, '
            'network = { enabled = false } }')


def run_codex(prompt, options, timeout, environment):
    cli = _resolve_cli('codex', options['cli_path'])
    env = _cli_environment(cli, environment)
    home = options['config_dir'] or environment.get('CODEX_HOME')
    if home:
        env['CODEX_HOME'] = os.path.abspath(os.path.expanduser(home))
    with tempfile.TemporaryDirectory(prefix='ankibrain-codex-') as workdir:
        output = Path(workdir) / 'response.txt'
        command = [cli, '-a', 'never', 'exec', '-', '--ephemeral', '--ignore-user-config',
                   '--ignore-rules', '--skip-git-repo-check', '--color', 'never',
                   '--output-last-message', str(output), '-C', workdir]
        overrides = ['forced_login_method="chatgpt"', 'default_permissions="ankibrain"',
                     _permission_profile(cli), 'web_search="disabled"', 'tools.view_image=false',
                     'history.persistence="none"', 'project_doc_max_bytes=0',
                     f'developer_instructions={json.dumps(TEXT_INSTRUCTIONS)}']
        for feature in ('shell_tool', 'unified_exec', 'multi_agent', 'apps', 'hooks', 'memories',
                        'plugins', 'remote_plugin', 'browser_use', 'computer_use', 'image_generation',
                        'view_image', 'skill_search', 'shell_snapshot', 'goals'):
            overrides.append(f'features.{feature}=false')
        if options['effort']:
            overrides.append('model_reasoning_effort=' + json.dumps(options['effort']))
        for override in overrides:
            command.extend(('-c', override))
        if options['model']:
            command.extend(('--model', options['model']))
        _run_cli(command, prompt, workdir, env, timeout)
        if not output.is_file():
            raise RuntimeError('Codex returned no final response.')
        return output.read_text(encoding='utf-8')


def run_claude(prompt, options, timeout, environment):
    cli = _resolve_cli('claude', options['cli_path'])
    env = _cli_environment(cli, environment)
    home = options['config_dir'] or environment.get('CLAUDE_CONFIG_DIR')
    if home:
        env['CLAUDE_CONFIG_DIR'] = os.path.abspath(os.path.expanduser(home))
    with tempfile.TemporaryDirectory(prefix='ankibrain-claude-') as workdir:
        command = [cli, '--print', '--output-format', 'json', '--restricted',
                   '--safe-mode', '--tools', '', '--disallowedTools', '*', '--permission-mode', 'dontAsk',
                   '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                   '--setting-sources', '', '--settings', '{"disableAllHooks":true,"forceLoginMethod":"claudeai"}',
                   '--disable-slash-commands', '--no-session-persistence', '--no-chrome',
                   '--max-turns', '1', '--append-system-prompt', TEXT_INSTRUCTIONS]
        if options['model']:
            command.extend(('--model', options['model']))
        if options['effort']:
            command.extend(('--effort', options['effort']))
        raw = _run_cli(command, prompt, workdir, env, timeout)
    try:
        result = json.loads(raw)
        if result.get('is_error') or result.get('subtype') != 'success':
            raise RuntimeError('Claude Code failed. Check subscription login, model access, and quota in your terminal.')
        return result['result']
    except (ValueError, TypeError, AttributeError, KeyError):
        raise RuntimeError('Claude Code returned an invalid response; update the CLI.') from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward user-supplied authentication headers to a redirect target.


def run_openai(prompt, options, timeout, environment):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
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
        hints = {401: 'Check credentials.', 403: 'Check credentials and model access.',
                 404: 'Check base URL and model ID.', 429: 'Quota or rate limit reached; try later.'}
        raise RuntimeError(f'OpenAI-compatible endpoint returned HTTP {error.code}. '
                           + hints.get(error.code, 'Check endpoint configuration and provider status.')) from None
    except (URLError, TimeoutError, OSError):
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
    run = {'codex': run_codex, 'claude': run_claude, 'openai': run_openai}[provider]
    response = run(prompt, config['providers'][provider], config['timeout_seconds'], _environment())
    if not isinstance(response, str) or not response.strip():
        raise RuntimeError('AI provider returned no text.')
    for sequence in stop or []:
        response = response.split(sequence, 1)[0]
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
