# AVR Pitch Deck Brief — Claude Design (Slide Deck mode)

**Last updated:** 2026-04-20
**Workflow:** Pattern C (slide-deck mode) from [claude-ai-design](~/.claude/codex/nodes/claude-ai-design.md) — one-prompt on-brand deck, replaces Figma+Keynote loop.

---

## How to use

1. Open `claude.ai/design`.
2. Switch to **Slide deck** tab.
3. Select design system: **`citability.dev Design System`** (must be registered — confirm in the Design systems tab before prompting).
4. Paste the prompt below.
5. Review against the **QA checklist** at the bottom before sending to a prospect.

---

## The prompt (paste verbatim)

> Generate a 10-slide consulting pitch deck for **AI Visibility Readiness (AVR)** — an audit methodology that measures whether a website is discoverable, recommendable, and citable by AI systems (ChatGPT, Perplexity, Claude, Google AI Overviews).
>
> **Design system:** citability.dev (Forensic Telemetry — dark-mode, OKLch tokens, mono-numeral signature, JetBrains Mono for every numeral, Inter for body).
>
> **Audience:** marketing directors / founders at DA 40-90 sites whose AI citation rate is near-zero despite strong traditional SEO.
>
> **Motion:** FadeInSection only. No parallax, no shader backgrounds, no cursor-reactive effects. Respect `prefers-reduced-motion`.
>
> **Slide outline:**
>
> 1. **Title** — "AI Visibility Readiness" + subtitle "The audit your SEO team isn't running" + tagline "Ahrefs 92 · AI citations 5%". Dated footer mono.
> 2. **The gap** — DA ≠ AI-READY. Bar chart: Reddit (99), Medium (95), Ahrefs (92) all NOT-READY on AI infrastructure. chudi.dev (5) AI-READY. One-line: *Domain Authority does not predict AI citation.*
> 3. **Three measurement axes** — Visibility (does AI know you exist?), Recommendation (does AI suggest you?), Citation (does AI link to you?). Three-column layout with a single metric per column in mono.
> 4. **What we measure [VERIFIABLE]** — 12-check infrastructure audit. Receipt-style list: robots.txt AI-crawler allowlist, llms.txt, schema coverage, Core Web Vitals, sitemap freshness, structured data depth. Each line stamped [VERIFIABLE].
> 5. **What we measure [BEST-EFFORT]** — 37 queries across ChatGPT, Perplexity, Claude. Confidence bands (LOW/MODERATE/HIGH by round count). Each line stamped [BEST-EFFORT]. Hard visual separation from slide 4 — evidence tiers never mix.
> 6. **The 3-band verdict** — StatusBadge-style: `AI-READY` / `FOUNDATION-READY` / `NOT-READY`. One sentence under each. No fake composite score.
> 7. **Sample deliverable** — terminal-card screenshot of an audit report header. Shows client name, audit date, verdict band, top-3 prioritized actions. Mono-numerals throughout.
> 8. **Case study** — chudi.dev went from infra-gap to AI-READY (9/9) using this methodology. DA 5 outscores DA 99 sites on AI infrastructure. Single metric hero in mono.
> 9. **Pricing tiers** — 4-row table: Free Scan ($0) · Quick Report ($X) · Full Audit + Strategy Call ($XX) · Implementation Sprint ($XXX). Mono for every dollar amount.
> 10. **Next step** — "Run the free scan on your domain" + contact row (hello@chudi.dev, citability.dev). Editorial, not marketing-y.
>
> **Constraints:** No glassmorphism, no backdrop-blur. No hardcoded colors outside OKLch tokens. Dark mode only. Every number, percent, score, stat, date must render in JetBrains Mono with `tabular-nums`. Receipt-style dividers between evidence tiers. No emoji.

---

## Brand guardrails (reject output that violates any)

From [claude-ai-design](~/.claude/codex/nodes/claude-ai-design.md) constraint guardrails applied to citability.dev's Forensic Telemetry lock:

- [ ] **No glassmorphism** (`backdrop-filter: blur`, `backdrop-blur-*`)
- [ ] **Dark-only** — no light variants leaking through
- [ ] **OKLch tokens only** — no hardcoded hex except brand social colors
- [ ] **FadeInSection only** — any other motion rejected
- [ ] **Mono-numerals** — every numeral in JetBrains Mono, `tabular-nums`
- [ ] **[VERIFIABLE] and [BEST-EFFORT] never mix on the same slide**
- [ ] **No fake composite score** — the audit is explicitly not a single 0-100 number
- [ ] **Editorial > marketing** — no hero CTAs screaming "BOOK NOW", no emoji

If the first generation violates ≥2 guardrails, re-prompt with the specific violation called out. Do not "fix" in Figma after export — the deck is a sandbox output; regenerate until brand-lock holds.

---

## Post-generation QA (before sending to a prospect)

1. **Spot-check slide 2** — are the DA numbers accurate? (Pull latest from `sample-audits/`.)
2. **Spot-check slide 4 + 5** — evidence tier labels `[VERIFIABLE]` and `[BEST-EFFORT]` present and visually distinct?
3. **Spot-check slide 6** — verdict badges match the 3 bands from `scripts/run_audit.py` (`AI-READY` / `FOUNDATION-READY` / `NOT-READY`). Case-sensitive.
4. **Spot-check slide 9** — pricing matches the citability.dev service tiers. Update `$X / $XX / $XXX` placeholders to the current numbers before sending.
5. **Read-back for slide 7** — audit report header shows the right client name + date. Do not ship a deck with placeholder client names.
6. **Export** — share-link or PDF export. Never ship the Claude Design editor URL to a client.

---

## What this brief is NOT

- NOT a codegen source. This deck lives in Claude Design; it does not ship to citability.dev's Svelte codebase.
- NOT a replacement for the 30-min strategy call. The deck is the opener; the call is the close.
- NOT permanent. Re-run every time AVR framework version bumps (currently v1.1.0 at `FRAMEWORK.md:6`). Version-mismatch decks are worse than no deck.

---

## Iteration log

| Date | What changed | Deck version |
|------|-------------|--------------|
| 2026-04-20 | Initial brief | v0.1 (unreleased) |
