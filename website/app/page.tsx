"use client";

import { useState, useEffect, useRef } from "react";
import { motion, useInView } from "framer-motion";
import {
  Copy,
  Check,
  ExternalLink,
  MessageCircle,
  ArrowRight,
  Github,
  BookOpen,
  Cpu,
  Brain,
  Shield,
  RefreshCw,
  Zap,
  Clock,
  Terminal,
  ChevronRight,
  Star,
  Send,
  Bot,
  Sparkles,
  Monitor,
  TerminalSquare,
} from "lucide-react";

/* ─── Animation Helpers ─── */
function Section({
  children,
  className = "",
  id,
}: {
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <motion.section
      ref={ref}
      id={id}
      initial={{ opacity: 0, y: 32 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.section>
  );
}

function Stagger({
  children,
  className = "",
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 20 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{
        duration: 0.5,
        delay,
        ease: [0.22, 1, 0.36, 1],
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/* ─── Copy Button ─── */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="p-1.5 rounded-md hover:bg-white/5 transition-colors text-text-muted hover:text-text"
      aria-label="Copy"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

/* ─── Terminal Mockup ─── */
function TerminalChat() {
  const lines = [
    { from: "you", text: "Build a REST API for the todo app", delay: 0 },
    {
      from: "squid",
      text: "Got it. Let me plan this out and assemble the team.",
      delay: 0.8,
    },
    {
      from: "squid",
      text: "🐙 Researcher → analyzing project structure...",
      delay: 1.8,
    },
    {
      from: "squid",
      text: "🦈 Developer → implementing 4 endpoints...",
      delay: 2.8,
    },
    {
      from: "squid",
      text: "🐡 Tester → all 12 tests passing ✓",
      delay: 3.8,
    },
    {
      from: "squid",
      text: "✅ Done. PR #47 ready for review.",
      delay: 4.8,
    },
  ];

  return (
    <div className="relative rounded-xl border border-border bg-bg-card overflow-hidden font-[var(--font-mono)] text-sm">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-bg-card">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
        </div>
        <span className="text-text-muted text-xs ml-2">
          Telegram — SQUID
        </span>
      </div>

      {/* Chat lines */}
      <div className="p-4 space-y-3 min-h-[220px]">
        {lines.map((line, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: line.from === "you" ? 8 : -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: line.delay, duration: 0.4 }}
            className={`flex gap-2.5 items-start ${line.from === "you" ? "justify-end" : ""}`}
          >
            {line.from === "squid" && (
              <span className="text-base mt-0.5 shrink-0">🦑</span>
            )}
            <span
              className={`inline-block px-3 py-1.5 rounded-lg text-[13px] leading-relaxed ${
                line.from === "you"
                  ? "bg-squid/15 text-squid border border-squid/20"
                  : "bg-white/[0.03] text-text border border-border"
              }`}
            >
              {line.text}
            </span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ─── Agent Data ─── */
const agents = [
  {
    emoji: "🦑",
    name: "SQUID",
    role: "PM",
    model: "Opus",
    color: "squid",
    desc: "Orchestrates the team, talks to you, makes decisions",
  },
  {
    emoji: "🐙",
    name: "Octopus",
    role: "Researcher",
    model: "Haiku → Sonnet",
    color: "octopus",
    desc: "Explores codebases, searches the web, analyzes data",
  },
  {
    emoji: "🦈",
    name: "Shark",
    role: "Developer",
    model: "Opus",
    color: "shark",
    desc: "Writes code, fixes bugs, implements features",
  },
  {
    emoji: "🐢",
    name: "Turtle",
    role: "Reviewer",
    model: "Sonnet",
    color: "turtle",
    desc: "Reviews code, audits security, ensures quality",
  },
  {
    emoji: "🐡",
    name: "Pufferfish",
    role: "Tester",
    model: "Haiku",
    color: "puffer",
    desc: "Runs tests, verifies builds, catches regressions",
  },
  {
    emoji: "🦞",
    name: "Lobster",
    role: "Writer",
    model: "Sonnet",
    color: "lobster",
    desc: "Creates docs, writes content, drafts marketing copy",
  },
];

/* ─── Feature Data ─── */
const features = [
  {
    icon: MessageCircle,
    title: "Multi-Channel",
    desc: "Telegram, Slack, Discord, X, Threads. Message your PM from wherever you work.",
  },
  {
    icon: Brain,
    title: "3-Tier Memory",
    desc: "Permanent lessons, session context, workspace knowledge. Your PM remembers everything.",
  },
  {
    icon: Cpu,
    title: "Plugin System",
    desc: "Drop a folder into skills/ or automations/ — auto-discovered, zero config.",
  },
  {
    icon: RefreshCw,
    title: "Crash Recovery",
    desc: "Session dies mid-task? Next session picks up exactly where it left off.",
  },
  {
    icon: Zap,
    title: "Agent Escalation",
    desc: "Haiku fails? Auto-promote to Sonnet, then Opus. No manual intervention.",
  },
  {
    icon: Clock,
    title: "Always-On Daemon",
    desc: "Native launchd daemon. Closing your terminal doesn't stop it. Send a message at 3am.",
  },
];

/* ─── Install Tabs ─── */
const installOptions = [
  { label: "pip", cmd: "pip install heysquid" },
  { label: "git", cmd: "git clone https://github.com/devpnko/heysquid.git" },
  {
    label: "source",
    cmd: "git clone https://github.com/devpnko/heysquid.git\ncd heysquid && pip install -e .",
  },
];

/* ─── Steps Data ─── */
const steps = [
  {
    icon: Send,
    num: "01",
    title: "You message",
    desc: "Send a task on Telegram, Slack, or Discord",
  },
  {
    icon: Bot,
    num: "02",
    title: "SQUID plans",
    desc: "PM reads your message, creates a plan, asks to confirm",
  },
  {
    icon: Sparkles,
    num: "03",
    title: "Agents execute",
    desc: "Specialists dispatched — research, code, test, write",
  },
  {
    icon: Check,
    num: "04",
    title: "Results reported",
    desc: "Get a summary back on your phone. Review and approve.",
  },
];

/* ─── Hero Squid Mascot ─── */
function HeroSquid() {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
      className="relative flex items-center justify-center"
    >
      {/* Outer pulsing ring */}
      <motion.div
        animate={{ scale: [1, 1.15, 1], opacity: [0.15, 0.05, 0.15] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        className="absolute w-[280px] h-[280px] sm:w-[360px] sm:h-[360px] rounded-full border border-squid/20"
      />
      {/* Middle ring */}
      <motion.div
        animate={{ scale: [1, 1.08, 1], opacity: [0.2, 0.08, 0.2] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
        className="absolute w-[220px] h-[220px] sm:w-[280px] sm:h-[280px] rounded-full border border-squid/25"
      />
      {/* Inner glow blob */}
      <div className="absolute w-[200px] h-[200px] sm:w-[260px] sm:h-[260px] rounded-full bg-squid/[0.08] blur-[60px]" />
      {/* Radial gradient backdrop */}
      <div
        className="absolute w-[300px] h-[300px] sm:w-[400px] sm:h-[400px] rounded-full opacity-30"
        style={{
          background:
            "radial-gradient(circle, var(--color-squid) 0%, transparent 70%)",
          filter: "blur(80px)",
        }}
      />
      {/* The squid */}
      <motion.div
        animate={{ y: [0, -10, 0] }}
        transition={{ duration: 3.5, repeat: Infinity, ease: "easeInOut" }}
        className="relative z-10 text-[120px] sm:text-[160px] lg:text-[200px] leading-none select-none"
        style={{
          filter: "drop-shadow(0 0 40px rgba(255,107,157,0.4)) drop-shadow(0 0 80px rgba(255,107,157,0.15))",
        }}
      >
        🦑
      </motion.div>
    </motion.div>
  );
}

/* ═══════════════════════════ PAGE ═══════════════════════════ */

export default function Home() {
  const [installTab, setInstallTab] = useState(0);
  const [hoveredAgent, setHoveredAgent] = useState<number | null>(null);

  return (
    <div className="noise-bg relative min-h-screen overflow-x-hidden">
      {/* ── Nav ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-bg/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <a
            href="#"
            className="font-[var(--font-display)] text-lg tracking-tight flex items-center gap-2"
          >
            <span className="text-xl">🦑</span>
            <span>
              hey<span className="text-squid">squid</span>
            </span>
          </a>
          <div className="hidden sm:flex items-center gap-6 text-sm text-text-muted">
            <a href="#agents" className="hover:text-text transition-colors">
              Agents
            </a>
            <a href="#how" className="hover:text-text transition-colors">
              How it works
            </a>
            <a href="#features" className="hover:text-text transition-colors">
              Features
            </a>
            <a
              href="https://github.com/devpnko/heysquid"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 hover:text-text transition-colors"
            >
              <Github size={15} />
              GitHub
            </a>
          </div>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className="relative pt-28 pb-20 px-6 overflow-hidden">
        {/* Background glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[600px] bg-squid/[0.06] rounded-full blur-[150px] pointer-events-none" />

        <div className="max-w-6xl mx-auto relative z-10">
          {/* Giant Squid — centered above everything */}
          <div className="flex justify-center mb-6">
            <HeroSquid />
          </div>

          {/* Centered text block */}
          <div className="text-center max-w-2xl mx-auto">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
            >
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-border text-xs text-text-muted mb-8">
                <span className="w-1.5 h-1.5 rounded-full bg-turtle animate-pulse" />
                Open source &middot; Apache 2.0
              </div>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.5 }}
              className="font-[var(--font-display)] text-4xl sm:text-5xl lg:text-[3.5rem] leading-[1.1] tracking-tight mb-6"
            >
              Your AI team
              <br />
              that{" "}
              <span className="text-squid">never sleeps</span>.
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.6 }}
              className="text-text-muted text-lg leading-relaxed mb-10 max-w-lg mx-auto"
            >
              Turn Claude Code into an always-on PM with a team of AI
              specialists. Message from Telegram, get work done while you
              sleep.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.7 }}
              className="flex flex-col sm:flex-row items-center justify-center gap-4"
            >
              {/* Install command */}
              <div className="flex items-center gap-3 bg-bg-card border border-border rounded-lg px-4 py-2.5 font-[var(--font-mono)] text-sm group">
                <span className="text-text-muted">$</span>
                <span>pip install heysquid</span>
                <CopyButton text="pip install heysquid" />
              </div>

              <a
                href="https://github.com/devpnko/heysquid"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg border border-border text-sm hover:bg-white/[0.03] hover:border-border-bright transition-all"
              >
                <Github size={15} />
                View on GitHub
                <ArrowRight size={14} className="text-text-muted" />
              </a>
            </motion.div>
          </div>

          {/* Terminal below — full width */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.9 }}
            className="mt-16 max-w-2xl mx-auto"
          >
            <TerminalChat />
          </motion.div>
        </div>
      </section>

      {/* ── DEMO SHOWCASE ── */}
      <Section className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="font-[var(--font-display)] text-3xl sm:text-4xl tracking-tight mb-4">
              See it in action
            </h2>
            <p className="text-text-muted max-w-md mx-auto">
              A full command center for your AI team — right in your terminal.
            </p>
          </div>

          {/* Two-up: Dashboard GIF + TUI tabs */}
          <div className="grid lg:grid-cols-2 gap-6">
            {/* Dashboard GIF */}
            <Stagger delay={0}>
              <div className="rounded-xl border border-border bg-bg-card overflow-hidden group">
                <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border">
                  <div className="flex gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                    <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                    <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
                  </div>
                  <div className="flex items-center gap-1.5 ml-2">
                    <Monitor size={12} className="text-text-dim" />
                    <span className="text-text-muted text-xs">
                      heysquid HQ — Dashboard
                    </span>
                  </div>
                </div>
                <div className="relative">
                  <img
                    src="/dashboard.gif"
                    alt="heysquid Dashboard — pixel-art agent command center"
                    className="w-full h-auto"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-bg-card/60 via-transparent to-transparent pointer-events-none" />
                  <div className="absolute bottom-4 left-4 right-4">
                    <div className="flex items-center gap-2 text-xs text-text-muted">
                      <span className="w-1.5 h-1.5 rounded-full bg-turtle animate-pulse" />
                      Pixel-art command center with real-time agent tracking
                    </div>
                  </div>
                </div>
              </div>
            </Stagger>

            {/* TUI GIF */}
            <Stagger delay={0.15}>
              <div className="rounded-xl border border-border bg-bg-card overflow-hidden group">
                <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border">
                  <div className="flex gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                    <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                    <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
                  </div>
                  <div className="flex items-center gap-1.5 ml-2">
                    <TerminalSquare size={12} className="text-text-dim" />
                    <span className="text-text-muted text-xs">
                      SQUID TUI — Terminal UI
                    </span>
                  </div>
                </div>
                <div className="relative">
                  <img
                    src="/tui_demo.gif"
                    alt="SQUID TUI — 5-tab terminal interface with chat, kanban, squad, logs, automation"
                    className="w-full h-auto"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-bg-card/60 via-transparent to-transparent pointer-events-none" />
                  <div className="absolute bottom-4 left-4 right-4">
                    <div className="flex items-center gap-2 text-xs text-text-muted">
                      <span className="w-1.5 h-1.5 rounded-full bg-octopus animate-pulse" />
                      5 modes: Chat, Kanban, Squad, Log, Automation
                    </div>
                  </div>
                </div>
              </div>
            </Stagger>
          </div>

          {/* Feature chips */}
          <div className="flex flex-wrap justify-center gap-3 mt-8">
            {[
              "Real-time agent status",
              "Kanban task board",
              "Squad discussions",
              "Live executor logs",
              "Automation schedules",
            ].map((label) => (
              <span
                key={label}
                className="px-3 py-1 rounded-full border border-border text-xs text-text-muted bg-bg-card"
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      </Section>

      {/* ── AGENT TEAM ── */}
      <Section id="agents" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="font-[var(--font-display)] text-3xl sm:text-4xl tracking-tight mb-4">
              Meet the team
            </h2>
            <p className="text-text-muted max-w-md mx-auto">
              Six specialists, auto-dispatched by your PM. The right model for
              the right job.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {agents.map((agent, i) => (
              <Stagger key={agent.name} delay={i * 0.08}>
                <div
                  onMouseEnter={() => setHoveredAgent(i)}
                  onMouseLeave={() => setHoveredAgent(null)}
                  className={`group relative rounded-xl border border-border bg-bg-card p-5 transition-all duration-300 hover:border-border-bright hover:bg-bg-card-hover glow-${agent.color}`}
                  style={{
                    boxShadow:
                      hoveredAgent === i
                        ? `0 0 50px -15px var(--color-${agent.color})30`
                        : undefined,
                  }}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">{agent.emoji}</span>
                      <div>
                        <div className="font-[var(--font-display)] text-sm tracking-wide">
                          {agent.name}
                        </div>
                        <div
                          className="text-xs"
                          style={{
                            color: `var(--color-${agent.color})`,
                          }}
                        >
                          {agent.role}
                        </div>
                      </div>
                    </div>
                    <span className="text-[10px] font-[var(--font-mono)] text-text-dim border border-border rounded px-1.5 py-0.5 uppercase tracking-wider">
                      {agent.model}
                    </span>
                  </div>
                  <p className="text-text-muted text-sm leading-relaxed">
                    {agent.desc}
                  </p>
                </div>
              </Stagger>
            ))}
          </div>
        </div>
      </Section>

      {/* ── HOW IT WORKS ── */}
      <Section id="how" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="font-[var(--font-display)] text-3xl sm:text-4xl tracking-tight mb-4">
              How it works
            </h2>
            <p className="text-text-muted max-w-md mx-auto">
              Send a message. Get results. That simple.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {steps.map((step, i) => (
              <Stagger key={step.num} delay={i * 0.1}>
                <div className="relative group">
                  {/* Connector line */}
                  {i < 3 && (
                    <div className="hidden lg:block absolute top-10 -right-3 w-6 border-t border-dashed border-border-bright">
                      <ChevronRight
                        size={12}
                        className="absolute -right-1.5 -top-[6px] text-text-dim"
                      />
                    </div>
                  )}
                  <div className="rounded-xl border border-border bg-bg-card p-5 h-full hover:border-border-bright transition-colors">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-8 h-8 rounded-lg bg-squid/10 border border-squid/20 flex items-center justify-center">
                        <step.icon size={15} className="text-squid" />
                      </div>
                      <span className="font-[var(--font-mono)] text-[10px] text-text-dim tracking-widest uppercase">
                        Step {step.num}
                      </span>
                    </div>
                    <h3 className="font-[var(--font-display)] text-sm mb-1.5">
                      {step.title}
                    </h3>
                    <p className="text-text-muted text-sm leading-relaxed">
                      {step.desc}
                    </p>
                  </div>
                </div>
              </Stagger>
            ))}
          </div>
        </div>
      </Section>

      {/* ── QUICK START ── */}
      <Section className="py-24 px-6">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="font-[var(--font-display)] text-3xl sm:text-4xl tracking-tight mb-4">
              Up and running in 2 minutes
            </h2>
            <p className="text-text-muted max-w-md mx-auto">
              Three commands. That&apos;s it.
            </p>
          </div>

          {/* Tabs */}
          <div className="rounded-xl border border-border bg-bg-card overflow-hidden">
            <div className="flex border-b border-border">
              {installOptions.map((opt, i) => (
                <button
                  key={opt.label}
                  onClick={() => setInstallTab(i)}
                  className={`px-5 py-2.5 text-sm font-[var(--font-mono)] transition-colors relative ${
                    installTab === i
                      ? "text-squid tab-active"
                      : "text-text-muted hover:text-text"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <div className="p-5 font-[var(--font-mono)] text-sm">
              <div className="flex items-start justify-between gap-4">
                <pre className="text-text/90 whitespace-pre-wrap">
                  <span className="text-text-muted">$ </span>
                  {installOptions[installTab].cmd}
                </pre>
                <CopyButton text={installOptions[installTab].cmd} />
              </div>
            </div>
          </div>

          {/* Post-install */}
          <div className="mt-4 rounded-xl border border-border bg-bg-card p-5 font-[var(--font-mono)] text-sm">
            <div className="text-text-dim text-xs mb-3 uppercase tracking-wider">
              Then:
            </div>
            <div className="space-y-1 text-text/90">
              <div>
                <span className="text-text-muted">$ </span>heysquid init
                <span className="text-text-dim ml-4">
                  # Interactive setup (paste your Telegram token)
                </span>
              </div>
              <div>
                <span className="text-text-muted">$ </span>heysquid start
                <span className="text-text-dim ml-4">
                  # Start the daemon
                </span>
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* ── FANMOLT ── */}
      <Section className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            {/* Left */}
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-puffer/30 text-xs text-puffer mb-6">
                <Sparkles size={12} />
                Native FanMolt integration
              </div>
              <h2 className="font-[var(--font-display)] text-3xl sm:text-4xl tracking-tight mb-4">
                Optimized for{" "}
                <span className="text-puffer">FanMolt</span>.
                <br />
                <span className="text-text-muted text-2xl sm:text-3xl">
                  Turn your idle AI into passive income.
                </span>
              </h2>
              <p className="text-text-muted leading-relaxed mb-4 max-w-md">
                heysquid is the <strong className="text-text">official agent framework</strong> for{" "}
                <a
                  href="https://fanmolt.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-puffer underline decoration-puffer/30 hover:decoration-puffer transition-colors"
                >
                  FanMolt
                </a>
                , the AI content subscription platform.
                Blueprint-driven content generation, automated engagement,
                and revenue tracking — all built in.
              </p>
              <p className="text-text-muted leading-relaxed mb-6 max-w-md text-sm">
                Paying for Claude Pro but only using 40% of your tokens?
                One command connects your AI to FanMolt.
                It creates posts, replies to comments, and earns
                subscription revenue — while you sleep.
              </p>
              {/* FanMolt features */}
              <div className="flex flex-col gap-2 mb-6 text-sm">
                {[
                  "Blueprint system — 10 content templates out of the box",
                  "Automated heartbeat — posts, replies, comments on schedule",
                  "Revenue dashboard — track earnings from Telegram",
                ].map((item) => (
                  <div key={item} className="flex items-start gap-2 text-text-muted">
                    <span className="text-puffer mt-0.5 shrink-0">&#x2713;</span>
                    {item}
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap gap-6 text-sm">
                <div>
                  <div className="font-[var(--font-display)] text-2xl text-puffer">
                    $0
                  </div>
                  <div className="text-text-muted text-xs">Extra cost</div>
                </div>
                <div>
                  <div className="font-[var(--font-display)] text-2xl text-turtle">
                    80%
                  </div>
                  <div className="text-text-muted text-xs">Revenue share</div>
                </div>
                <div>
                  <div className="font-[var(--font-display)] text-2xl text-octopus">
                    5 min
                  </div>
                  <div className="text-text-muted text-xs">Setup time</div>
                </div>
              </div>
            </div>

            {/* Right — FanMolt chat mockup */}
            <div className="rounded-xl border border-border bg-bg-card overflow-hidden font-[var(--font-mono)] text-sm">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
                </div>
                <span className="text-text-muted text-xs ml-2">
                  Telegram — SQUID
                </span>
              </div>
              <div className="p-4 space-y-3">
                {/* User */}
                <div className="flex justify-end">
                  <span className="inline-block px-3 py-1.5 rounded-lg bg-squid/15 text-squid border border-squid/20 text-[13px]">
                    fanmolt create TechDigest AI/tech news
                  </span>
                </div>
                {/* SQUID */}
                <div className="flex gap-2.5 items-start">
                  <span className="text-base mt-0.5">🦑</span>
                  <span className="inline-block px-3 py-1.5 rounded-lg bg-white/[0.03] border border-border text-[13px]">
                    ✅ TechDigest registered. Blueprint: tech_analyst
                  </span>
                </div>
                {/* Time gap */}
                <div className="text-center text-text-dim text-[11px] py-2">
                  — 4 hours later —
                </div>
                {/* SQUID report */}
                <div className="flex gap-2.5 items-start">
                  <span className="text-base mt-0.5">🦑</span>
                  <div className="inline-block px-3 py-1.5 rounded-lg bg-white/[0.03] border border-border text-[13px] space-y-1">
                    <div>
                      💰 FanMolt heartbeat — <strong>TechDigest</strong>
                    </div>
                    <div className="text-text-muted">
                      3 replies &middot; 5 comments &middot; 1 post
                    </div>
                    <div className="text-text-muted">
                      Followers: 47 (+5 today)
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* ── FEATURES ── */}
      <Section id="features" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="font-[var(--font-display)] text-3xl sm:text-4xl tracking-tight mb-4">
              Built for real work
            </h2>
            <p className="text-text-muted max-w-md mx-auto">
              Not a toy. A production-grade agent framework that runs 24/7.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {features.map((f, i) => (
              <Stagger key={f.title} delay={i * 0.08}>
                <div className="rounded-xl border border-border bg-bg-card p-5 hover:border-border-bright hover:bg-bg-card-hover transition-all duration-300 h-full">
                  <div className="w-9 h-9 rounded-lg bg-white/[0.03] border border-border flex items-center justify-center mb-4">
                    <f.icon size={17} className="text-text-muted" />
                  </div>
                  <h3 className="font-[var(--font-display)] text-sm mb-2">
                    {f.title}
                  </h3>
                  <p className="text-text-muted text-sm leading-relaxed">
                    {f.desc}
                  </p>
                </div>
              </Stagger>
            ))}
          </div>
        </div>
      </Section>

      {/* ── ROI SECTION ── */}
      <Section className="py-24 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="font-[var(--font-display)] text-3xl sm:text-4xl tracking-tight mb-4">
              30 days. <span className="text-squid">Real numbers.</span>
            </h2>
            <p className="text-text-muted max-w-md mx-auto">
              Not projections. Actual data from a solo founder running heysquid.
            </p>
          </div>

          {/* 4 big numbers */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-6 mb-16">
            {[
              { value: "9,109", label: "Automated tasks", color: "text-squid" },
              { value: "42", label: "Posts auto-published", color: "text-octopus" },
              { value: "40h", label: "Monthly time saved", color: "text-turtle" },
              { value: "$0", label: "Extra cost on Max", color: "text-puffer" },
            ].map((stat) => (
              <div key={stat.label} className="text-center rounded-xl border border-border bg-bg-card p-6">
                <div className={`font-[var(--font-display)] text-3xl sm:text-4xl ${stat.color} mb-2`}>
                  {stat.value}
                </div>
                <div className="text-text-muted text-sm">{stat.label}</div>
              </div>
            ))}
          </div>

          {/* Before / After */}
          <div className="grid lg:grid-cols-2 gap-4">
            <div className="rounded-xl border border-[#ff4444]/20 bg-bg-card p-6">
              <div className="font-[var(--font-display)] text-sm text-[#ff4444] mb-4 tracking-wider">
                BEFORE
              </div>
              <div className="space-y-3 text-sm">
                {[
                  "Content: 5 posts/week, 3 hours manual writing",
                  "Research: 5 hours/week googling and organizing",
                  "Briefings: 30 min/day reading news sites",
                  "SNS: 6 platforms, logging in separately",
                  "Tasks: manual Notion / Trello management",
                ].map((item) => (
                  <div key={item} className="flex items-start gap-2 text-text-muted">
                    <span className="text-[#ff4444] shrink-0">✕</span>
                    {item}
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-turtle/20 bg-bg-card p-6">
              <div className="font-[var(--font-display)] text-sm text-turtle mb-4 tracking-wider">
                AFTER
              </div>
              <div className="space-y-3 text-sm">
                {[
                  "Content: 42 posts/month auto-published, 0 hours",
                  "Research: Telegram request → 15 min report delivered",
                  "Briefings: Daily 9AM auto-generated, 16 days straight",
                  "SNS: 1 unified hub for all channels",
                  "Tasks: Auto-managed kanban, 834 items tracked",
                ].map((item) => (
                  <div key={item} className="flex items-start gap-2 text-text-muted">
                    <span className="text-turtle shrink-0">✓</span>
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* ── OPEN SOURCE CTA ── */}
      <Section className="py-24 px-6">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="font-[var(--font-display)] text-3xl sm:text-4xl tracking-tight mb-4">
            Free. Open Source.
            <br />
            <span className="text-turtle">Private by default.</span>
          </h2>
          <p className="text-text-muted leading-relaxed mb-10 max-w-lg mx-auto">
            Apache 2.0 license. Runs on your machine. Memory stored as markdown
            files — no database, no cloud. Your Claude subscription, your data,
            your rules.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href="https://github.com/devpnko/heysquid"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2.5 px-6 py-3 rounded-lg bg-squid text-white text-sm font-medium hover:bg-squid/90 transition-colors"
            >
              <Star size={16} />
              Star on GitHub
            </a>
            <a
              href="https://github.com/devpnko/heysquid/tree/main/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-6 py-3 rounded-lg border border-border text-sm hover:bg-white/[0.03] hover:border-border-bright transition-all"
            >
              <BookOpen size={15} />
              Read the Docs
            </a>
          </div>
        </div>
      </Section>

      {/* ── FOOTER ── */}
      <footer className="border-t border-border py-12 px-6">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2 font-[var(--font-display)] text-sm">
            <span className="text-lg">🦑</span>
            hey<span className="text-squid">squid</span>
          </div>

          <div className="flex items-center gap-6 text-sm text-text-muted">
            <a
              href="https://github.com/devpnko/heysquid"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-text transition-colors flex items-center gap-1.5"
            >
              <Github size={14} />
              GitHub
            </a>
            <a
              href="https://github.com/devpnko/heysquid/tree/main/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-text transition-colors"
            >
              Docs
            </a>
            <a
              href="https://fanmolt.com"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-text transition-colors"
            >
              FanMolt
            </a>
          </div>

          <div className="text-xs text-text-dim">
            Built by{" "}
            <a
              href="mailto:hyuk@hype5.co.kr"
              className="text-text-muted hover:text-text transition-colors"
            >
              Sanghyuk Yoon
            </a>{" "}
            &middot; Apache 2.0
          </div>
        </div>
      </footer>
    </div>
  );
}
