#!/usr/bin/env python3
"""
telecode 실시간 스트림 뷰어

사용법:
    tail -f logs/executor.stream.jsonl | python3 scripts/stream_viewer.py

    또는:
    bash scripts/monitor.sh
"""

import sys
import json

def main():
    print("=" * 50)
    print("  telecode 실시간 모니터")
    print("  Ctrl+C로 종료")
    print("=" * 50)
    print()

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = d.get("type", "")

            if t == "system":
                subtype = d.get("subtype", "")
                if subtype == "init":
                    sid = d.get("session_id", "?")[:12]
                    model = d.get("model", "?")
                    print(f"\033[36m[SESSION]\033[0m {sid}... ({model})")

            elif t == "assistant":
                content = d.get("message", {}).get("content", [])
                for c in content:
                    if c["type"] == "text":
                        text = c["text"].strip()
                        if text:
                            print(f"\033[33m[AI]\033[0m {text}")
                    elif c["type"] == "tool_use":
                        name = c.get("name", "?")
                        inp = c.get("input", {})

                        # 도구별 요약
                        if name == "Read":
                            detail = inp.get("file_path", "")
                            print(f"\033[35m[TOOL]\033[0m 📖 Read → {detail}")
                        elif name == "Bash":
                            cmd = inp.get("command", "")
                            if len(cmd) > 80:
                                cmd = cmd[:80] + "..."
                            print(f"\033[35m[TOOL]\033[0m 💻 Bash → {cmd}")
                        elif name == "Edit":
                            fp = inp.get("file_path", "")
                            print(f"\033[35m[TOOL]\033[0m ✏️  Edit → {fp}")
                        elif name == "Write":
                            fp = inp.get("file_path", "")
                            print(f"\033[35m[TOOL]\033[0m 📝 Write → {fp}")
                        elif name == "Grep":
                            pat = inp.get("pattern", "")
                            print(f"\033[35m[TOOL]\033[0m 🔍 Grep → {pat}")
                        elif name == "Glob":
                            pat = inp.get("pattern", "")
                            print(f"\033[35m[TOOL]\033[0m 📂 Glob → {pat}")
                        elif name == "Task":
                            desc = inp.get("description", "")
                            print(f"\033[35m[TOOL]\033[0m 🤖 Task → {desc}")
                        else:
                            detail = str(inp)
                            if len(detail) > 80:
                                detail = detail[:80] + "..."
                            print(f"\033[35m[TOOL]\033[0m {name} → {detail}")

            elif t == "user":
                # tool result (보통 길어서 생략)
                pass

            elif t == "result":
                cost = d.get("total_cost_usd", 0)
                dur = d.get("duration_ms", 0) / 1000
                turns = d.get("num_turns", 0)
                result_text = d.get("result", "")
                if len(result_text) > 100:
                    result_text = result_text[:100] + "..."

                print()
                print("\033[32m" + "─" * 50 + "\033[0m")
                print(f"\033[32m[DONE]\033[0m 💰 ${cost:.4f} | ⏱ {dur:.1f}초 | 🔄 {turns}턴")
                if result_text:
                    print(f"\033[32m[결과]\033[0m {result_text}")
                print("\033[32m" + "─" * 50 + "\033[0m")
                print()

    except KeyboardInterrupt:
        print("\n\n종료.")

if __name__ == "__main__":
    main()
