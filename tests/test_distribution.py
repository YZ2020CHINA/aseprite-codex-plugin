"""Check clean source packaging, relocation, stdio and optional CLI lifecycle."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import Bridge, read_json
from viewer_control import Viewer
from scripts.build_plugin import build


class Distribution(unittest.TestCase):
    def test_relocation_and_clean_archive(self):
        result = build(sys.executable)
        destination = ROOT / 'test-relocation' / ('解压-' + uuid.uuid4().hex[:8])
        with zipfile.ZipFile(result['archive']) as bundle:
            names = bundle.namelist()
            self.assertFalse(any(any('/' + part + '/' in n for part in
                ('vendor', '.state', 'outputs', 'assets', 'plugins', 'project-blocks')) for n in names))
            self.assertNotIn('aseprite-codex-plugin/config.json', names)
            self.assertIn('aseprite-codex-plugin/config.example.json', names)
            self.assertIn('aseprite-codex-plugin/LICENSE', names)
            bundle.extractall(destination)
        moved = destination / 'aseprite-codex-plugin'
        env = os.environ.copy()
        env.pop('ASEPRITE_MCP_HOME', None)
        env['PYTHONUTF8'] = '1'
        command = subprocess.run([sys.executable, '-X', 'utf8', str(moved / 'scripts/build_plugin.py')],
            env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(command.returncode, 0, command.stderr)
        plugin = moved / 'plugins/aseprite-local'
        cfg = read_json(plugin / 'mcp.json')['mcpServers']['aseprite']
        self.assertEqual(cfg['command'], 'cmd.exe')
        self.assertEqual(set(cfg), {'type', 'command', 'args', 'cwd'})
        self.assertIn(str(moved.resolve()), (plugin / 'launch-mcp.cmd').read_text(encoding='utf-8'))
        requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                    {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                     'params': {'name': 'aseprite_status', 'arguments': {}}}]
        result = subprocess.run([cfg['command'], *cfg['args']], env=env, cwd=plugin, capture_output=True,
            input=''.join(json.dumps(r) + '\n' for r in requests), text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies[1]['result']['tools']), 8)
        self.assertFalse(replies[2]['result']['isError'])
        self.assertIn('MIT License', (moved / 'LICENSE').read_text())
        for source in (ROOT / 'server.py', ROOT / 'viewer_control.py', ROOT / 'viewer_process.py'):
            self.assertNotIn('from aseprite_live', source.read_text(encoding='utf-8'))

    @unittest.skipUnless(os.environ.get('ASEPRITE_LIVE_PATH'), 'Set ASEPRITE_LIVE_PATH for optional real CLI integration')
    def test_external_viewer(self):
        bridge = Bridge()
        bridge.config['aseprite_live_path'] = os.environ['ASEPRITE_LIVE_PATH']
        viewer = Viewer(bridge)
        watch = ROOT / 'outputs' / ('external-preview-' + uuid.uuid4().hex[:8])
        try:
            state = viewer.call({'action': 'start', 'watch': str(watch), 'port': 0})
            self.assertTrue(state['online'])
            http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with http.open(state['url'], timeout=5) as response:
                self.assertIn(b'<html', response.read().lower())
            identity = read_json(viewer.marker)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                http.open(identity['control_url'] + '/status', timeout=2)
            self.assertEqual(caught.exception.code, 403)
            sprite = str(watch / 'sample.aseprite')
            bridge.call('aseprite_create', {'output': sprite, 'spec': {'width': 4, 'height': 4,
                'durations_ms': [100], 'palette': {'X': '#ff0000'},
                'layers': [{'name': 'Body', 'frames': [{'rows': ['XXXX'] * 4}]}]}})
            observed = None
            for _ in range(80):
                with http.open(state['url'] + '/api/state', timeout=2) as response:
                    observed = json.load(response)
                if observed.get('files'):
                    break
                time.sleep(.1)
            self.assertTrue(observed.get('files'), observed)
            self.assertTrue(viewer.call({'action': 'stop'})['stopped'])
            for _ in range(40):
                if not viewer.call({'action': 'status'})['online']:
                    break
                time.sleep(.1)
            self.assertFalse(viewer.call({'action': 'status'})['online'])
        finally:
            viewer.call({'action': 'stop'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
