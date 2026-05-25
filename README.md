# ChemQuest // Procedural Alchemical Stoichiometry Engine

ChemQuest is a gamified, dark-slate-themed educational web application designed to help high school and college chemistry students master multi-step stoichiometry through an interactive, structural workflow. 

Instead of traditional static multiple-choice questions, ChemQuest visualizes learning as a **Tower of Alchemical Mastery Ascent**. The system decomposes multi-part chemical problems into an overarching **Preparation Ledger (Phase 1)** and a dynamic, modular **Step-Grid Fractional Workspace (Phase 2)** where students drag, drop, and link dimensional analysis conversion cards to balance systemic chemical parameters.

---

## 🚀 Key Architectural Features

* **Tower Progression Core Dashboard:** Visualizes academic curriculum as a vertical tower ascent map. Sub-questions (e.g., parts a, b, c, d of a hydrocarbon combustion array) are parsed out dynamically as distinct tactical "Sector Quests."
* **The Preparation Ledger (Phase 1):** Forces students to stabilize reaction environments by balancing the core chemical equation and harvesting molecular weights from an atomic databank before calculation lanes unlock.
* **Dynamic Step-Grid Workspace (Phase 2):** A smart dimensional analysis canvas. It reads the specific conversion strategy flags (`mass_to_mass`, `mole_to_mass`, `mass_to_mole`) straight from a relational SQLite database and automatically structures, expands, or shrinks the fractional card layouts in real-time.
* **Procedural Math Parser Engine:** Powered by a pure Python utility layer that reads raw molecular syntax mappings (e.g., `C3H8:1,O2:5|CO2:3,H2O:4`), computes combined molar weights on the fly, and generates precise cancellation targets programmatically.

---

## 🛠️ Tech Stack

* **Backend Framework:** Django 5.x (Python 3.11+)
* **Database Layer:** SQLite (Relational Structure)
* **Frontend Design Architecture:** Semantic HTML5, CSS3 Custom Properties (Cyber Teal/Constant Gold Neon Palette), Vanilla JavaScript ES6 (Asynchronous Fetch Operations)

---
