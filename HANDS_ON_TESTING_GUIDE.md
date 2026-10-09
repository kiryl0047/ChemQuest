# ChemQuest: Hands-On Testing Guide

Welcome! Thank you for helping us test **ChemQuest** — a gamified, dark-slate-themed educational web application designed to help high school and college chemistry students master multi-step stoichiometry through an interactive, structural workflow.

This guide walks you through the four core modules. **Remember: we are testing the system, not you.** If you get stuck, that is helpful feedback! Feel free to share your thoughts out loud as you click around.

---

## Prerequisites

1. Start the server:
   ```bash
   python manage.py runserver
   ```
2. Open `http://127.0.0.1:8000/` in your browser.
3. Create an account (or log in if you already have one).

---

## Step 1: Register & Enter the Problem Lobby
**Goal:** Verify account creation, login, and the problem selection interface.

1. **Register a new account**
   - Click "Create an account" on the login page.
   - Fill in username, password, and password confirmation.
   - Click **CREATE ACCOUNT**.
   - ✅ *Check:* You are redirected to the Problem Selection Lobby.

2. **Explore the Lobby**
   - Observe the **Synthesis Challenge** banner (top) — it shows your progress toward unlocking the unassisted review.
   - Use the **Filter Ribbon** (ALL TYPES / mol→mol / mol→g / g→mol / g→g) to filter problems by conversion type.
   - ✅ *Check:* Cards hide/show correctly when filtering.
   - Click **Begin Preparation Ledger** on any problem card.
   - ✅ *Check:* You land on the Module 1 Ledger for that problem.

---

## Step 2: Module 1 — Preparation Ledger
**Goal:** Test the predict-before-calculate gate, reaction balancing, molar mass lookup, and the exit reasoning checkpoint.

### 2A — Predict-Before-Calculate Checkpoint
1. Read the strategy question ("In balancing, why is it correct to change only the coefficients...").
2. Select an answer and submit.
3. ✅ *Check:* Wrong answer → hint appears. Correct answer → checkpoint clears, coefficient inputs unlock.

### 2B — Sub-Step 1A: Balance the Equation (Chamber Stabilization)
1. Enter integer coefficients in the **Equation Builder** for each reactant and product.
2. Watch the **Live Atom Conservation HUD** update in real time (left/right atom counts, meter bars, status badges).
3. Click **Verify Chamber**.
4. ✅ *Check:*
   - Balanced → status = "STABILIZED", coefficients lock green, **Conservation Blueprint** explanation appears, Molar Mass section unlocks.
   - Imbalanced → tactical hint appears (progressively more specific per attempt), HUD shows deficits.

### 2C — Sub-Step 1B: Harvest Canned Constants (Molar Mass Lookup)
1. For each compound, use the **Atomic Databank** (full periodic table at bottom) to compute molar mass.
   - Click elements to accumulate into the **Scratchpad** (click an item to remove).
2. Enter the value in the input, click **Verify Molar Masses**.
3. ✅ *Check:*
   - Within scaled tolerance (`0.10 + 0.05 × atom count`, capped at 1.0) → green "✓", locks.
   - Outside tolerance → diagnostic feedback (partial sum detection, missing elements, or coefficient-multiplication warning).
   - Coefficient-multiplication trap → specific warning: *"You multiplied by the balancing coefficient... Molar mass measures 1 mole of the formula alone."*

### 2D — Exit Reasoning Checkpoint (Before Leaving Module 1)
1. After all molar masses verify, the **Reasoning Check** card appears.
2. Answer: "After a reaction is balanced, which statement must be true for every element...?"
3. ✅ *Check:* Correct answer → "Proceed to Module 2 Workspace" button enables.

### 2E — Transition
1. Click **Proceed to Module 2 Workspace** (or **Proceed to Limiting Workspace** for limiting-reagent problems).
2. ✅ *Check:* Redirects to the correct next module.

---

## Step 3: Module 2 — Step-Grid Workspace (Dimensional Analysis)
**Goal:** Test the progressive, node-by-node fractional workspace with flexible chain ordering.

1. **Read the prompt** — note the given quantity, unit, formula, and target.
2. **Conversion type badge** (mol→mol, mol→g, g→mol, g→g) tells you how many fraction cards (nodes) are required.
3. **Fill Step 1:**
   - Numerator value + unit dropdown, Denominator value + unit dropdown.
   - Denominator **must cancel** the previous unit diagonally.
   - Click **✓ Verify Step 1**.
4. ✅ *Check:*
   - Correct → card locks green with **verified-link** style, unit cancellation strikethrough visual appears, next card spawns.
   - Incorrect → card flashes red (`error-link`), tutor console explains *unit mismatch* or *value check failed*, progressive hint after retries.
5. Repeat for all required nodes.
6. ✅ *Check:* Final yield node appears with calculated answer, **Module Actions Bar** shows navigation (Next Part / Limiting Workspace / Lobby).
7. **Navigation:** Use the Part Strip (top) to jump between parts; progress persists server-side.

---

## Step 4: Module 3 — Limiting Reagent Workspace
**Goal:** Test the explicit lane-verification → side-by-side comparison → final deduction flow.

*(Only available on problems marked **LIMITING** in the lobby.)*

1. **Verify Each Lane** (one per reactant track):
   - Fill all fraction cards for the track (same UI as Module 2).
   - Click **Verify Lane** per track.
   - ✅ *Check:* Each lane locks independently; yields display as "COMPUTED YIELD — PART X".

2. **Yield Comparison (Side-by-Side):**
   - After all lanes verified, the **Compare Yields** button enables.
   - Select which track produces the **smaller** primary-product yield.
   - ✅ *Check:* Correct → "Yield comparison confirmed. Proceed to final deduction." Wrong → progressive hints.

3. **Final Deduction:**
   - Enter: Limiting Reagent formula, Theoretical Yield (value), Excess Remaining (per excess reactant).
   - Click **Finalize Deduction**.
   - ✅ *Check:*
     - All three correct → "Chemical synthesis sequence master cleared!", XP awarded, redirect to Lobby.
     - Any wrong → specific message (limiting reagent / yield / excess) + progressive hint ladder.

---

## Step 5: Module 4 — Analytics Dashboard
**Goal:** Verify telemetry-driven diagnostics, trend sparklines, skill breakdowns, and PDF export.

1. Navigate to **Dashboard** (via Lobby header or direct URL `/dashboard/`).
2. **Summary Metrics** (top row):
   - Total Secured Vector Nodes, Global Submission Accuracy, Critical Concept Bottleneck.
   - ✅ *Check:* Numbers reflect your actual session activity.
3. **Dimensional Analysis Mastery Diagnostics** (progress bars):
   - Four conversion types (mol→mol, mol→g, g→mol, g→g) with status badges (Mastered / Developing / Needs Review / Unmapped).
   - ✅ *Check:* Bar colors match tier (teal ≥80%, gold 60–79%, red <60%).
4. **Accuracy Trend — Last 14 Days** (sparklines):
   - One polyline per conversion type.
   - ✅ *Check:* Points appear after you complete problems; dates labeled.
5. **Skill Depth & Chain-Position Diagnostics:**
   - By Chain Depth (single-node vs multi-node) and By Position (first / middle / last node).
   - ✅ *Check:* Scores reflect where you struggled (e.g., middle node of g→g chains).
6. **Strategic Optimization Targets:**
   - Recommended problems based on your trouble spots (or onboarding problems if no history).
   - Click **Launch Remediate Phase** → returns to that problem's Ledger.
7. **Export Report (PDF):**
   - Click **⬇ Export Report (PDF)**.
   - ✅ *Check:* PDF downloads with your username, summary, conversion mastery, skill breakdown, synthesis status, and recommended targets.

---

## Step 6: Synthesis Challenge (Retention Credential)
**Goal:** Test the unassisted, randomized review unlocked after 5 completed problems.

1. Complete ≥5 problems (any mix).
2. Return to Lobby — **Synthesis Challenge** banner shows "Unlocked".
3. Click **Enter Review**.
4. Complete 3 randomized items **without hints**.
5. ✅ *Check:* Score ≥60% → "Credential earned" banner with best score. Score <60% → can retry later.

---

## Step 7: System Wipe / Retry (Optional Stress Test)
**Goal:** Verify the "Retry" button on problem cards fully resets progress.

1. On a problem card with telemetry (shows 🔄), click the **🔄** button.
2. Confirm in the modal: **CONFIRM ERASE**.
3. ✅ *Check:* All localStorage drafts + server telemetry/progress for that problem are deleted; card shows 🔒 (locked/untouched).

---

## Quick Reference: Key URLs

| Page | URL |
|------|-----|
| Login | `/login/` |
| Register | `/register/` |
| Problem Lobby | `/problem_lobby/` |
| Module 1 Ledger | `/ledger/<problem_id>/` |
| Module 2 Workspace | `/workspace/<problem_id>/<part_label>/` |
| Module 3 Limiting | `/limiting/<problem_id>/` |
| Student Dashboard | `/dashboard/` |
| PDF Export | `/dashboard/export_pdf/` |
| Synthesis Challenge | `/synthesis/` |
| Instructor Console (staff only) | `/dashboard/instructor/` |

---

## Feedback Checklist (for Testers)

After completing the walkthrough, please rate/note:

| Area | Smooth? (Y/N) | Confusing? | Bugs/Glitches | Suggestions |
|------|---------------|------------|---------------|-------------|
| Registration/Login | | | | |
| Lobby filtering & cards | | | | |
| Module 1: Checkpoint gate | | | | |
| Module 1: Balancing + HUD | | | | |
| Module 1: Molar mass + scratchpad | | | | |
| Module 1: Exit reasoning gate | | | | |
| Module 2: Node-by-node verify | | | | |
| Module 2: Unit cancellation visual | | | | |
| Module 3: Lane → compare → deduce | | | | |
| Module 4: Dashboard metrics | | | | |
| Module 4: Sparklines & breakdowns | | | | |
| Module 4: PDF export | | | | |
| Synthesis Challenge | | | | |
| Retry/Wipe flow | | | | |
| Mobile/responsive layout | | | | |

---

## Known Constraints (by design)

- **No answer keys in client** — all grading is server-side; expected values never leave the server.
- **localStorage is draft-only** — clearing browser storage cannot spoof gates or lose verified progress.
- **Module 1 gates are sequential** — you cannot skip the checkpoint, balancing, molar masses, or exit reasoning.
- **Module 2 chain order is flexible** — any dimensionally valid unit-cancellation sequence is accepted.
- **Synthesis Challenge is hint-free** — intentionally unassisted to measure retention.

---

Thank you for testing ChemQuest! Your feedback directly shapes the learning experience for chemistry students.