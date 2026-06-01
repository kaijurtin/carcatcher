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
   > Research **<Make> <Model>** for a German used-car buyer. Cover: all variants/trims
   > and their specs (battery usable-kWh, range, power, years); battery **cell
   > suppliers** by variant/model-year/plant; known problems & recalls (KBA, NHTSA,
   > TÜV/ADAC defect rates) by year; and the **best model-year/variant to buy** (fewest
   > issues) with what to check. Cite every claim with a source link.
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
