# Local AI providers — native authentication, no provider CLIs

| Option in this build | Authentication | Usage / billing |
| --- | --- | --- |
| **ChatGPT (experimental)** | Built-in browser OAuth with your own account | ChatGPT-backed Codex service; your account's entitlements, limits, credits, and extra-usage settings apply |
| **OpenAI-compatible API** (final option) | API key, custom headers, or no authentication for a local server | The selected endpoint's billing |
| **Gemini API preset** | Google AI Studio API key | Eligible free API quota, or paid API billing if enabled |
| **Grok / xAI API preset** | xAI API key | Separate API billing, **not SuperGrok/X Premium subscription login** |
| Other API presets | OpenAI, OpenRouter, DeepSeek, Kimi Open Platform keys | Each service's API billing, not its chat subscription |

**No Codex, Claude Code, Gemini, Grok, or Copilot CLI is installed, invoked, or required by these providers.** The older Codex/Claude CLI adapters have been removed. The existing external Python document engine is still required; it is not an AI-provider CLI.

These settings affect **Local mode only**, not Regular/Server mode. Local means document handling and embeddings run on your computer, not that the language model is offline. Prompts, conversation history, and retrieved document excerpts go to your chosen service. Switching providers retains that history: clear the conversation before switching if you do not want to share it with the next provider.

## 1. Open settings

Complete the add-on's [installation and Local-mode dependency setup](README.md), then open **AnkiBrain → AI Provider Settings…**, also available under **Settings → Advanced** in the side panel.

- Settings apply to the next request after **Save**. In-flight requests retain their original configuration.
- **Test (uses quota)** sends a real short prompt using unsaved settings. It does not save them.
- Browser sign-in and local sign-out take effect immediately, independently of the settings Save/Cancel buttons.
- If upgrading from a CLI provider, requests stop with a migration message until you explicitly choose a provider and Save. The settings dialog carries over the old Codex model/effort where possible, preserves API settings, and removes CLI fields. It never reads or copies another application's login cache. An old Claude selection does not silently send requests to ChatGPT.

## 2. Native ChatGPT sign-in

1. Select **ChatGPT — native browser sign-in (experimental)**.
2. Leave **Private sign-in directory** blank for the default, or enter an absolute directory dedicated to this account.
3. Click **Sign in with ChatGPT…**. Your normal browser opens OpenAI's authentication site. Check that it is `https://auth.openai.com`; enter credentials there, never into AnkiBrain, a terminal, or this repository.
4. Complete sign-in and return to Anki. The callback listens only on localhost, using port 1455 or 1457. Keep the browser and Anki on the same machine. This build does not provide a remote/headless/device-code login flow.
5. Click **Load account models**, then select an available model. The editable list preserves your existing choice rather than silently switching price tiers. The default `gpt-5.6-luna` is only a starting value, not a promise of access; choose from your account's catalog or enter a known exact ID.
6. Optionally select **Reasoning effort**, subject to your model's supported levels. Blank uses the service default.
7. Click **Test (uses quota)** and **Save**. No OpenAI API key is needed.

Closing the dialog cancels a pending login. Sign-in expires after five minutes; close other pending login windows if both callback ports are occupied. **Sign out locally…** deletes this add-on's cached credentials. It does not revoke other OpenAI sessions or cancel already-running requests. Manage account-wide sessions through OpenAI separately.

### What this connection actually uses

This is a **DeepTutor-style experimental compatibility path**, implemented directly in Python:

- Browser OAuth with PKCE and state validation against `auth.openai.com`.
- Direct text requests to `https://chatgpt.com/backend-api/codex/responses` with the user's OAuth token.
- Models from that account's Codex catalog; no ordinary ChatGPT conversation API or browser-cookie scraping.
- No provider subprocess, tools, shell commands, MCP, agent plugins, or automatic API-key fallback.

Removing the CLI does **not** change which service supplies the response. OpenAI's pricing documentation says **ChatGPT Work and Codex share pricing, credits, and usage limits**; that does not imply every ordinary ChatGPT website allowance applies here. Check your actual account's usage dashboard. Enabled extra usage/credits may cost money.

This is not a documented general-purpose OpenAI API contract or an OpenAI-endorsed integration. It uses the public Codex OAuth client and compatibility endpoints, which can change or reject third-party traffic. Review current provider terms before distributing or relying on it. A protocol change should fail visibly, not fall back to API billing.

### Private credential storage

Default: **`user_files/provider_auth/chatgpt/session.json`**, with a sibling refresh lock file. A custom sign-in directory keeps the same filenames and must be absolute. Use different directories for separate accounts.

Tokens are plaintext on disk, stored outside the webview and excluded from Git and release packages at the default location. The default account directory is owner-only when created on POSIX, and credential writes are atomic with mode `0600`. On Windows protect the directory with your user-account ACLs. Use disk encryption and keep backups private. A custom directory must also stay outside publicly shared/source directories; it is your responsibility to exclude that location from backups/publication.

The adapter never reads or modifies `~/.codex`, `~/.claude`, `~/.grok`, browser cookies, or their logout state. Normal token renewal is serialized across Anki and the Python worker so they do not race refresh-token rotation. A 401 response can trigger one refresh and one replay; quota errors and other errors are not retried automatically. Authentication errors do not expose token responses in logs.

## 3. Other subscriptions: what is and isn't available

Removing the CLIs does not make every service's subscription OAuth available to third-party applications:

| Service | Direct subscription sign-in in this build? | Reason / alternative |
| --- | --- | --- |
| Claude | **No** | Anthropic explicitly prohibits third-party apps offering Claude.ai login or collecting/intermediating subscription tokens. Its unmodified-binary exception is irrelevant here because CLI adapters were removed. Use a properly authorized OpenAI-compatible gateway with separately billed API credentials if desired; the native Anthropic Messages API is not implemented. |
| Gemini / Google AI Pro or Ultra | **No** | Google prohibits third-party harvesting/piggybacking Gemini CLI OAuth. Use an AI Studio key and eligible API free quota instead. |
| Grok / SuperGrok / X Premium | **Not implemented** | Grok Build has subscription OAuth and partner integrations, but an arbitrary third-party native OAuth integration has not been established or validated here. The xAI API preset is separately billed. |
| GitHub Copilot | **Not implemented** | GitHub documents OAuth-app authentication for its SDK, but that is not an implemented native HTTP adapter here. No SDK/CLI sidecar is installed. |
| Kimi Code | **No OAuth adapter** | Official-client OAuth and third-party Coding Plan keys are different paths. Kimi documents subscription-backed keys for permitted agent/development uses, but directs product integrations to Kimi Open Platform. This tutor presets the latter, not a claimed entitlement to coding quota. |
| Qwen Code | **No** | Its documentation says Qwen OAuth was discontinued; use the applicable API/Coding Plan setup instead. No stale OAuth flow is included. |

API key authentication is implemented natively in this add-on too—it just does not consume a chat subscription. Do not paste CLI refresh tokens, cookies, or website session tokens into the API-key field. Do not impersonate an approved client with custom headers to bypass access controls.

## 4. OpenAI-compatible API configuration

Select the final provider, **OpenAI-compatible API**. The preset dropdown fills an endpoint and environment-variable name, then clears previous headers/options after confirmation. Presets do not verify free quota or grant model access. Choose an exact model from your provider.

| Field | Meaning |
| --- | --- |
| Base URL | API prefix; AnkiBrain appends `/chat/completions`. Do not include that suffix. |
| Model ID | Required exact model/deployment ID |
| API key | Literal key, `${ENV_VAR}`, or blank to omit Bearer authentication |
| Custom headers | JSON object of string values, optionally using `${ENV_VAR}` |
| Temperature | Blank omits it; otherwise 0–2. Leave blank if the model rejects temperature. |
| Max output tokens | Blank omits it; otherwise sends `max_tokens` |
| Extra request body | Optional provider-specific fields, e.g. `{"max_completion_tokens":4096,"reasoning_effort":"low"}` |
| Allow HTTP outside localhost | Explicit opt-in for unencrypted remote/LAN endpoints; leave off for internet services |

Examples:

| Service | Base URL | Credential |
| --- | --- | --- |
| OpenAI API | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| Gemini API | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` |
| Grok / xAI API | `https://api.x.ai/v1` | `XAI_API_KEY` |
| OpenRouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| DeepSeek | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| Kimi Open Platform (international) | `https://api.moonshot.ai/v1` | `MOONSHOT_API_KEY` |
| Local compatible server | e.g. `http://127.0.0.1:1234/v1` | Blank if authentication is not required |

Set environment references in **`user_files/.env`**, for example:

```dotenv
GEMINI_API_KEY='your-ai-studio-key'
MY_GATEWAY_TOKEN='your-gateway-key'
```

Custom header example:

```json
{"X-Custom-Token":"${MY_GATEWAY_TOKEN}"}
```

A custom `Authorization` header overrides the API-key field, case-insensitively. For an endpoint expecting `api-key`, clear the API key and set `{"api-key":"${MY_GATEWAY_TOKEN}"}`. Extra body fields may override optional temperature/token limits, but cannot override routing, messages, streaming, tools, number of completions, or stop sequences.

This is a **text-only Chat Completions** adapter, not a universal API translator. Responses-only APIs, native Anthropic Messages, image uploads, tool execution, and base-URL query parameters are unsupported. Azure endpoints requiring `api-version` query parameters need a compatible gateway. Custom headers do not change protocol compatibility.

Redirects, automatic retries, and provider fallback are disabled for generic APIs. TLS verification stays enabled. Empty, invalid, tool-call, filtered, or truncated responses fail instead of producing partial cards. HTTP response bodies are not copied into errors because they may echo secrets.

## 5. Free Gemini with a free Google account

**Potentially yes, using an AI Studio API key—not Google subscription OAuth.**

1. Open [Google AI Studio](https://aistudio.google.com/apikey), create/select an eligible project, and obtain its Gemini API key.
2. Check the project's actual free-tier access, supported models, [pricing](https://ai.google.dev/gemini-api/docs/pricing), and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). A Google AI subscription is not required for eligible free API access.
3. If zero paid usage is essential, do not enable paid billing. AnkiBrain cannot determine whether your key is billed or enforce your cloud spending limit.
4. Apply the **Gemini API** preset. Supply the key directly or through `${GEMINI_API_KEY}` in `.env`, then enter a currently free-tier-eligible text model for that project.
5. Test, Save, and check AI Studio's usage dashboard.

Do not confuse Gemini CLI's advertised personal-account limits with Gemini **API** quotas; they are different services. A Google AI Pro/Ultra subscription does not automatically grant API credits. Free availability varies by region, account, project, and model.

Unpaid prompts/responses may be used for product improvement and human review. Avoid sensitive patient data or confidential study material without checking applicable privacy terms. Google's [API terms](https://ai.google.dev/gemini-api/terms) include regional conditions, including Paid Services requirements when making API clients available to users in the EEA, Switzerland, or UK. Check current eligibility and terms before use/distribution.

## 6. Configuration and limits

The private settings file is **`user_files/ai_providers.json`**, saved atomically with mode `0600` on POSIX. Keys/headers are plaintext; protect Windows ACLs and backups. Only public provider/model metadata reaches the webview.

```json
{
  "provider": "chatgpt",
  "timeout_seconds": 600,
  "document_chunk_size": 6000,
  "providers": {
    "chatgpt": {"model":"gpt-5.6-luna","auth_dir":"","effort":""},
    "openai": {
      "model":"MODEL_ID_FROM_YOUR_PROVIDER",
      "base_url":"https://api.openai.com/v1",
      "api_key":"${OPENAI_API_KEY}",
      "headers":{}, "temperature":null, "max_tokens":null,
      "extra_body":{}, "allow_insecure_http":false
    }
  }
}
```

- Missing optional fields receive defaults; malformed JSON, unknown fields, and invalid values fail visibly. Only `chatgpt` and `openai` are runnable providers. Old `codex`/`claude` selectors require explicit migration through Settings.
- Provider settings replace the local use of the old webview `llmModel`/`temperature` controls; those now belong to Server mode. Legacy `ANKIBRAIN_CODEX_*`, `CODEX_HOME`, and `CLAUDE_CONFIG_DIR` variables have no effect.
- `${NAME}` expansion applies only to API-key/header values. `.env` overrides process environment variables. Missing references fail before sending anything. Provider config and `.env` reload on each request.
- Networking uses standard Python TLS/proxy configuration from the process environment. Proxies must be trusted; certificate verification is never disabled.
- Timeout (1–3,600 seconds) is a **socket-operation** timeout, not a total request deadline. A slow stream can last longer. OAuth/model-catalog operations use 30-second socket timeouts; interactive sign-in waits up to five minutes, plus an in-progress token exchange.
- Document-to-cards chunk size (100–100,000 characters) is not a token count or retrieval-embedding setting. Reduce it for context/response limits. Native streaming responses have 1 MiB per-line and 16 MiB total transport limits.
- Local cost says **Provider-billed**, not `$0`. Consult your provider dashboard for actual credits, charges, and limits.

## 7. Verification and troubleshooting

Offline checks, with no live accounts/charges:

```sh
python3 tests/test_ai_providers.py
# Optional, using the installed Local-mode environment:
user_files/venv/bin/python tests/test_ai_providers.py --runtime
```

These cover config migration/persistence, private credentials, real localhost OAuth callbacks, PKCE/state validation, token refresh races, direct HTTP/SSE, no provider process launches, secret-safe errors, redirect refusal, API headers, IPC serialization, and (with `--runtime`) Qt and LangChain integration.

A real smoke test **uses the selected account's quota/billing**:

```sh
user_files/venv/bin/python ChatAI/AIProviders.py
```

Windows uses `user_files\venv\Scripts\python.exe`. Optional `--config /absolute/path/to/ai_providers.json` tests a separate file without modifying Anki's settings.

- **CLI providers were removed:** open Settings, select native ChatGPT or an API, complete sign-in/configuration, and Save.
- **Not signed in / invalid session / 401:** use the same private sign-in directory, sign out locally, and sign in again. No CLI cache is imported.
- **Callback unavailable:** close other pending logins; allow localhost ports 1455/1457. Browser and Anki must run on the same machine.
- **403 / 404 / 429:** check account access, model/endpoint, or quota respectively. Model catalog availability is not proof of unlimited/free use.
- **HTML / wrong response format:** an API base URL must point to a compatible API, not a consumer website.
- **Local engine/dependency failure:** complete Local-mode installation. Native auth does not remove the legacy document/embedding dependencies or their initial model download.

Validation is offline/local-server testing, Python 3.9 LangChain/Qt integration, and the webview build. **The new browser OAuth flow has not yet been completed against a real account, nor tested in a full running-Anki session.** Live endpoint access, model compatibility, billing, and other operating systems still need user verification. Earlier release tests of a Codex CLI request do not validate this new native implementation.

## Primary references

- [DeepTutor pinned provider implementation](https://github.com/HKUDS/DeepTutor/blob/42fab3cf429a1fbf36b257ab8d116a3814964202/deeptutor/services/llm/provider_core/openai_codex_provider.py) and [OAuth implementation](https://github.com/HKUDS/DeepTutor/blob/42fab3cf429a1fbf36b257ab8d116a3814964202/deeptutor/services/codex_auth/oauth.py)
- [OpenAI authentication](https://developers.openai.com/codex/auth) and [pricing / shared usage](https://developers.openai.com/codex/pricing)
- [Anthropic authentication restrictions](https://code.claude.com/docs/en/legal-and-compliance)
- [Google third-party OAuth restriction](https://github.com/google-gemini/gemini-cli/blob/main/docs/resources/faq.md), [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai), [API terms](https://ai.google.dev/gemini-api/terms)
- [Grok Build authentication](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/02-authentication.md)
- [GitHub Copilot SDK authentication](https://docs.github.com/en/copilot/how-tos/copilot-sdk/auth/authenticate)
- [Kimi membership / permitted integrations](https://www.kimi.com/en/help/kimi-code/membership-guide)
- [Qwen authentication](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/auth/)
