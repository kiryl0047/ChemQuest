# ChemQuest // Procedural Alchemical Stoichiometry Engine

ChemQuest is a gamified, dark-slate-themed educational web application designed to help high school and college chemistry students master multi-step stoichiometry through an interactive, structural workflow.

Instead of traditional static multiple-choice questions, ChemQuest decomposes multi-part chemical problems into four modules: a **Preparation Ledger (Module 1)**, a dynamic **Step-Grid Fractional Workspace (Module 2)**, a **Limiting Reagent Workspace (Module 3)**, and a **Telemetry Analytics Dashboard (Module 4)**.

> **Architecture note:** This codebase is the source of truth. Earlier planning documents described a Supabase/PostgreSQL SPA target; the shipped implementation is server-rendered Django on SQLite. Supabase/PostgreSQL remains a *possible future migration*, not the current system. Do not plan features against the old stack.

---

## Modules

### Module 1 — Preparation Ledger
1. **Predict-before-calculate checkpoint:** a strategy question must be answered before coefficient inputs unlock.
2. **Sub-step 1A (Balancing):** server-verified with progressive attempt-based hints.
3. **Sub-step 1B (Molar masses):** verified against the `Substance` registry with a tolerance that scales with formula complexity (`0.10 + 0.05 × atom count`, capped at 1.0) — no flat ±0.5 forgiveness.
4. **Held-out retrieval check:** before progressing, students must recall one previously locked molar mass with the databank suspended.
5. **≥80% accuracy gate:** Module 1 accuracy across 1A+1B must reach 80% for the transition to unlock; falling short directs students to the lobby's Retry (full reset).
6. **Quick-Harvest** auto-fill is a post-completion review tool only — it cannot bypass live computation. Mastery counter is server-tracked.

### Module 2 — Step-Grid Workspace
- Expected node values never leave the server; clients submit guesses and receive per-node `UNITS ✓/✗` + `VALUE ✓/✗` feedback separately.
- Chain audits accept any ordering that is dimensionally valid (units must cancel from the given unit to the target unit); there is no artificial single canonical order.
- Rolling 75% accuracy step-lock: below-threshold accuracy triggers a server-enforced cooldown with mandatory review.
- **Synthesis Challenge:** after completing 5 problems, a randomized unassisted review unlocks; ≥60% earns the retention credential.

### Module 3 — Limiting Reagent Workspace
- Sequential lane verification, then an explicit side-by-side yield comparison action, then the final deduction.
- The true limiting reagent is derived explicitly per primary-product track; excess-reagent remaining is a required final calculation.
- Progressive hint ladder after repeated failed deductions.

### Module 4 — Analytics
- Student dashboard is strictly scoped to the requesting user's telemetry.
- Accuracy trends over time per conversion type, chain-depth and chain-position diagnostics.
- PDF report export.
- Instructor console (`is_staff` only): cohort heatmap of students × sub-skills plus roster metrics.

---

## Progress & State Model

All gating state lives server-side:

| Model | Purpose |
|---|---|
| `ProblemProgress` | Per-user flags: balancing, molar masses, checkpoint, retrieval, accuracy gate, comparison, deduction, synthesis |
| `PartProgress` | Per-part lane clears and verified chains (authoritative replay data) |
| `StudentTelemetryLog` | Per-user, per-sub-step attempts (drives hints, locks, analytics) |
| `SynthesisAttempt` | Unassisted-review results |

`localStorage` holds **only non-authoritative drafts** (unverified typing), so clearing browser storage can no longer lose progress or spoof gates.

## Tech Stack

* **Backend:** Django (server-rendered templates)
* **Database:** SQLite
* **PDF export:** ReportLab
* **Frontend:** Semantic HTML5, CSS3 custom properties, Vanilla JS ES6 (async fetch)

## Getting Started

```bash
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_problems
python manage.py createsuperuser   # optional: grants /dashboard/instructor/
python manage.py runserver
```

## Tests

```bash
python manage.py test core_app
```

Covers gate math, scaled tolerances, flexible-order chain grading, step-lock, limiting/excess verification, dashboard scoping, PDF export, and role separation.
