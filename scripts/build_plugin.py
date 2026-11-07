"""Build a machine-local plugin and a clean, relocatable MIT source archive."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import Bridge, write_json

RUNTIME = ('plugin.json', 'server.py', 'viewer_control.py', 'viewer_process.py',
           'config.example.json', 'LICENSE', 'THIRD_PARTY_NOTICES.md')
DIRECTORIES = ('lua', 'extension', 'skills')


def source_files():
    files = [ROOT / f for f in (*RUNTIME, 'README.md', 'install-plugin.ps1', 'uninstall-plugin.ps1', '.gitignore')]
    for directory in (*DIRECTORIES, 'scripts', 'tests'):
        files += [p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return sorted(set(files))


def build(python):
    python = Path(python).resolve()
    if not python.is_file():
        raise ValueError(f'Python not found: {python}')
    manifest = json.loads((ROOT / 'plugin.json').read_text(encoding='utf-8'))
    bridge = Bridge()
    icon = ROOT / 'assets/aseprite.png'
    if not icon.is_file():
        original = bridge.exe.parent / 'data/icons/ase256.png'
        if not original.is_file():
            raise ValueError('Aseprite bundled logo not found; configure ASEPRITE_PATH or run install-plugin.ps1')
        icon.parent.mkdir(exist_ok=True)
        shutil.copy2(original, icon)
    plugin = ROOT / 'plugins/aseprite-local'
    plugin.mkdir(parents=True, exist_ok=True)
    files = [ROOT / f for f in RUNTIME] + [icon]
    for directory in DIRECTORIES:
        files += [p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for source in files:
        target = plugin / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    write_json(plugin / 'mcp.json', {'mcpServers': {'aseprite': {'type': 'stdio', 'command': str(python),
        'args': ['-X', 'utf8', '-s', str(plugin / 'server.py')], 'env': {'ASEPRITE_MCP_HOME': str(ROOT)},
        'startup_timeout_sec': 30, 'tool_timeout_sec': 90}}})
    write_json(ROOT / '.agents/plugins/marketplace.json', {'name': 'aseprite-local-market',
        'interface': {'displayName': 'Aseprite 本地插件'}, 'plugins': [{'name': 'aseprite-local',
        'source': {'source': 'local', 'path': './plugins/aseprite-local'},
        'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'}, 'category': 'Creativity'}]})
    bridge.prepare_live(ROOT / '.state/bootstrap')
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    archive = dist / f"aseprite-local-plugin-{manifest['version']}.zip"
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for source in source_files():
            bundle.write(source, 'aseprite-codex-plugin/' + source.relative_to(ROOT).as_posix())
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(sha + '  ' + archive.name + '\n', encoding='ascii')
    return {'plugin': str(plugin), 'archive': str(archive), 'sha256': sha, 'tools': 8}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    print(json.dumps(build(args.python), ensure_ascii=False, indent=2))
