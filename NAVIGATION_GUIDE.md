# ChemQuest Problem Lobby Navigation Guide

## Quick Access

| Action | Method |
|--------|--------|
| **Enter the lobby** | Click "CHEMQUEST //" in header, or visit `/problem_lobby/` directly |
| **After login/registration** | Automatically redirected to lobby |
| **Return from any module** | Use lobby links in module headers/footers |

## Finding a Problem

### 1. **Browse all problems**
- Default view shows all available problems
- Each card displays: title, conversion types, status badge (COMPLETE/IN PROGRESS/LOCKED)

### 2. **Filter by conversion type**
Use the ribbon below the header:

| Tab | Shows |
|-----|-------|
| **ALL TYPES** | Every problem in the database |
| **mol → mol** | 1-node conversions (molecule → molecule) |
| **mol → g** | 2-node conversions (molecule → grams) |
| **g → mol** | 2-node conversions (grams → molecule) |
| **g → g** | 3-node conversions (grams → grams) |

- Click any tab to filter the grid
- Counter badges update dynamically to show how many problems match

### 3. **Identify problem status**
Each problem card shows:

| Indicator | Meaning |
|-----------|---------|
| **LIMITING** badge (red) | Limiting reagent problem (Module 3 available) |
| **✓ COMPLETE** (green) | Problem previously finished |
| **🔄** (default color) | You've started this problem (has telemetry) - can **Retry** |
| **🔒** (gray, disabled) | Untouched problem - not yet started |

### 4. **Start a problem**
- Click **"Begin Preparation Ledger →"** button on any problem card
- This opens: `/ledger/<problem_id>/` (Module 1 Preparation Ledger)

## Progress & Status

### **Retry (🔄 button)**
- Appears on problems you've started (has telemetry data)
- Opens a confirmation modal: "SYSTEM ALERT: RESET SEQUENCE"
- **WARNING**: Deletes all telemetry, progress flags, and locked constants
- After confirmation: redirects to `/problem/reset/<problem_id>/` and returns lobby with reset status

### **Synthesis Challenge**
- **Unlock requirement**: Complete ≥5 problems (any mix of conversion types)
- **When unlocked**: Banner at top of lobby shows "Unlocked — randomized unassisted review available"
- **Enter review**: Click the "Enter Review →" button in the Synthesis banner
- **Credential**: Score ≥60% earns "Credential earned" badge with best percentage

### **Dashboard access**
- Click the dashboard link in the lobby header, or visit `/dashboard/`
- Shows your analytics, accuracy trends, and mastery breakdowns

## Navigation Path Summary

```
Login/Register
    ↓
Problem Lobby (/problem_lobby/)
    │
    ├── Filter by conversion type (ribbon tabs)
    │
    ├── Select problem card
    │   ↓
    │   Begin Preparation Ledger
    │   ↓
    │   Module 1: Balancing → Molar Masses → Exit Reasoning
    │   ↓ (if ≥80% accuracy gate passed)
    │   Module 2: Step-Grid Workspace (dimensional analysis)
    │   ↓
    │   Module 3: Limiting Reagent (if limiting problem)
    │   ↓
    │   Return to lobby (progress saved)
    │
    ├── Synthesis Challenge banner
    │   (unlocks after ≥5 completed problems)
    │   ↓ Enter Review
    │
    └── Dashboard link
           ↓
           Module 4: Analytics
```

## Troubleshooting Common Issues

| Problem | Solution |
|---------|----------|
| "I don't know where to start" | The lobby is your starting point - look for problem cards with "Begin Preparation Ledger" button |
| "I filtered but no problems show" | Try "ALL TYPES" to see everything, or check if problems exist in the database |
| "I want to restart a problem" | Use the 🔄 Retry button on your problem card (opens confirmation modal) |
| "Synthesis challenge isn't appearing" | You need to complete 5 problems total first |
| "Progress seems lost" | Progress is server-based - logging out/in preserves it. Only clearing browser localStorage removes draft data. |
| "I can't find my problem" | Use the filter ribbon to narrow by conversion type, or scroll through all problems |

## Key URLs Reference

| Page | URL |
|------|-----|
| Problem Lobby | `/problem_lobby/` |
| Module 1 Ledger | `/ledger/<problem_id>/` |
| Module 2 Workspace | `/workspace/<problem_id>/<part_label>/` |
| Module 3 Limiting | `/limiting/<problem_id>/` |
| Student Dashboard | `/dashboard/` |
| Synthesis Challenge | `/synthesis/` |
| Problem Reset/Reset | `/problem/reset/<problem_id>/` |

---

*This guide is based on ChemQuest v1.0. For the latest version, check the project README.*