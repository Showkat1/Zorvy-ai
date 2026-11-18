# 08 — Seed Readiness

**Status:** Working document · 18 Nov 2026
**Purpose:** State exactly what an investor can verify today, what is still missing, and what
must be true before a seed round is credible.

This document is deliberately unflattering where the evidence is thin. A seed investor will
find the gaps anyway; finding them stated with a plan is a signal, not a weakness.

---

## 1. The honest position

Zorvy is **technically credible and commercially unproven**.

| Question an investor asks | Answer today | Verdict |
|---|---|---|
| Does the product exist and work? | Yes — FastAPI + Next.js application, 8-stage pipeline, 51 backend tests, CI, Docker | **Strong** |
| Is the intelligence defensible? | Deterministic, explanation-first engine with an India-first brand registry, no LLM required | **Strong for a seed-stage story** |
| Can accuracy be verified? | Deterministic benchmark harness and a generated report over 28 labelled cases, 8 of them India-focused | **Started, not sufficient** |
| Is the IP protected? | Proprietary licence, no copyleft in shipped code, security disclosure policy | **Partial** |
| Is anyone paying? | No | **Missing** |
| Is there a design partner? | No | **Missing** |
| Is the company clean? | Repository hygiene is good; corporate, cap-table and IP-assignment work is founder-only and unstarted | **Missing** |

The gap between "good product" and "fundable company" is not more code. It is **proof of demand
and clean ownership**. Everything in §6 is founder work, not engineering work.

---

## 2. What this pass added to the evidence pack

| Artefact | Path | What it proves |
|---|---|---|
| Benchmark harness | `backend/scripts/benchmark.py` | Accuracy, confusion, signal detection and latency are reproducible on any machine |
| Benchmark report | [`BENCHMARK-REPORT.md`](BENCHMARK-REPORT.md) | The current numbers, the method, and the limits, in one page |
| Machine-readable results | `docs/zorvy/benchmark-results.json` | Per-case verdicts for a technical reviewer to inspect |
| Test suite | `backend/tests/` | 51 tests covering auth, isolation, extraction, Indian formats, URL intelligence, risk gating and the evaluation set |
| CI | `.github/workflows/ci.yml` | Lint, tests, frontend typecheck/build and Docker builds on every push |
| Proprietary licence | [`LICENSE`](../../LICENSE) | The engine is not forkable; no implied evaluation rights |
| Licence hygiene | `backend/pyproject.toml` | The AGPL PDF library (PyMuPDF) was replaced with BSD-licensed `pypdf`; shipping runtime dependencies are permissive |
| Security policy | [`SECURITY.md`](../../SECURITY.md) | A disclosure channel, response targets and scope — a question every security reviewer asks |
| India-first registry | `backend/app/services/brand_registry.py` | 121 brands ordered India (57), Pakistan (21), global (43), with boundary-aware matching |
| URL hardening | `backend/app/services/url_intelligence.py` | Scheme rejection, correct IP handling, Indian second-level suffixes |

Reproduce the headline evidence with:

```bash
cd backend
uv run pytest -q
uv run ruff check app tests scripts
uv run python -m scripts.benchmark
```

---

## 3. Seed-readiness scorecard

Scoring is intentionally harsh. **Green** means an investor can verify it without taking a
meeting. **Amber** means it exists but would not survive technical diligence. **Red** means it
does not exist.

| Dimension | Status | Evidence | What closes the gap |
|---|---|---|---|
| Problem clarity | 🟢 | Strategy set [`01`](01-MASTER-THESIS.md)–[`07`](07-RISK-REGISTER.md) | — |
| Product completeness | 🟢 | Working app, 8 persisted stages, audit trail | — |
| Engineering quality | 🟢 | 51 tests, ruff clean, CI, Docker, typed schemas | Add coverage reporting |
| Technical differentiation | 🟢 | Deterministic explainable engine, claim verification, India-first brand registry | Publish the ruleset versioning approach |
| Accuracy evidence | 🟡 | 28-case benchmark, 100% level accuracy, 87.9% signal recall, F1 0.718 | External labelled set, inter-annotator agreement, per-category precision/recall on real reports |
| India-first depth | 🟡 | 57 Indian brands, Indian suffixes, INR/`₹`, `+91` phones, Indian institution extraction, 8 India-focused cases | Indian-language cases (Hindi, Marathi, Tamil, Bengali), larger Indian institution corpus, regional-language registry |
| Security posture | 🟡 | Rotation, rate limiting, isolation, disclosure policy | VAPT report, dependency scanning, secret scanning, threat model |
| Legal hygiene | 🟡 | Proprietary licence; shipping runtime dependencies are permissive (AGPL PDF library replaced) | Trademark search/filing, IP assignment, privacy policy, DPA template; drop the AGPL `legacy/streamlit` tree before sharing source |
| Commercial proof | 🔴 | None | 1–2 paid pilots or signed LOIs |
| Distribution | 🔴 | None | Consumer wedge live, first 1,000 checks |
| Team | ⚪ | Not assessed here | Founder-only narrative |
| Financial plan | 🟡 | [`05`](05-ECONOMICS-AND-GTM.md) | Bottom-up model reconciled to actual costs |

**Read:** the product and engineering columns are seed-grade. The evidence, legal and commercial
columns are not yet. A seed round raised on the current pack would be a bet on the founder, not
on traction — which is a legitimate pre-seed conversation, not a seed one.

---

## 4. The benchmark, stated correctly

The current harness reports **100% risk-level accuracy on 28 hand-written cases**, with zero
dangerous misses and zero false alarms. That number is real but narrow:

- **It is not field accuracy.** No real customer traffic, no adversarial distribution, no
  temporal split.
- **The labels are the author's own.** There is no second annotator and no disagreement analysis.
- **The corpus is mixed, not India-complete.** 20 cases are Pakistan-flavoured (PKR, CNIC, HBL)
  and 8 are India-focused (UPI, Aadhaar, HDFC/SBI/PhonePe, `₹`). There are no Indian-language
  cases yet, and 8 cases cannot substantiate an India-first accuracy claim on their own.
- **Signal recall is 87.9% and signal precision is 60.7% (F1 0.718), not 100%.** The engine
  over-reports some signals and still misses implicit ones (`impersonation`,
  `artificial_urgency`). Verdict bands happen to absorb those misses; a stricter evaluation
  would not.

The defensible claim is:

> On a deterministic 28-case labelled suite — 20 legacy South Asian cases and 8 India-focused
> cases — the engine reproduces every expected verdict band, with an in-process p95 of a few
> milliseconds and no LLM or network dependency. Signal-level recall is 87.9% at 60.7%
> precision.

That is a statement about **specification conformance**, not about the world.

What makes the number credible to an investor is not a bigger claim. It is a **held-out set
labelled by someone other than the author**, plus a per-category precision/recall table on real
reports with an explicit error taxonomy. Add that before quoting accuracy in a deck.

---

## 5. First-meeting demo (10 minutes)

Aim to show the audit trail, not the landing page. Everything below runs on the local stack with
no API key.

| Minute | Do | Why it lands |
|---|---|---|
| 0–1 | One-sentence framing: "an auditable verdict on a suspicious message, in under a second" | Sets the category |
| 1–3 | `make up`, seed the demo workspace, open `http://localhost:3000` | Shows a real product, not slides |
| 3–5 | Submit an Indian phishing message: a fake `paytm-kyc-verify` link, an OTP request and an urgency line | Shows India-first detection |
| 5–7 | Walk the 8 stages, then the evidence panel: URL flags, brand mismatch, extracted money/phone/requests | Shows the engine, not a black box |
| 7–8 | Show the written justification and the bounded risk band | Shows explainability an auditor can read |
| 8–9 | Open `BENCHMARK-REPORT.md` and the JSON; run the benchmark live | Shows verifiable evidence |
| 9–10 | State the ask and the next milestone: one paid pilot | Ends on a falsifiable commitment |

Have a benign message ready (a real bank statement notice) to show the engine is not a
scam-label machine. The false-positive story is more convincing than the true-positive one.

---

## 6. Founder-only gaps

These cannot be closed by another commit, and each one is a standard diligence request.

| # | Gap | Why it blocks | First action |
|---|---|---|---|
| 1 | Corporate entity | Investors invest in a company, not a repository | Incorporate (India Pvt Ltd) or confirm the existing entity |
| 2 | Cap table and ESOP | Ownership must be unambiguous | Clean, fully diluted sheet with vesting |
| 3 | IP assignment | Contributor code without assignment is a diligence fail | Assign from every founder and contractor, including past work |
| 4 | Trademark | A coined name is easier to protect, but it is unregistered | Search, then file "Zorvy" in India (classes 9/42) and secure the domains |
| 5 | Privacy policy and DPA | Fraud reports contain personal data | DPDP-aligned policy, retention schedule, sub-processor list |
| 6 | Penetration test | Banks and investors ask for a VAPT report | Scope the API, auth and upload paths |
| 7 | Design partners | No amount of code substitutes for a buyer | 10 conversations, 2 LOIs, 1 paid pilot |
| 8 | Financial model | A top-down market slide is discounted | Bottom-up: price × accounts × cost to serve, reconciled to actuals |
| 9 | Data room | Diligence must not stall | Assemble the index in [`06`](06-INVESTOR-AND-ACQUISITION-READINESS.md) §3 |
| 10 | References | Buyers and investors call customers | Two accounts willing to take a call |

Until items 1–4 are done, **do not represent the company as investment-ready**. The product is;
the vehicle is not.

---

## 7. What not to claim

| Do not say | Say instead |
|---|---|
| "100% accurate" | "Reproduces every expected verdict on a 28-case labelled suite; field accuracy is not yet measured" |
| "Detects all Indian fraud" | "Covers 57 Indian brands and Indian domain suffixes; language and institution coverage is expanding" |
| "AI-powered" as the headline | "Deterministic, explainable engine that works without an LLM" — that is the differentiator for regulated buyers |
| "Bank-grade security" | "Session rotation, rate limiting, tenant isolation and a disclosure policy; VAPT pending" |
| "₹X Cr market" without a bottom-up path | "N target institutions × contract value, with the first two named in the pipeline" |
| "No false positives" | "Zero false alarms on the current benign set; production precision will be measured with design partners" |

The pattern: every claim should name its **evidence** and its **boundary**. That is also the
product's own design principle, so the pitch and the engine tell the same story.

---

## 8. Next 90 days of evidence

| Window | Milestone | Evidence produced |
|---|---|---|
| Days 1–30 | India-first labelled set (60+ cases), second annotator, held-out split | Benchmark report v2 with inter-annotator agreement and per-category precision/recall |
| Days 1–30 | Trademark search, entity confirmation, IP assignment drafts | Legal pack started |
| Days 31–60 | Consumer wedge live; 1,000 checks | Funnel data: checks, repeat use, share rate |
| Days 31–60 | 10 institutional conversations; 2 LOIs | Pipeline evidence, objection log |
| Days 61–90 | First paid pilot signed; VAPT booked | Revenue evidence, security evidence |

A seed round is credible when **at least one paid pilot and two LOIs exist**, the benchmark has a
held-out split, and items 1–4 of §6 are complete. Until then the right conversation is pre-seed
or angel, and the right ask is enough capital to reach that milestone — not a priced round on
promise.

---

## 9. How to use this pack

| Reader | Read |
|---|---|
| Investor, first call | This document, then [`BENCHMARK-REPORT.md`](BENCHMARK-REPORT.md) |
| Investor, deep dive | [`01`](01-MASTER-THESIS.md), [`02`](02-MARKET-AND-COMPETITION.md), [`05`](05-ECONOMICS-AND-GTM.md), [`06`](06-INVESTOR-AND-ACQUISITION-READINESS.md) |
| Technical diligence | [`03`](03-PRODUCT-AND-ARCHITECTURE.md), the repository, `make test`, `make benchmark` |
| Security diligence | [`SECURITY.md`](../../SECURITY.md), [`07`](07-RISK-REGISTER.md) |
| Founder, weekly | §6 and §8 — the only lists that matter until the round closes |

The strategy documents describe an 18–24 month path. This document describes the **next
milestone**, which is the only one that should be in a seed deck.
