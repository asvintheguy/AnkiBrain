"""Build an .ankiaddon from reviewed Git-tracked source and a prebuilt webview.

Run from anywhere: python3 scripts/build_addon.py
Never zip the whole checkout: user_files contains private credentials and documents.
"""
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent


def main():
    if not (ROOT / 'webview/build/index.html').is_file():
        raise SystemExit('Build the webview first: cd webview && yarn install --frozen-lockfile && yarn build')
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    files = set()
    for name in tracked:
        path = Path(name)
        allowed = (
            len(path.parts) == 1 and path.suffix in ('.py', '.sh', '.bat', '.ps1', '.txt', '.md')
            or name == 'manifest.json'
            or name.startswith('ChatAI/') and path.suffix == '.py'
            or name.startswith('user_files/bundled_dependencies/')
            or name in ('user_files/README.md', 'user_files/pulmonary_hypertension_sample.docx')
        )
        if allowed and (ROOT / path).is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            files.add(path)
    files.update(path.relative_to(ROOT) for path in (ROOT / 'webview/build').rglob('*') if path.is_file())
    required = {'__init__.py', 'manifest.json', 'InterprocessCommand.py', 'AIProviderDialog.py',
                'ChatAI/AIProviders.py', 'ChatAI/ProviderLLM.py', 'webview/build/index.html',
                'webview/build/asset-manifest.json', 'user_files/bundled_dependencies/dotenv/__init__.py'}
    names = {path.as_posix() for path in files}
    if not required <= names:
        raise SystemExit('Missing required files; review and git add new source before packaging: ' + ', '.join(sorted(required - names)))
    if any((ROOT / path).resolve() != ROOT / path for path in files):
        raise SystemExit('Refusing symlinks in the release package.')

    output = ROOT / 'dist/AnkiBrain-providers.ankiaddon'
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(ROOT / path, path.as_posix())

    # Runnable release check: valid ZIP, correct root layout, all compiled assets, no personal state.
    with ZipFile(output) as archive:
        names = set(archive.namelist())
        assert archive.testzip() is None
        assert required <= names
        assert json.loads(archive.read('manifest.json'))['package'] == 'ankibrain_providers'
        for asset in json.loads(archive.read('webview/build/asset-manifest.json'))['files'].values():
            assert 'webview/build/' + asset.removeprefix('./').lstrip('/') in names
        assert not any('__pycache__' in name or name.endswith('.pyc') or '/node_modules/' in name for name in names)
        assert all(not name.startswith('user_files/') or name.startswith('user_files/bundled_dependencies/')
                   or name in ('user_files/README.md', 'user_files/pulmonary_hypertension_sample.docx') for name in names)
    print(f'Built and checked: {output} ({output.stat().st_size / 1024 / 1024:.1f} MiB)')


if __name__ == '__main__':
    main()
