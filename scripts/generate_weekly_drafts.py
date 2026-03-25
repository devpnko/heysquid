"""주간 콘텐츠 초안을 옵시디언 마크다운으로 생성."""

from datetime import date, timedelta

from heysquid.skills.threads_fortune._content_generator import generate_weekly_drafts
from heysquid.skills.threads_fortune._generator import generate_daily_fortune

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
OUTPUT = "workspaces/threads/drafts_0325_0329.md"


def main():
    start = date(2026, 3, 25)
    results = []

    # 08:00 띠별 운세
    for i in range(5):
        d = start + timedelta(days=i)
        text = generate_daily_fortune(d)
        results.append({
            "date": d,
            "time": "08:00",
            "type": "띠별운세",
            "text": text,
            "cta": "👇가장 정확한 오늘의 운세는 여기 DKBSQD.com 🔮",
        })

    # 14:00 + 20:00
    drafts = generate_weekly_drafts(start)
    for d in drafts:
        results.append(d)

    # 정렬
    results.sort(key=lambda x: (str(x.get("date", "")), x.get("time", "")))

    lines = [
        "# dkbsqd 주간 콘텐츠 초안 (3/25~29)",
        "",
        "> 자동 생성 초안. 검수 후 큐 등록.",
        "> 생성일: 2026-03-25",
        "",
    ]

    current_date = None
    for r in results:
        d = r.get("date", "")
        d_str = str(d)
        if d_str != current_date:
            current_date = d_str
            if hasattr(d, "weekday"):
                lines.append(f"## {d.month}/{d.day} ({WEEKDAY_KR[d.weekday()]})")
            else:
                lines.append(f"## {d_str}")
            lines.append("")

        time_str = r.get("time", "")
        typ = r.get("type", "")

        if typ == "띠별운세":
            lines.append(f"### {time_str} 띠별 운세 ✅자동")
            lines.append("```")
            lines.append(r["text"])
            lines.append("```")
            lines.append(f"첫댓글: `{r['cta']}`")

        elif typ == "사주심리":
            theme = r.get("sipsung_theme", "")
            cat = r.get("category", "")
            pillar = r.get("pillar", {})
            ilju = pillar.get("gan", "") + pillar.get("ji", "")
            lines.append(f"### {time_str} 사주 심리 분석 📝검수필요")
            lines.append(f"**테마:** {theme} / {cat}")
            lines.append(f"**일주:** {ilju}")
            lines.append("```")
            lines.append(r["draft"])
            lines.append("```")
            lines.append(f"첫댓글: `{r['cta']}`")
            lines.append(f"> {r.get('notes', '')}")

        elif typ == "연프분석":
            themes = r.get("themes", [])
            pillar = r.get("pillar", {})
            ilju = pillar.get("gan", "") + pillar.get("ji", "")
            lines.append(f"### {time_str} 연프 사주 분석 📝검수필요")
            lines.append(f"**테마:** {' vs '.join(themes)}")
            lines.append(f"**일주:** {ilju}")
            lines.append("```")
            lines.append(r["draft"])
            lines.append("```")
            lines.append(f"첫댓글: `{r['cta']}`")
            lines.append(f"> {r.get('notes', '')}")

        lines.append("")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ {OUTPUT} 생성 완료 ({len(results)}개 콘텐츠)")


if __name__ == "__main__":
    main()
