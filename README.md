# AnkiBrain — Subscription & API Providers

Unofficial fork of [Rosetta Technologies' AnkiBrain](https://github.com/RosettaTechnologies/AnkiBrain)
([original AnkiWeb listing](https://ankiweb.net/shared/info/1915225457)).

Local mode supports **native ChatGPT browser sign-in** and **OpenAI-compatible APIs**,
including presets for Gemini's eligible free API tier, Grok/xAI, and other endpoints.
**No provider CLI is required or invoked.** Models, sign-in storage, API keys, base URLs,
custom headers, timeouts, and request options are configurable. See [AI_PROVIDERS.md](AI_PROVIDERS.md).

**Experimental:** offline OAuth/HTTP tests and real Qt/LangChain integration checks pass.
The new native login has not yet been completed against a real account or in a full
running-Anki session. It uses the ChatGPT-backed Codex Responses service directly—not
the ChatGPT website conversation interface. Other subscription logins are not claimed;
Grok/Gemini API presets are API-key routes, not subscription OAuth. This fork still
inherits upstream's end-of-life Python 3.9 stack; verify your Anki/OS compatibility.

## Install in Anki Desktop

1. Back up your Anki collection and, if already installed, the original add-on's `user_files`.
   Add-ons run with your user account's filesystem permissions; install only code you trust.
2. Download **`AnkiBrain-providers.ankiaddon`** from this fork's
   [GitHub releases](https://github.com/asvintheguy/AnkiBrain/releases).
   Do **not** use GitHub's “Source code (zip)” as the install file: it lacks the built webview.
3. In Anki, open **Tools → Add-ons**. Disable the original AnkiBrain if present, then choose
   **Install from file…** and select the `.ankiaddon` file. Restart Anki.
   The fork uses the separate folder `ankibrain_providers`; the manifest also declares a
   conflict with the original AnkiWeb add-on. Do not enable both together.
4. Choose **Local mode**, not Regular/Server mode. Complete **AnkiBrain → Install…** to set
   up the existing Python/document dependencies, then restart Anki. If the legacy installer
   fails, use the manual setup below. The dependency download can require several GB.
5. Open **AnkiBrain → AI Provider Settings…** and select **ChatGPT — native browser sign-in**.
   Click **Sign in with ChatGPT…** and complete authentication in your browser on the same
   computer as Anki. No CLI installation or API key is needed.
6. Click **Load account models**, choose a model, then **Test (uses quota)** and **Save**.
   If upgrading from a CLI-backed release, this explicit reconfiguration is required;
   the add-on does not import existing CLI logins or silently switch providers.

For Gemini, Grok/xAI, local models, or another API endpoint, follow [AI_PROVIDERS.md](AI_PROVIDERS.md).
No credentials or machine-specific provider configuration are included in the release.

### Manual dependency setup

Use the official native [Anki Desktop distribution](https://apps.ankiweb.net/).
Flatpak/Snap confinement may prevent launching the external Python engine or the browser callback;
those sandboxed installations are not covered by these instructions.

Open **Tools → Add-ons → AnkiBrain — Subscription & API Providers → View Files**.
Copy that folder's path, then **close Anki** before installing dependencies.
Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if necessary and
open a terminal in the add-on folder.

For a **fresh Linux/macOS installation**:

```sh
cd "/absolute/path/to/ankibrain_providers"
uv venv --python 3.9 --seed user_files/venv
uv pip install --python user_files/venv/bin/python -r linux_requirements.txt
```

For **Windows**, use PowerShell and the Windows requirements:

```powershell
Set-Location "C:\absolute\path\to\ankibrain_providers"
uv venv --python 3.9 --seed user_files/venv
uv pip install --python user_files/venv/Scripts/python.exe -r windows_requirements.txt
```

If `user_files/venv` already exists, skip its creation rather than deleting a working
installation. Resolve all installation errors before restarting Anki. Compiled packages
may need C++ build tools: `build-essential` on Debian/Ubuntu, Xcode command-line tools on
macOS, or Visual Studio's **Desktop development with C++** workload on Windows.
The old macOS/Windows dependency sets may need platform-specific adjustments and were
not validated here. Linux dependency resolution was checked with Python 3.9.25.

**The environment must be in `user_files/venv`, not a top-level `venv`.** The upstream
boot routine deletes a top-level `venv`. Python 3.9 is end-of-life; the legacy document
engine has not yet been modernized. Native authentication adds no provider CLI dependency.

### Existing AnkiBrain data and updates

The fork has a different add-on folder, so installing it does not overwrite the original
add-on. Keep the original disabled. Already-added Anki cards stay in your collection.
AnkiBrain's document index/settings do not migrate automatically. Keep a backup and
re-import documents or carefully migrate only your own data; do not copy another user's
credentials or copy a Python virtual environment between paths.

Update GitHub installations by installing a newer `.ankiaddon` from this fork's releases.
Anki preserves the fork's `user_files` directory during add-on replacement, but back it up
before updating. GitHub-only installs do not receive AnkiWeb automatic updates.

## Build an install file from source

With Git, Python 3.9+, and Node/npm available:

```sh
git clone https://github.com/asvintheguy/AnkiBrain.git
cd AnkiBrain
cd webview
npm exec --yes --package=yarn@1.22.22 -- yarn install --frozen-lockfile --non-interactive
npm run build
cd ..
python3 tests/test_ai_providers.py
python3 scripts/build_addon.py
```

Output: **`dist/AnkiBrain-providers.ankiaddon`**. The packager uses Git-tracked runtime
source plus the compiled webview, checks the archive and its assets, and excludes private
settings, keys, documents, virtual environments, Node dependencies, and Python bytecode.
If developing changes, review and `git add` new source files before packaging them.
Never create a release by blindly zipping your entire add-on directory.

Optional real Qt/LangChain integration checks with the local dependencies installed:

```sh
user_files/venv/bin/python tests/test_ai_providers.py --runtime
```

## Publish this fork on AnkiWeb

GitHub publishing does **not** create an AnkiWeb listing. Publish manually when ready:

1. **Verify redistribution/licensing first.** The upstream GitHub repository contains no
   project-level `LICENSE`. [AnkiWeb's terms](https://ankiweb.net/account/terms) require
   shared add-ons to use AGPL3 or a compatible license and assume AGPL3 if no license is
   stated. Verify the applicable license of the upstream code/version being reused (or
   obtain permission), retain attribution and third-party notices, and provide the
   corresponding source. A public GitHub repository alone is not a license grant for
   arbitrary redistribution. This fork does not invent a new license for upstream code.
   Review the providers' authentication/integration terms too; see the provider guide.
2. **Test in a separate Anki profile** on the Anki versions and operating systems you plan
   to advertise. Test first install, document loading/card creation, settings persistence,
   and updating with existing `user_files`. Do not advertise untested compatibility.
3. Build the `.ankiaddon` above. Its ZIP root contains `__init__.py` and `manifest.json`,
   not a containing `AnkiBrain/` directory. Check it contains no API keys or OAuth tokens.
4. Sign into [AnkiWeb](https://ankiweb.net/), open
   [Shared Add-ons](https://ankiweb.net/shared/addons/), and select **Upload**.
5. Create a **new** listing, e.g. **“AnkiBrain — Subscription & API Providers (Unofficial Fork)”**.
   Upload `dist/AnkiBrain-providers.ankiaddon`. Credit Rosetta Technologies and link both
   the upstream project and this fork's source/issues/setup guide. Explain the Local mode
   installation, experimental native authentication, provider billing/quota, and cloud data handling.
6. Set the supported Anki versions/platforms according to your tests, add screenshots and
   a changelog, then submit using the site's current review/publication flow. AnkiWeb
   assigns your fork its **own add-on ID**; do not reuse the original `1915225457` listing.
7. For later updates, edit your listing and upload the new package. Add your newly assigned
   numeric ID to this manifest's `conflicts` list if you will also distribute the named
   `ankibrain_providers` GitHub package, so users do not accidentally run both copies.

AnkiWeb installations use their numeric add-on folder. Moving from the GitHub package to
AnkiWeb is therefore a separate installation: back up your data, disable the GitHub copy,
recreate its Python environment in the new folder, and reconfigure/migrate your own data.
Do not publish your personal `ai_providers.json`, `.env`, `provider_auth` directory, or documents.

Reference: [official Anki add-on packaging/sharing guide](https://addon-docs.ankiweb.net/sharing.html).
