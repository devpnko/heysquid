#!/usr/bin/env python3
"""Dashboard HTTP server with Save API endpoints."""

from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
import base64
import json
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
WS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'workspaces')
TEMPLATE_HTML = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'heysquid', 'templates', 'dashboard.html'
)

# Cache for automations data — survives file corruption from concurrent writes
_automations_cache = {}
_workspaces_cache = {}


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DATA_DIR, **kwargs)

    def do_POST(self):
        if self.path == '/api/save-workspace':
            content = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            from heysquid.dashboard._store import store as _store
            _store.modify("workspaces", lambda data: content)
            self._respond(200, {'ok': True})

        elif self.path == '/api/kanban/feedback':
            content = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            task_id = content.get('task_id', '')
            message = content.get('message', '')
            title = content.get('title', '')
            if not task_id or not message:
                self._respond(400, {'error': 'task_id and message required'})
                return
            from heysquid.dashboard.kanban import add_kanban_activity
            add_kanban_activity(task_id, 'pm', message)
            # Inject into messages.json to trigger PM session
            from heysquid.channels.dashboard import inject_feedback
            inject_feedback(message, task_title=title, task_id=task_id)
            self._respond(200, {'ok': True})

        elif self.path == '/api/kanban/delete':
            content = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            task_id = content.get('task_id', '')
            if not task_id:
                self._respond(400, {'error': 'task_id required'})
                return
            from heysquid.dashboard.kanban import delete_kanban_task
            deleted = delete_kanban_task(task_id)
            self._respond(200, {'ok': True, 'deleted': deleted})

        elif self.path == '/api/kanban/merge':
            content = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            source_id = content.get('source_id', '')
            target_id = content.get('target_id', '')
            if not source_id or not target_id:
                self._respond(400, {'error': 'source_id and target_id required'})
                return
            from heysquid.dashboard.kanban import merge_kanban_tasks
            merged = merge_kanban_tasks(source_id, target_id)
            self._respond(200, {'ok': True, 'merged': merged})

        elif self.path == '/api/kanban/move':
            content = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            task_id = content.get('task_id', '')
            column = content.get('column', '')
            if not task_id or not column:
                self._respond(400, {'error': 'task_id and column required'})
                return
            from heysquid.dashboard.kanban import move_kanban_task
            moved = move_kanban_task(task_id, column)
            self._respond(200, {'ok': True, 'moved': moved})

        elif self.path == '/api/automation/config':
            content = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            name = content.get('name', '')
            if not name:
                self._respond(400, {'error': 'name required'})
                return
            self._save_automation_config(name, content)
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

        # Serve agent_status.json with live migration (skills → automations)
        if self.path.startswith('/agent_status.json'):
            global _automations_cache, _workspaces_cache
            status_path = os.path.join(DATA_DIR, 'agent_status.json')
            try:
                with open(status_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # automations: prefer separate automations.json
                auto_path = os.path.join(DATA_DIR, 'automations.json')
                try:
                    with open(auto_path, 'r', encoding='utf-8') as af:
                        data['automations'] = json.load(af)
                except (FileNotFoundError, json.JSONDecodeError):
                    # Fallback: in-memory migration from agent_status.json
                    if 'skills' in data and 'automations' not in data:
                        data['automations'] = data.pop('skills')
                    elif 'skills' in data:
                        data.pop('skills', None)
                    if 'automations' not in data:
                        data['automations'] = {}
                # kanban: prefer separate kanban.json (Phase 2 split)
                kanban_path = os.path.join(DATA_DIR, 'kanban.json')
                try:
                    with open(kanban_path, 'r', encoding='utf-8') as kf:
                        data['kanban'] = json.load(kf)
                except (FileNotFoundError, json.JSONDecodeError):
                    if 'kanban' not in data or data['kanban'] is None:
                        data['kanban'] = {"tasks": []}
                # Cache non-empty automations data (survives file corruption)
                if data['automations']:
                    _automations_cache = data['automations']
                elif _automations_cache:
                    data['automations'] = _automations_cache
                # workspaces: prefer separate workspaces.json
                ws_json_path = os.path.join(DATA_DIR, 'workspaces.json')
                try:
                    with open(ws_json_path, 'r', encoding='utf-8') as wf:
                        data['workspaces'] = json.load(wf)
                except (FileNotFoundError, json.JSONDecodeError):
                    # Fallback: auto-populate from directory
                    if 'workspaces' not in data:
                        data['workspaces'] = {}
                        if os.path.isdir(WS_DIR):
                            for name in os.listdir(WS_DIR):
                                if os.path.isdir(os.path.join(WS_DIR, name)):
                                    data['workspaces'][name] = {
                                        'status': 'standby',
                                        'last_active': '', 'description': name,
                                    }
                # squad_log: prefer separate squad_log.json
                sq_path = os.path.join(DATA_DIR, 'squad_log.json')
                try:
                    with open(sq_path, 'r', encoding='utf-8') as sqf:
                        sq_data = json.load(sqf)
                        if sq_data:  # non-empty dict = active squad
                            data['squad_log'] = sq_data
                except (FileNotFoundError, json.JSONDecodeError):
                    pass  # keep whatever's in agent_status.json
                # Cache non-empty workspaces data
                if data.get('workspaces'):
                    _workspaces_cache = data['workspaces']
                elif _workspaces_cache:
                    data['workspaces'] = _workspaces_cache
                content = json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(content)
            except (FileNotFoundError, json.JSONDecodeError):
                resp = {}
                # Try separate JSON files even when agent_status.json fails
                for fname, key, default in [
                    ('kanban.json', 'kanban', {"tasks": []}),
                    ('automations.json', 'automations', _automations_cache or {}),
                    ('workspaces.json', 'workspaces', _workspaces_cache or {}),
                ]:
                    try:
                        with open(os.path.join(DATA_DIR, fname), 'r', encoding='utf-8') as sf:
                            resp[key] = json.load(sf)
                    except (FileNotFoundError, json.JSONDecodeError):
                        resp[key] = default
                self._respond(200, resp)
            return

        # Serve dashboard.html from templates/ (single source of truth)
        if self.path == '/dashboard.html' or self.path == '/':
            try:
                with open(TEMPLATE_HTML, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, 'dashboard.html not found in templates/')
            return

        super().do_GET()

    def _save_automation_config(self, name, content):
        from datetime import datetime, timedelta
        global _automations_cache

        # 1. Update skills_config.json (separate file, single writer)
        config_path = os.path.join(DATA_DIR, 'skills_config.json')
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}
        fields = {k: v for k, v in content.items() if k != 'name'}
        config.setdefault(name, {}).update(fields)
        with open(config_path, 'w') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # 2. Update automations.json (flock-protected via store)
        from heysquid.dashboard._store import store as _store

        def _modify(data):
            if name not in data:
                return False  # skip save
            for key in ('schedule', 'enabled', 'description', 'workspace'):
                if key in content:
                    data[name][key] = content[key]
            if 'schedule' in content and data[name].get('trigger') == 'schedule':
                try:
                    now = datetime.now()
                    h, m = content['schedule'].split(':')
                    next_dt = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
                    if next_dt <= now:
                        next_dt += timedelta(days=1)
                    data[name]['next_run'] = next_dt.strftime('%Y-%m-%dT%H:%M')
                except (ValueError, IndexError):
                    pass

        _store.modify("automations", _modify)

        # 3. Update server cache
        _automations_cache = {}

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


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 8420), DashboardHandler)
    print(f'Dashboard server running on http://127.0.0.1:8420')
    server.serve_forever()
