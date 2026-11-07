"""MIT adapter supervising a separately installed aseprite-live CLI process."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

_children = {}


class Viewer:
    def __init__(self, bridge):
        self.bridge = bridge
        self.root = bridge.root
        self.marker = self.root / '.state/external-viewer.json'
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, info, stop=False):
        address = urlsplit(info['control_url'])
        if address.scheme != 'http' or address.hostname != '127.0.0.1' or address.path:
            raise ValueError('Invalid local control address')
        req = urllib.request.Request(info['control_url'] + ('/stop' if stop else '/status'),
            data=b'' if stop else None, headers={'X-Viewer-Token': info['token']})
        with self.http.open(req, timeout=2) as response:
            result = json.load(response)
        if result.get('instance') != info['instance']:
            raise ValueError('Viewer identity mismatch')
        return result

    def state(self):
        from server import read_json
        return {**self.request(read_json(self.marker)), 'online': True}

    def call(self, args):
        from server import integer, read_json, write_json
        action = args.get('action', 'status')
        try:
            state = self.state()
        except (OSError, ValueError, KeyError):
            state = {'online': False}
        if action == 'status':
            return state
        if action == 'stop':
            if not state['online']:
                return {'online': False, 'stopped': False}
            self.request(read_json(self.marker), stop=True)
            owned = _children.pop(str(self.root), None)
            if owned is not None:
                owned.wait(timeout=8)
            return {'stopped': True, 'online': False}
        if action != 'start':
            raise ValueError('action must be start, status or stop')
        watch = Path(args.get('watch', str(self.bridge.outputs))).expanduser().resolve()
        if state['online']:
            if state['watch'] != str(watch):
                raise ValueError('Viewer watches a different directory; stop it before changing watch')
            return {**state, 'started': False}
        external = Path(self.bridge.config.get('aseprite_live_path') or self.root / '.state/external/aseprite-live').resolve()
        if not (external / 'aseprite_live/__main__.py').is_file():
            raise ValueError('Install optional N7z/aseprite-live first: scripts/install_live.ps1; it is separately licensed AGPL-3.0')
        if sys.version_info < (3, 12):
            raise ValueError('aseprite-live requires Python 3.12+')
        watch.mkdir(parents=True, exist_ok=True)
        port = integer(args.get('port', 7777), 'port', 0, 65535)
        steps = integer(args.get('max_steps', 200), 'max_steps', 1, 1000)
        lock = self.root / '.state/external-viewer-start.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ValueError('Viewer startup pending; inspect its log before retrying')
        os.close(fd)
        try:
            write_json(self.marker, {'token': secrets.token_hex(32), 'instance': secrets.token_hex(16)})
            log = self.root / '.state/external-viewer.log'
            with log.open('ab') as output:
                proc = subprocess.Popen([sys.executable, '-X', 'utf8', '-s', str(self.root / 'viewer_process.py'),
                    '--home', str(self.root), '--external', str(external), '--watch', str(watch),
                    '--aseprite', str(self.bridge.exe), '--port', str(port), '--steps', str(steps)],
                    stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            for _ in range(100):
                time.sleep(.1)
                try:
                    state = self.state()
                    _children[str(self.root)] = proc
                    return {**state, 'started': True, 'log': str(log)}
                except (OSError, ValueError, KeyError):
                    if proc.poll() is not None:
                        break
            raise RuntimeError(f'Viewer did not start; read {log}')
        finally:
            lock.unlink(missing_ok=True)

    def event(self, message, phase):
        # The standalone CLI watches saves. Tool labels require upstream proxy mode.
        pass
