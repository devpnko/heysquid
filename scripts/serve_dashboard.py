#!/usr/bin/env python3
"""Dashboard HTTP server with Save API endpoints."""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import base64
import json
import os
import threading

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
WS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'workspaces')


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DATA_DIR, **kwargs)

    def do_POST(self):
        if self.path == '/api/save-workspace':
            content = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self._update_agent_status('workspaces', content)
            self._respond(200, {'ok': True})

        elif self.path == '/api/save-deco-layout':
            content = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self._save_json('dashboard_layout.json', content)
            self._respond(200, {'ok': True})

        elif self.path == '/api/screenshot':
            self._take_screenshot()
            return

        elif self.path == '/api/save-workspace-context':
            content = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            name = content.get('name', '')
            text = content.get('content', '')
            if not name or '/' in name or '..' in name:
                self._respond(400, {'error': 'invalid name'})
                return
            ctx_path = os.path.join(WS_DIR, name, 'context.md')
            os.makedirs(os.path.dirname(ctx_path), exist_ok=True)
            with open(ctx_path, 'w', encoding='utf-8') as f:
                f.write(text)
            self._respond(200, {'ok': True})

        else:
            self._respond(404, {'error': 'not found'})

    def do_GET(self):
        if self.path == '/api/deco-layout':
            path = os.path.join(DATA_DIR, 'dashboard_layout.json')
            if os.path.exists(path):
                with open(path) as f:
                    data = json.load(f)
                self._respond(200, data)
            else:
                self._respond(200, {})
            return

        if self.path.startswith('/api/workspace-context?'):
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            name = qs.get('name', [''])[0]
            if not name or '/' in name or '..' in name:
                self._respond(400, {'error': 'invalid name'})
                return
            ctx_path = os.path.join(WS_DIR, name, 'context.md')
            if os.path.exists(ctx_path):
                with open(ctx_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self._respond(200, {'content': content})
            else:
                self._respond(200, {'content': ''})
            return

        super().do_GET()

    def _update_agent_status(self, key, value):
        path = os.path.join(DATA_DIR, 'agent_status.json')
        with open(path) as f:
            data = json.load(f)
        data[key] = value
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_json(self, filename, content):
        path = os.path.join(DATA_DIR, filename)
        with open(path, 'w') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

    def _take_screenshot(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                page.goto('http://127.0.0.1:8420/dashboard.html', wait_until='networkidle')
                page.wait_for_timeout(2000)  # Wait for animations/data load
                png_bytes = page.locator('.viewport').screenshot(type='png')
                browser.close()
            b64 = base64.b64encode(png_bytes).decode('ascii')
            self._respond(200, {'ok': True, 'image': b64})
        except Exception as e:
            self._respond(500, {'error': str(e)})

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass  # Suppress request logs


if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 8420), DashboardHandler)
    print(f'Dashboard server running on http://127.0.0.1:8420')
    server.serve_forever()
