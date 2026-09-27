# Contributing to Sangam

## Adding a country (or a state)

Adding a country adds **files, not code**. Create `backend/packs/<name>/` with:

| File | Contents |
|---|---|
| `pack.yaml` | Country code, currency, languages, admin level names, which statistic measures each need, scoring weights, thresholds, privacy floor, place-naming words. Copy `packs/india/pack.yaml` and edit. |
| `need_taxonomy.yaml` | The needs citizens can report, with labels in local languages. |
| `admin_units.csv` | Every place: `unit_id, country_code, level, name, name_variants, parent_unit_id, external_code, population, source_name, source_url` |
| `indicators.csv` | Statistics, one row per place per statistic: `unit_id, indicator_key, value, unit, period, source_name, source_url` |
| `sanctioned_projects.csv` | Public money committed: `project_id, unit_id, sector, title, amount, currency, status, sanctioned_date, completion_date, source_name, source_url` |
| `admin_centroids.csv` *(optional)* | `external_code, centroid_lat, centroid_lon` for the map and GPS matching |

Then:

```bash
cd backend
python -m app.features.packs validate <name>   # lists every problem, or says "valid"
python -m app.features.packs load <name>       # safe to run repeatedly
```

Set `ACTIVE_COUNTRY_PACK=<name>` to serve it.

### The one rule for data

**Every number comes from a published source, and the source is recorded in the row.** Never estimate,
never fill a gap with a plausible figure, never carry a number across years silently. A missing row is
fine — Sangam drops that term from the score and says so. An invented row is the only thing that can
genuinely damage the project. Blank beats wrong.

- `name_variants` (separated by `|`) should include local-script names, common misspellings and old names.
  Every variant rescues reports the place matcher would otherwise miss.
- `amount` is a plain number in base units (`40000000`, not "4 crore").
- `status` is one of `planned | sanctioned | in_progress | completed | stalled`. Use `stalled` only when a
  source explicitly says so — never infer it from an old date.
- Don't hand-type data: download and transform with a script kept in `packs/<name>/build/`.

## Adding a feature

1. Backend: create `backend/app/features/<name>/` with `router.py` (and `service.py` if needed), then add
   one line to `backend/app/registry.py`.
2. New columns or tables: `alembic revision --autogenerate -m "..."`, review the file, commit it. Never
   change the schema any other way — a test fails if models and migrations disagree.
3. Frontend: create `frontend/src/features/<name>/Page.tsx`, add one line to `frontend/src/routes.tsx`
   and a sidebar entry in `frontend/src/app/Layout.tsx`.
4. A feature may import from `core/` and `models`, never from another feature (enforced by
   `import-linter` in the test suite). Features share data through tables.
5. Add tests. Every bug fix starts with a test that fails.
