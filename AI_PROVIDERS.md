# Local AI provider setup

AnkiBrain Local mode supports:

| Option | Authentication | Billing / limits |
| --- | --- | --- |
| ChatGPT via **Codex CLI** | Sign in to the official CLI with your own ChatGPT account | Your Codex allowance; plan limits and any enabled extra usage apply |
| Claude via **Claude Code** | Sign in to the unmodified official CLI with your own Claude account | Your eligible Claude plan; account limits and any enabled extra usage apply |
| **OpenAI-compatible API** | API key, custom authentication headers, or no authentication for a local endpoint | Whatever that endpoint charges; a chat subscription is not an API key |
| **Gemini API free tier** | Google AI Studio API key, using the OpenAI-compatible option | Free only for eligible accounts, projects, models, and quotas |

These settings do **not** change AnkiBrain Regular/Server mode. Local mode means documents and embeddings are managed locally—not that the language model is offline. Prompts, conversation history, and retrieved document excerpts go to the provider you select.

## 1. Open the settings

1. Install this version of the add-on in Anki and complete AnkiBrain's existing **Local mode** dependency installation. The provider changes do not replace its Python, document-loader, Chroma, or local embedding dependencies.
2. Choose **AnkiBrain → AI Provider Settings…**, or **Settings → Advanced → AI Provider Settings…** in the side panel.
3. Select a provider and fill its fields. Each provider keeps its own settings when you switch.
4. **Test (uses quota)** sends a short real request using the unsaved fields. It does not save settings.
5. Click **Save**. New requests read the saved configuration; restarting the AI is not required. In-flight provider calls keep the settings they started with. Existing conversation history is retained and will be sent to the newly selected provider—clear the conversation first if you do not want that.

When using the source checkout, build the webview before loading the add-on:

```sh
cd webview
yarn install --frozen-lockfile
yarn build
```

`webview/build` is required by Anki and is ignored by Git. Include it when packaging/copying the add-on. Back up and preserve an existing installation's `user_files`; do not replace it with another person's credentials or documents.

## 2. ChatGPT subscription / Codex

Install a recent official Codex CLI (integration tested with **0.153.4**):

```sh
npm install -g @openai/codex
codex login
codex login status
```

Choose **Sign in with ChatGPT**, not API-key login. For a headless machine, the CLI also supports:

```sh
codex login --device-auth
```

In AnkiBrain:

- **Provider:** ChatGPT subscription — Codex CLI.
- **Model ID:** blank for the CLI default, or an exact Codex-compatible model available to your account. ChatGPT's UI model names are not necessarily valid Codex IDs.
- **CLI executable path:** blank if Anki can find `codex` on its PATH; otherwise paste its full executable path. On Linux/macOS, use `command -v codex` to find it. Desktop-launched Anki often has a different PATH than your terminal.
- **CLI configuration directory:** blank uses `CODEX_HOME` from the environment/`.env`, or the CLI's default `~/.codex`. Set a full directory path to use a different login. Log in with that same directory, for example `CODEX_HOME=/absolute/path codex login`.
- **Reasoning effort:** blank uses the CLI default. Available levels depend on the model.

AnkiBrain invokes the official CLI; it never copies OAuth tokens or implements a private ChatGPT API. Subscription mode forces ChatGPT authentication and does not fall back to an OpenAI API key. Requests use fresh ephemeral sessions, with conversation context supplied by AnkiBrain.

Codex runs in an empty temporary working directory, with user configuration/rules ignored, hosted search and integrations disabled, and a restrictive filesystem/network permission profile. A CLI too old to accept the required options fails rather than retrying without restrictions.

## 3. Claude subscription / Claude Code

Install the official Claude Code CLI using [Anthropic's installation instructions](https://code.claude.com/docs/en/setup). Use **2.1.263 or newer** for the options used here. Then:

```sh
claude auth login
claude
```

Choose your **Claude subscription account**, not Console/API billing. Check `/status` inside Claude Code to confirm the account and billing method, then exit it.

In AnkiBrain:

- **Provider:** Claude subscription — Claude Code.
- **Model ID:** an alias such as `sonnet`, `opus`, or a full model ID available on your plan. Blank uses the CLI default.
- **CLI executable path:** blank for PATH lookup or the full `claude` executable path.
- **CLI configuration directory:** blank uses `CLAUDE_CONFIG_DIR` or the CLI default. If set, sign in using the same directory, e.g. `CLAUDE_CONFIG_DIR=/absolute/path claude auth login`.
- **Reasoning effort:** optional, subject to model availability.

Run the login as the **same OS user** that runs Anki. CLI authentication, token refresh, and logout remain the CLI's responsibility. AnkiBrain neither stores nor forwards Claude subscription tokens. `CLAUDE_CODE_OAUTH_TOKEN`, API keys, cloud-provider overrides, and arbitrary injected CLI options are not forwarded by this adapter.

Requests use print mode, restricted mode, safe mode, no session persistence, no built-in tools, no MCP servers, disabled hooks/skills, and an empty working directory. **Do not add `--bare`: it disables subscription authentication.** No API-key fallback is attempted. Administrator-managed CLI policies still apply; these restrictions are not a VM/container boundary for the CLI program itself.

Anthropic distinguishes running the unmodified CLI with an end user's own login from collecting or proxying subscription credentials. This integration only does the former. Review the [current legal/authentication conditions](https://code.claude.com/docs/en/legal-and-compliance), especially before distributing a product or offering a hosted service.

**Validation:** CLI 2.1.263 accepts these flags and rejects an unauthenticated request. A paid-account end-to-end test has **not** been performed on this machine. Use the Test button after logging in; verify your account's actual usage/billing dashboard. CLI acceptance alone is not proof of subscription billing.

## 4. Generic OpenAI-compatible API

Choose the final provider option, **OpenAI-compatible API**.

| Setting | Meaning |
| --- | --- |
| Base URL | API prefix, e.g. `https://api.openai.com/v1`. AnkiBrain appends `/chat/completions` once. Do **not** include that suffix yourself. |
| Model ID | Required; exact model/deployment ID understood by that endpoint |
| API key | A literal key, `${ENV_VAR}`, or blank to omit Bearer authentication |
| Custom headers | JSON object of header names and string values; values can contain `${ENV_VAR}` |
| Temperature | Blank omits it; otherwise a number from 0 to 2. Leave blank for models that reject temperature. |
| Max output tokens | Blank omits it; otherwise sends `max_tokens` |
| Extra request body | Additional top-level JSON fields, e.g. `{"reasoning_effort":"low"}` |
| Allow HTTP outside localhost | Explicit opt-in for unencrypted LAN/remote endpoints; leave off for internet services |

Example headers:

```json
{
  "OpenAI-Organization": "org-example",
  "OpenAI-Project": "proj_example",
  "X-Custom-Token": "${MY_GATEWAY_TOKEN}"
}
```

Header names are case-insensitive. A supplied `Authorization` header replaces generated Bearer authentication and prevents API-key expansion. For a provider using `api-key` instead, clear the **API key** field and enter:

```json
{
  "api-key": "${MY_API_KEY}"
}
```

For models that require `max_completion_tokens`, leave **Max output tokens** blank and use:

```json
{
  "max_completion_tokens": 4096,
  "reasoning_effort": "low"
}
```

Extra body fields override optional temperature/token fields when both are supplied. They cannot override the model, messages, streaming, tools, number of completions, or stop sequences. This is a **text-only Chat Completions** adapter: it does not execute tool calls, support Responses-only endpoints, upload images, or emulate provider-specific APIs. Custom headers alone do not make a non-compatible endpoint compatible. Classic Azure endpoints requiring `api-version` query parameters need a compatible gateway; query strings in the base URL are not supported.

Examples:

| Service | Base URL | Authentication |
| --- | --- | --- |
| OpenAI API | `https://api.openai.com/v1` | Your separately billed OpenAI API key |
| Gemini API | `https://generativelanguage.googleapis.com/v1beta/openai` | Google AI Studio API key |
| OpenRouter | `https://openrouter.ai/api/v1` | OpenRouter API key; use its model IDs |
| Local OpenAI-compatible server | e.g. `http://127.0.0.1:1234/v1` | Blank if the local server requires no authentication |

Those endpoint examples are not claims of live testing or free access. For other services, use the endpoint and exact model ID from that service's documentation.

There is no automatic retry, redirect following, provider fallback, or API-key fallback. Redirects are rejected so credentials/custom headers cannot be forwarded to another host. HTTP 401/403 errors indicate authentication/access problems, 404 commonly indicates a bad base URL/model, and 429 indicates quota/rate limits. Empty, malformed, tool-call, filtered, or truncated responses fail rather than silently creating partial cards. API response bodies and CLI stderr are not copied into errors because they may echo private data.

## 5. Can a free Google account provide free Gemini here?

**Potentially yes, through the Gemini API free tier—not by substituting a Google login token for an API key.**

1. Sign in to [Google AI Studio](https://aistudio.google.com/apikey) with an eligible Google account.
2. Create/select a project and obtain its Gemini API key. A paid Google AI subscription is not required merely to qualify for available free API usage.
3. Check the project's actual free-tier access, model availability, [pricing](https://ai.google.dev/gemini-api/docs/pricing), and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Avoid enabling paid billing if your requirement is zero paid API usage. AnkiBrain cannot tell whether a key belongs to a billed project or enforce your cloud spending limit.
4. In AnkiBrain's API settings, use **Use Gemini API preset…**. It fills Google's OpenAI-compatible base URL and `${GEMINI_API_KEY}`, clears unrelated API options, and leaves the model for you to choose.
5. Paste the key into **API key**, or put it in `user_files/.env`:

   ```dotenv
   GEMINI_API_KEY='your-ai-studio-key'
   ```

6. Enter a text model currently eligible for your project's free quota. For example, Google's compatibility guide currently demonstrates `gemini-3.8-flash`; verify availability and pricing before choosing it. Model IDs and free quotas change.
7. Test, save, and check AI Studio's usage dashboard.

Google also advertises a personal-account free allowance for its **own Gemini CLI** (60 requests/minute and 1,000/day in the referenced documentation). **Those are not promises about Gemini API quotas.** Google explicitly restricts harvesting/piggybacking Gemini CLI OAuth for third-party backend access and recommends AI Studio/Vertex API keys for integrations. AnkiBrain therefore has **no Gemini CLI OAuth/subscription adapter**, and upgrading to Google AI Pro/Ultra does not turn its subscription credentials into an API key.

Free-tier privacy and eligibility matter: unpaid API prompts/responses may be used to improve Google's products and may be reviewed. Do not send sensitive study notes, patient information, or confidential documents without checking the applicable terms. Supported regions, age/account eligibility, and regional API-client restrictions also apply; see the [Gemini API terms](https://ai.google.dev/gemini-api/terms). Free usage is neither unlimited nor guaranteed for every account/model.

## 6. Configuration files and precedence

The dialog writes **`user_files/ai_providers.json`**, separately from ordinary UI settings. It is ignored by Git and never sent to the webview. Saves use atomic replacement with owner-only file permissions on POSIX. Keys/headers are still **plaintext**; on Windows protect the file with your user-account ACLs. Keep backups private.

A complete example (replace the API model before selecting `openai`):

```json
{
  "provider": "codex",
  "timeout_seconds": 600,
  "document_chunk_size": 6000,
  "providers": {
    "codex": {
      "model": "",
      "cli_path": "",
      "config_dir": "",
      "effort": ""
    },
    "claude": {
      "model": "sonnet",
      "cli_path": "",
      "config_dir": "",
      "effort": ""
    },
    "openai": {
      "model": "MODEL_ID_FROM_YOUR_PROVIDER",
      "base_url": "https://api.openai.com/v1",
      "api_key": "${OPENAI_API_KEY}",
      "headers": {},
      "temperature": null,
      "max_tokens": null,
      "extra_body": {},
      "allow_insecure_http": false
    }
  }
}
```

- The selected provider is the **only** provider used. Missing optional file fields receive defaults; unknown fields, invalid values, and malformed JSON fail clearly instead of silently selecting a different provider.
- Saved provider settings take precedence over the old local `llmModel`/`temperature` webview settings, which now apply only to Server mode. Before the first provider-config save, the old `llmModel` seeds Codex's model; `ANKIBRAIN_CODEX_CLI` and `ANKIBRAIN_CODEX_TIMEOUT` are migration defaults only.
- Provider **configuration directory** overrides `CODEX_HOME` / `CLAUDE_CONFIG_DIR`. Blank **CLI executable path** means PATH lookup. Use absolute executable/directory paths, not a shell command with arguments. For npm installs the Node runtime must be reachable too; on Windows prefer native executables.
- `${NAME}` expansion is supported in API keys and header **values**, not arbitrary JSON fields. Values in `user_files/.env` override the process environment. Missing/empty referenced variables fail before making a request. Each request re-reads `.env` and provider configuration, so changes apply without restart. Literal secrets are also supported.
- Subscription CLIs get a small environment allowlist for home/runtime paths, proxies, and certificate configuration—not your unrelated credentials or injected `NODE_OPTIONS`. Their official cached login is reused. API keys in the Anki environment are not forwarded to subscription CLI invocations.
- API networking uses Python's standard TLS verification and process proxy/certificate configuration; it never disables TLS verification. CLI networking inherits allowed proxy/certificate environment values. The permission profile's disabled network applies to agent tools, **not** the CLI's necessary inference/authentication connection.
- Timeout is 1–3,600 seconds: a wall-clock limit for CLI requests and a socket-operation timeout for API requests. The CLI may perform its own internal retries within that limit; AnkiBrain does not implement retries.
- Document-to-cards chunk size is 100–100,000 **characters**, not tokens. Lower it if a model truncates card JSON or exceeds its context window. This controls Make Cards document splitting, not retrieval embedding chunking.
- Editing the file manually changes backend behavior on the next request. The webview's displayed provider/model updates on a dialog save or Anki restart.
- Local cost is shown as **Provider-billed**, not `$0`: subscription quota, extra credits, and arbitrary API pricing cannot be reliably calculated here. Consult the provider's dashboard.

## 7. Checks and troubleshooting

Offline regression checks, without any paid/live calls:

```sh
python3 tests/test_ai_providers.py
```

With the local LangChain and PyQt6 dependencies installed:

```sh
user_files/venv/bin/python tests/test_ai_providers.py --runtime
```

Windows uses `user_files\venv\Scripts\python.exe`. These checks cover config validation/persistence, secret resolution, custom headers, local HTTP transport, no redirects/retries, CLI arguments and error handling, IPC serialization, and (with `--runtime`) real Qt widgets and LangChain conversation calls against a local test server.

A real provider smoke test (**uses the selected account's quota/billing**):

```sh
user_files/venv/bin/python ChatAI/AIProviders.py
```

Use `--config /path/to/ai_providers.json` to test a different configuration without changing Anki's saved file. This option affects that test invocation only.

If it fails:

- **CLI not found / cannot launch:** use the full executable path, confirm it runs as the same OS user, and check Node/native-runtime dependencies. Anki does not source your interactive shell profile.
- **CLI exited:** check version, log in through the official CLI again, check model/effort access, and inspect your quota. Old CLI versions are not retried with weaker security settings. No subscription connector silently switches to billed API usage.
- **Configuration cannot be read:** correct `user_files/ai_providers.json` or restore a backup. Invalid files are not automatically overwritten.
- **Endpoint returned HTML / wrong format:** the base URL must be an OpenAI-compatible API prefix, not a website, ChatGPT page, or `/responses` endpoint.
- **Module missing / local engine won't start:** complete the existing Local mode dependency installation. Subscription authentication does not remove those dependencies. Document retrieval still uses local Hugging Face embeddings and may download their model on first use.

Tested on Linux: Codex 0.153.4 with an actual ChatGPT login; generic API against a local HTTP server; Python 3.9.25 with LangChain 0.0.231 and PyQt6 6.5.1; webview production build. Claude's flags/authentication-failure path were checked with 2.1.263, but no Claude/Gemini account-backed request or full running-Anki session was available. Other OS/CLI versions should be verified with Test before regular use.

## Sources (reviewed 6 September 2026)

- [OpenAI: Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-codex-agent-faq)
- [Codex authentication](https://developers.openai.com/codex/auth)
- [Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [Claude Code authentication](https://code.claude.com/docs/en/authentication)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- [Google: OpenAI-compatible Gemini API](https://ai.google.dev/gemini-api/docs/openai)
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [API keys](https://ai.google.dev/gemini-api/docs/api-key), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [terms](https://ai.google.dev/gemini-api/terms)
- [Gemini CLI authentication](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/authentication.mdx) and [FAQ / third-party OAuth restriction](https://github.com/google-gemini/gemini-cli/blob/main/docs/resources/faq.md)
