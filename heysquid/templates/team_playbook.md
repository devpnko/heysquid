# Team Playbook — Agent Assignment Guide by Task Type

PM references this document to assemble the optimal agent team.

## Agent Roster (5 agents + PM)

| Agent | Animal | Model | Role |
|-------|--------|-------|------|
| 🐙 researcher | octopus | Haiku | Exploration/Investigation |
| 🦈 developer | shark | Opus | Implementation/Coding |
| 🐢 reviewer | turtle | Sonnet | Review/Inspection |
| 🐡 tester | pufferfish | Haiku | Testing/QA |
| 🦞 writer | lobster | Sonnet | Writing/Content |

## Development

### Feature Addition
researcher(analyze structure) → PM(plan + confirm) → developer(implement) → reviewer(review) → tester(verify)

### Bug Fix
researcher(find cause, confirm reproduction steps) → developer(fix) → tester(verify)

### Refactoring
researcher(analyze impact scope) → PM(plan + confirm) → developer(refactor) → tester(regression test)

### Dependency Upgrade
researcher(investigate changes, check breaking changes) → developer(upgrade) → tester(full test)

## Code Quality

### Code Review
reviewer(full review) → PM(summary report)

### Security Audit
reviewer(detect vulnerabilities) → researcher(CVE lookup) → PM(report)

### Performance Optimization
researcher(analyze profiling results) → developer(optimize) → tester(benchmark)

## Research & Analysis

### Technical Research
researcher(web search + doc analysis) x2~3 parallel → PM(consolidated report)

### Architecture Analysis
researcher(explore codebase) → researcher(analyze patterns/dependencies) → PM(organize diagrams)

### Competitor/Market Analysis
researcher(web search) x3 parallel → PM(create comparison table)

## Content

### Technical Documentation
researcher(analyze code) → writer(write markdown) → reviewer(review)

### README/Guides
researcher(understand project) → writer(write docs)

### SNS Content
researcher(analyze trends) → writer(draft) → PM(final review)

### Reports
researcher(collect data) x2 parallel → writer(write report) → PM(review)

## Infrastructure

### Deployment/CI-CD
researcher(understand current setup) → developer(modify config) → tester(verify build)

### Environment Setup
researcher(identify requirements) → developer(create config files) → tester(verify functionality)

## Project Management (PM)

### Status Report
researcher(git log + assess progress) → PM(write briefing)

### Schedule/Milestones
researcher(assess current progress) → PM(update roadmap)

---

## Principles

1. **No excessive agent deployment** — PM handles simple tasks directly
2. **Prefer Haiku** — researcher, tester are fast and cost-effective
3. **Maximize parallelism** — run independent tasks concurrently
4. **Verify results** — critical tasks must include reviewer or tester
5. **Only PM reports to user** — agents never send Telegram messages directly
6. **Writer specializes in content** — use for docs/SNS/report writing
