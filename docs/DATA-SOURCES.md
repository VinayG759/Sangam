# Data task brief

**This is the whole job.** You own three CSV files per country. Nothing else in
this repo is yours to change, and nothing you do here can break anyone's code.

Read this once, then work top to bottom. Ask before guessing.

---

## What Sangam does, in four lines

Citizens send voice notes and messages about what their area needs — no water,
broken road, no doctor. Sangam groups them by place and need, then lays that
demand next to two government datasets: **how badly served is this place already**,
and **has money already been allocated here.**

That comparison produces the finding: either *"nobody funded this"* or
*"money went in and nothing came out."*

**Your files are the second half of that comparison.** Without them, Sangam is
just a complaint collector.

---

## The one rule

> **Every number must come from a published source, and you must record where.**

Never estimate, never fill a gap with a plausible figure, never carry a number
over from a different year without saying so. A missing row is fine. An invented
row is the only thing that can genuinely damage this project — a judge who finds
one stops trusting everything else.

If you can't find something, write it in the **Known gaps** section of
`packs/india/SOURCES.md`. Gaps are useful information, not failure.

---

## File 1 — `packs/india/admin_units.csv`

Every administrative area in the country, and every name people use for it.

```
unit_id,country_code,level,name,name_variants,parent_unit_id,external_code,population,source_name,source_url
```

| Column | What goes in it |
|--------|-----------------|
| `unit_id` | Our own ID. Make it readable and stable: `IN`, `IN-KA`, `IN-KA-KOLAR`, `IN-KA-KOLAR-MALUR` |
| `country_code` | Always `IN` in this file |
| `level` | `0` country · `1` state · `2` district · `3` block |
| `name` | The official English name |
| `name_variants` | **The important one.** Every other spelling people actually use, separated by `\|` |
| `parent_unit_id` | The `unit_id` of the row above it. Blank for the country row |
| `external_code` | The government's own code (LGD code for India) |
| `population` | Most recent published figure |
| `source_name` / `source_url` | Where population came from |

**Worked example:**

```
IN,IN,0,India,,,,1428600000,Census projection,https://...
IN-KA,IN,1,Karnataka,Karnātaka|ಕರ್ನಾಟಕ,IN,29,61095297,Census 2011,https://...
IN-KA-KOLAR,IN,2,Kolar,Kolara|ಕೋಲಾರ|कोलार,IN-KA,2916,1536401,Census 2011,https://...
IN-KA-KOLAR-MALUR,IN,3,Malur,Maluru|ಮಾಲೂರು,IN-KA-KOLAR,291604,213000,Census 2011,https://...
```

### Why `name_variants` matters more than it looks

A woman says *"ಕೋಲಾರ"* in a voice note. If that spelling isn't in this column,
Sangam cannot work out where she is, and her request is dropped from the entire
analysis. **Every variant you add is requests rescued.**

Include: English spellings, common misspellings, the local-script name, the Hindi
name, and any older name still in use (Bangalore/Bengaluru, Mysore/Mysuru).

### How much to do

| Priority | Scope |
|----------|-------|
| **1 — do first** | All ~780 Indian districts (level 2) |
| **2** | All blocks in **Karnataka only** (level 3, ~230) |
| **3 — only if time** | Anything else |

Do **not** attempt blocks for all of India. That's a week of work and we don't need it.

---

## File 2 — `packs/india/indicators.csv`

How well served each place already is. **One row per place, per statistic.**

```
unit_id,indicator_key,value,unit,period,source_name,source_url
```

**Worked example:**

```
IN-KA-KOLAR,water.piped_household_pct,31.4,percent,2024,Jal Jeevan Mission,https://...
IN-KA-KOLAR,sanitation.household_toilet_pct,88.0,percent,2023,SBM,https://...
IN-KA-TUMKUR,water.piped_household_pct,67.2,percent,2024,Jal Jeevan Mission,https://...
```

Note the shape: Kolar appears **twice**, once per statistic. That's correct and
deliberate — it's what lets Brazil add statistics India doesn't have without
anyone changing the file format.

### The exact `indicator_key` values to use

Use these strings precisely. Anything else won't be picked up.

| `indicator_key` | Meaning | Priority |
|-----------------|---------|----------|
| `water.piped_household_pct` | % households with piped water | **1 — the one that matters most** |
| `sanitation.household_toilet_pct` | % households with a toilet | 2 |
| `road.all_weather_connectivity_pct` | % habitations with all-weather road | 2 |
| `power.household_electrified_pct` | % households electrified | 3 |
| `health.phc_per_100k` | primary health centres per 100,000 people | 3 |
| `education.school_infra_index` | any published school-infrastructure score | 3 |
| `demography.below_poverty_pct` | % below poverty line | 2 |

**Population does not go here** — it lives in `admin_units.csv`.

### Where to start looking

- **Jal Jeevan Mission** — `ejalshakti.gov.in` — district-wise piped water coverage. **Start here.**
- **data.gov.in** — the national open data portal; search by district
- **Census of India** — population, households, amenities
- **PMGSY** — `pmgsy.nic.in` — rural road connectivity
- **Swachh Bharat Mission** — sanitation coverage

---

## File 3 — `packs/india/sanctioned_projects.csv` ⚠️ the critical one

What the government has already committed money to. **This file is the
difference between Sangam and every other hackathon project.** Do it third,
but tell Vinay how it's going by **18 Aug** — if this data can't be found, the
whole approach changes and we need to know early.

```
project_id,unit_id,sector,title,amount,currency,status,sanctioned_date,completion_date,source_name,source_url
```

| Column | Notes |
|--------|-------|
| `sector` | Must match a need key: `water` `road` `electricity` `health` `education` `sanitation` |
| `amount` | Number only. No commas, no "crore" — write `40000000` not `4 crore` |
| `currency` | `INR` |
| `status` | Exactly one of: `sanctioned` `in_progress` `completed` `stalled` |
| `completion_date` | Blank unless actually completed |

**Worked example:**

```
JJM-KA-0142,IN-KA-KOLAR,water,Kolar rural piped water scheme,40000000,INR,in_progress,2024-03-15,,Jal Jeevan Mission,https://...
JJM-KA-0155,IN-KA-TUMKUR,water,Tumkur multi-village scheme,72000000,INR,completed,2022-06-01,2024-01-20,Jal Jeevan Mission,https://...
```

### About `status` — read this carefully

`status` is what lets Sangam tell the difference between *"nobody funded this"*
and *"money went in and nothing came out."* Getting it right matters more than
getting the amount exactly right.

- If a source says a scheme is sanctioned but gives no progress → `sanctioned`
- If it shows work underway → `in_progress`
- If it shows work finished → `completed`
- Only use `stalled` if a source **explicitly** says so. **Never infer it** from
  an old date — that's exactly the kind of guess that would get us caught.

### Where to look

- **Jal Jeevan Mission dashboard** — scheme-wise sanctioned works
- **PFMS dashboard** — `pfmsdashboard.gov.in` — published aggregates only
- **data.gov.in** — search "expenditure", "sanctioned", "scheme"
- **Karnataka state budget documents** — district-wise allocations

⚠️ **There is no open PFMS API.** Don't waste time hunting for one — work from
published dashboards, downloads and budget documents.

---

## File 4 — `packs/india/SOURCES.md`

Fill in one block per dataset as you go, not at the end. Also keep the coverage
table current — it's the honest picture of what we actually have, and it goes
straight into the pitch.

---

## Brazil

Once India is done, `packs/brazil/` is the same three files with the same columns.
`unit_id` becomes `BR`, `BR-BA`, `BR-BA-SALVADOR`. Levels are country → estado →
município (so only 0, 1, 2 — no level 3).

Start with **SNIS** (`snis.gov.br`) for municipal water and sanitation, and
**IBGE** for population and boundaries. Thin but real beats thick and invented.

---

## How you know you're done

- [ ] All ~780 Indian districts in `admin_units.csv`, each with real name variants
- [ ] Karnataka blocks added
- [ ] `water.piped_household_pct` filled for as many districts as published
- [ ] At least two more indicator types filled
- [ ] `sanctioned_projects.csv` has real water projects for Karnataka with honest `status`
- [ ] `SOURCES.md` has a block for every dataset and an up-to-date coverage table
- [ ] Known gaps written down

---

## Things that will save you time

**Don't hand-type anything.** Download the CSV or Excel, then transform it. If a
site only has an HTML table, copy it into a spreadsheet.

**Get one district completely right first.** Do Kolar end to end across all three
files, show it to Vinay, and only then scale up. Fixing a format mistake across
780 rows is miserable.

**Blank beats wrong.** An empty cell is handled gracefully by the engine. A wrong
number is not.

**Commit often.** Small commits, push to `main`. You can't collide with anyone —
you're the only person touching `packs/`.

**Ask early.** Two minutes of asking beats four hours in the wrong format.
