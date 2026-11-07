"""Private lifecycle helper. Does not import or contain aseprite-live source."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from server import read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    for name in ('home', 'external', 'watch', 'aseprite', 'port', 'steps'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    marker = Path(args.home) / '.state/external-viewer.json'
    identity = read_json(marker)
    env = os.environ.copy()
    env['PYTHONPATH'] = args.external
    env['PYTHONUTF8'] = '1'
    info = {'instance': identity['instance'], 'watch': args.watch, 'url': None,
            'component': 'N7z/aseprite-live (external AGPL-3.0 process)'}
    child = subprocess.Popen([sys.executable, '-X', 'utf8', '-s', '-m', 'aseprite_live', args.watch,
        '--aseprite', args.aseprite, '--port', args.port, '--max-steps', args.steps],
        cwd=args.external, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    def output():
        for line in child.stdout:
            print(line, end='', flush=True)
            match = re.search(r'aseprite-live: open http://(?:localhost|127\.0\.0\.1):(\d+)', line)
            if match:
                info['url'] = 'http://127.0.0.1:' + match.group(1)
    threading.Thread(target=output, daemon=True).start()
    try:
        deadline = time.monotonic() + 8
        while not info['url'] and time.monotonic() < deadline and child.poll() is None:
            time.sleep(.05)
        if not info['url']:
            raise RuntimeError('External CLI did not announce its browser address')

        class Control(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self):
                if self.headers.get('X-Viewer-Token') != identity['token']:
                    self.send_error(403)
                    return False
                body = json.dumps(info).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return True

            def do_GET(self):
                if self.path != '/status':
                    self.send_error(404)
                else:
                    self.reply()

            def do_POST(self):
                if self.path != '/stop':
                    self.send_error(404)
                elif self.reply():
                    threading.Thread(target=http.shutdown, daemon=True).start()

        http = ThreadingHTTPServer(('127.0.0.1', 0), Control)
        write_json(marker, {**identity, 'control_url': f'http://127.0.0.1:{http.server_port}'})

        def monitor():
            child.wait()
            http.shutdown()
        threading.Thread(target=monitor, daemon=True).start()
        http.serve_forever(poll_interval=.1)
        http.server_close()
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    main()
