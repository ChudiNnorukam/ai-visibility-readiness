# Wikidata submission risk assessment (2026-05-21)

## Verdict per Q-item

| Q-item | Notability criterion satisfied? | Risk of deletion nomination | Recommendation |
|---|---|---|---|
| AI Visibility Readiness Framework | Criterion 2 (clearly identifiable conceptual entity) IF backed by >=2 reliable independent sources | MEDIUM-HIGH | Submit ONLY after first independent third-party coverage lands (currently 1 source: FCC guest post by author himself, which is NOT independent) |
| AVR Score | Criterion 3 (structural need; supports Framework item's statements) IF Framework item is accepted | MEDIUM | Submit AFTER Framework Q-item is accepted; depends on it |
| calibration receipt | Criterion 3 IF citability.dev is referenced from accepted Q-items elsewhere | HIGH | DEFER, concept is too new, only one source (citability.dev/docs), high deletion risk |

## Why the risk

Per `Wikidata:Notability` (fetched 2026-05-21):

> Criterion 2: "It refers to an instance of a clearly identifiable conceptual or material entity that can be described using serious and publicly available references."

Per `Help:Sources` (fetched 2026-05-21):

> "References should point to reliable sources of information such as university-level textbooks or reference books, academic journals, and newspapers."

Self-published GitHub repos and personal blogs are NOT explicitly endorsed as reliable sources. The FCC guest post is the ONLY third-party-platform citation, and it was authored BY Chudi Nnorukam (not an independent source covering the framework).

Concretely, a Wikidata patroller seeing the Framework Q-item with sources [chudi.dev/framework, github.com/ChudiNnorukam/ai-visibility-readiness, freecodecamp.org/news/<chudi-post>] could reasonably nominate it for deletion on grounds: "single-author framework, no independent secondary sources, fails Criterion 2 reliable-source test."

## Suggested staging

1. **Now (2026-05-21):** Draft the three Q-items per operator request. Drafts are operator-only; do NOT submit.
2. **Wait gate:** Defer submission until at least ONE independent third-party source (a guest post NOT by Chudi, an academic paper, a recognized industry blog post by a different author) covers either the Framework or AVR Score by name. The deletion-nomination probability drops sharply once this exists.
3. **Submit order:** Framework first. Wait 30 days for community review. If accepted, submit AVR Score (Criterion 3 anchors to Framework). DO NOT submit calibration receipt until the Framework + AVR Score are both stable; calibration receipt is the weakest of the three.

## What this risk assessment is and isn't

This is an `[Inferred]` assessment from a single research pass against Wikidata's own help docs. It is NOT a guarantee that submission will succeed/fail. Wikidata patrolling is human + bot, and outcomes vary. The drafts below are pre-staged so submission requires only the operator's keystroke once the wait-gate clears.

## Primary sources consulted

- https://www.wikidata.org/wiki/Wikidata:Notability (tier 1, fetched 2026-05-21)
- https://www.wikidata.org/wiki/Help:Sources (tier 1, fetched 2026-05-21)
- https://www.wikidata.org/wiki/Wikidata:WikiProject_Informatics (tier 1, fetched 2026-05-21)
- https://www.wikidata.org/wiki/Wikidata:WikiProject_Informatics/Software/Properties (tier 1, fetched 2026-05-21)
