# Model guides

Researched, **cited** buyer's guides for car models, served read-only by the API
(`GET /api/models`, `GET /api/models/{make}/{model}/research`) and rendered in the
frontend "Model guides" tab.

## Layout
```
model_guides/
  TEMPLATE.md            # structure to copy for a new guide
  README.md              # this file
  <make-slug>/<model-slug>.md
  e.g. volkswagen/id-4.md
```
- **Slug rule** (must match `slugify` in `api/routes/models.py`): lowercase, every run
  of non-alphanumeric → `-`, trimmed. `Volkswagen` → `volkswagen`, `ID.4` → `id-4`,
  `ID. Buzz` → `id-buzz`, `Mercedes-Benz` → `mercedes-benz`.
- Each guide starts with a flat `---` front-matter block (`key: value` only — no nested
  YAML) followed by the markdown body. See `TEMPLATE.md`.

## Generating / refreshing a guide (the "agent")
Run in a Claude Code session — uses real research tooling (web search + Firecrawl/Exa
fetch + claim verification), not the live app:

1. Invoke the **`deep-research`** skill with a prompt like:
   > Research **<Make> <Model>** for a **German** used-car buyer. Cover: all variants/trims
   > sold in DE/EU and their specs (usable kWh, WLTP range, kW/PS, years); battery **cell
   > suppliers** by variant/Baujahr/plant; known problems & **KBA Rückrufe** (reference +
   > VW Aktionscode) plus **TÜV-Report (HU)** and **ADAC Pannenstatistik** findings by
   > year; and the **best Baujahr/variant to buy** (fewest issues) with what to check and
   > typical used **€** prices. Cite every claim with a source link.

   **SCOPE (hard rule):** focus on **Germany only** (Luxembourg/France acceptable) —
   **€ only, German/EU standards**. Prefer KBA, ADAC, TÜV, goingelectric.de,
   motor-talk.de, autobild.de (+ ev-database.org, batterydesign.net). Do **not** include
   US/UK or other-market data, NHTSA-only framing, $/£ prices, or US trim names. If only
   a non-DE source exists for a fact, note it as such or omit it.
2. Fold the cited output into `TEMPLATE.md`'s sections and save as
   `<make-slug>/<model-slug>.md`. Fill front-matter (`updated`, `sources`).
3. Commit and deploy (guides ride along in the image).

## ⚠️ Re-run rule: ENHANCE, NEVER DELETE
Re-running for an **existing** guide must only **add or refine** — never remove or
shorten prior content:
- Pass the **current file** to deep-research as the base and instruct it to *merge*:
  add new variants/issues/suppliers/sources, and refine an existing entry only by
  *adding* detail or appending a **dated correction with citation**. Do **not** delete,
  replace, or trim existing entries.
- Bump `updated` and increment `revisions` in the front-matter.
- Append one dated line to **`## Revision log`** summarizing what was added. Never edit
  past log lines.
- Git history is the hard backstop: every prior version stays recoverable. Destructive
  rewrites of an existing guide are not allowed.
