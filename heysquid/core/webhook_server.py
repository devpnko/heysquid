"""경량 webhook 수신 서버 — 외부 시스템이 automation/skill을 트리거.

Usage:
    python -m heysquid.core.webhook_server          # 기본 포트 8585
    python -m heysquid.core.webhook_server 9090      # 커스텀 포트

외부 호출 예시:
    curl -X POST http://localhost:8585/webhook/briefing \
      -H "X-Webhook-Secret: my-secret" \
      -H "Content-Type: application/json" \
      -d '{"args": "quick", "chat_id": 12345}'
"""

import json
import logging
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

from heysquid.automations import run_automation, get_automation_registry
from heysquid.skills import run_skill, get_skill_registry, SkillContext

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = None  # 시작 시 .env에서 로드


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 인증
        auth = self.headers.get("X-Webhook-Secret", "")
        if WEBHOOK_SECRET and auth != WEBHOOK_SECRET:
            self._respond(401, {"ok": False, "error": "Unauthorized"})
            return

        # Body 파싱
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}

        # URL에서 이름 추출: /webhook/<name>
        path = self.path.strip("/")
        parts = path.split("/")
        if len(parts) < 2 or parts[0] != "webhook":
            self._respond(404, {"ok": False, "error": "Use /webhook/<name>"})
            return

        plugin_name = parts[1]
        ctx = SkillContext(
            triggered_by="webhook",
            chat_id=body.get("chat_id", 0),
            args=body.get("args", ""),
            payload=body,
            callback_url=body.get("callback_url", ""),
        )

        # automations 먼저 찾고, 없으면 skills에서 찾기
        if plugin_name in get_automation_registry():
            result = run_automation(plugin_name, ctx)
        else:
            result = run_skill(plugin_name, ctx)

        self._respond(200 if result["ok"] else 500, result)

    def _respond(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        logger.info(format % args)


def start_webhook_server(port: int = 8585):
    """webhook 서버 시작 (블로킹)."""
    global WEBHOOK_SECRET
    from heysquid.core.http_utils import get_secret

    WEBHOOK_SECRET = get_secret("WEBHOOK_SECRET")

    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    logger.info(f"Webhook server listening on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8585
    start_webhook_server(port)
