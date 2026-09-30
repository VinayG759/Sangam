# Sangam — The Plan, in Plain Words

**Written:** 27 Sep 2026 · **For:** Vinay
**The detailed technical version:** [implementation-plan.md](implementation-plan.md).
Phase numbers match exactly, so you can read a phase here first, then open the same
phase there for the exact steps.

---

## Part 1 — What we are building, in one minute

Think of a town where people keep complaining that there's no water. Separately, in a
government office, there's a spreadsheet saying "₹4 crore was given for a water pipeline
in that town, two years ago."

Nobody ever puts those two things side by side. The complaints sit in one system, the
money sits in another.

**Sangam puts them side by side.** That's the whole idea. We call it **"the join."**

When you put them together, you can say things nobody else can:

| What we see | What it means | What the government should do |
|-------------|---------------|-------------------------------|
| Lots of complaints, **no money** given | **Unserved gap** — real need, nobody funded it | Give money here |
| Lots of complaints, **money already given** | **Stalled allocation** — money went in, nothing came out | Send an inspector |
| Few complaints, money given | **Well served** — it worked | Nothing to do |

Everything else we built — WhatsApp, voice notes, many languages, the map — exists to
feed this comparison. Other teams will have chatbots and maps. **Only the join is ours.**

One line for the pitch: *"Complaint systems pass complaints along. Sangam checks whether
the money went to the right place."*

---

## Part 2 — What's decided: deadline and BRICS

You confirmed two things on 27 Sep:

1. **The deadline is 30 September** — 3 days away. So before submitting we do **only
   Phase 0 (fix the live system) and Phase 1 (video, slides, description)**. Everything else
   is for the final round in October.
2. **The brief says "across BRICS nations."** So judges will ask: "Does this work
   outside India?"

**Why we don't build Brazil before 30 Sep.** Adding Brazil properly means finding *real*
Brazilian government data — regions, water coverage, spending — with a source for every
number. That's days of research, and it would have to happen while we're also recording
the video and making slides. Rushing it risks the whole submission, and a half-made-up
Brazil would break our most important rule: **blank beats wrong.**

**What we do instead: tell the truth, clearly.** In the slides and video we show that
Sangam was *built* for any country — a new country is a folder of data files, and a
checker confirms the folder is complete. Then we say plainly: *"India is live on real
government data. Brazil is our next pack — the engine doesn't change."* Judges respect a
true, specific answer far more than a demo that falls apart when they ask one question.

**After we submit, Brazil comes first.** Your teammate starts researching Brazil's data
the next day, while you work on Phase 2 (foundations). The two don't collide — the data
lives in its own folder that Phase 2 never touches.

### The order of work

```
27–30 Sep (before submitting):   Phase 0 → Phase 1 → SUBMIT
After submitting:                Phase 2  +  Brazil data research (at the same time)
                                 → Brazil live on the dashboard (rest of Phase 6)
                                 → Phase 4 (did the money work?)
                                 → Phase 3 (new look)
                                 → Phase 5 (whole-country view)
                                 → Phase 7 (extra security)
```

Phase 4 now comes before Phase 3. Phase 4 answers part of the brief we don't answer yet,
while Phase 3 is polish, which is valuable but not a gap.

If the October final comes before we finish, we drop items **from the bottom** (7, then 5,
then 3). We never drop Brazil — it's the BRICS answer.

### The next 4 days

| Day | What we do | Done when |
|-----|-----------|-----------|
| **27 Sep** (rest of today) | Phase 0 steps 1–4 and 7: deploy the waiting fix, set the admin password, lock the Telegram door, restrict CORS, write the smoke test | The live site is safe and the smoke test passes |
| **28 Sep** | Phase 0 steps 5–6 (zero embeddings — 3 hours max; real WhatsApp test) · Phase 1 steps 1–2 (tidy the project, load demo data) | Phase 0 finished; demo data live |
| **29 Sep** | Phase 1: record the video, finish the slides, add the BRICS story to both | Video exported; slides done |
| **30 Sep** | Morning: description, final check, **submit by midday**. Afternoon: spare time for surprises only | Submitted |

Your teammate can draft the slides on 28 Sep while you fix the live system; you review
them on 29 Sep.

**Rule for the last two days: no new features, no reorganising code.** Only fix things that
would look broken in the video or on the live link.

**One thing to check today:** the exact submission cut-off *time* and time zone on the
hackathon site. The schedule assumes end of day, India time.

---

## Where things stand now (27 Sep, after the rewrite)

You chose to rewrite everything now instead of patching. **The rewrite is done and tested on
your laptop. Nothing is live yet** — the website people see still runs the old code until you
approve a deploy.

**Done:**
- The new backend: one folder per feature, a rule-checker that stops features reaching into
  each other, migrations for every database change, and the Phase 0 security fixes (Telegram
  door locked, CORS restricted, admin password required).
- **The zero-embeddings mystery is solved.** When the AI failed, the old code saved a list of
  zeros as if it were a real answer. Now it saves "nothing yet" and tries again later.
- The new dashboard: the calm SaaS design, a real web address for every page, a source marker
  on every number. Checked in a real browser on desktop and phone.
- Practice data, the smoke test, a LICENSE file, and a new README, deploy guide and "add a
  country" guide.
- **Impact (Phase 4):** a new Impact page. For every block it shows the government's water-tap
  coverage in 2019 and 2026 next to what residents say today — so you can see where money went in
  but water isn't reaching people. It also compares complaints before and after a finished project,
  which switches on once we have real project data.
- **Updates for citizens:** when someone's report reaches the priority list, they get one message
  on Telegram (WhatsApp once Meta approves a message template). Their chat ID is stored locked
  (encrypted), used once, then deleted — or deleted after 6 months if never used.
- **Whole-country view (Phase 5):** a place picker on Overview and Priorities; a table
  ranking districts (then blocks) by how many places need action, which you click to zoom in;
  and a count of reports we couldn't place on the map, broken down by *why* — counts only,
  never the report text (your rule: text needs 5 different people in the same place and need,
  and these reports have no place). Overview → district → block → recommendation is three clicks.
- **Planned money:** a new verdict, "Planned, not started" (an **Audit** action), for places
  with high need where money is only planned. It won't show in the demo — we have no project data.
- **Extra security (Phase 7):** every PDF brief is now **digitally signed** — like a wax seal:
  change one character and the seal breaks. Anyone can check a brief on the new "Verify a
  brief" page, or offline with the public key in the repo. The security check-up found and
  fixed a real leak: the Telegram bot's password (its token) would have been written into the
  server's logs on every reply. Also added limits on how fast anyone can hit the tracking,
  PDF and simulator pages. No known-vulnerable libraries.
- **Public-good paperwork:** drafts of a privacy statement and a "do no harm" statement
  (`docs/privacy.md`, `docs/do-no-harm.md`) — please read them; you submit the application.
- **29 Sep, your list:** demo data for every feature (labelled DEMO); a new **Analytics**
  page of charts; the Fund/Audit switch no longer jiggles; every page fits phones and tablets;
  the report form speaks all 8 languages (Urdu right-to-left); photo preview with change/remove;
  a "discard or continue?" warning; voice notes tested in Hindi, Kannada and Tamil.
- **30 Sep: voice notes now go through Sarvam** (your key), which is built for Indian
  languages. In the same test, Gemini had written Kannada in English letters and Tamil in
  Russian letters; Sarvam got every word right, in the right script, every time. If Sarvam is
  ever down, Gemini takes over automatically.
- 130 automatic tests (120 backend, 10 dashboard), all passing. The Docker version was tested
  end to end before Phase 5.

**Two honest corrections the rewrite forced:**
1. **We have no real spending data.** The old dashboard's budget lines were made up by the old
   setup script *and presented as real*. (Update 29 Sep: you decided the prototype should use fake
   data wherever real data is missing, so every feature can be shown working. It is now **labelled
   DEMO everywhere** — that labelling is the difference from the old version.) Its real finding is stronger anyway:
   *the government's water data says homes here have taps, and residents say no water comes*
   — a **delivery gap**.
2. **We can't call a place "unserved" without data.** For roads, power, health, schools and
   sanitation we have no official statistics yet, so those show as **"demand hotspots — verify"**.

**Still needed from you before submitting:** decide on the production database (a new empty
Supabase project is my recommendation), set the settings on Render and Vercel, approve the
deploy, and test with your own phone. Then the video, slides and description.

---

## Part 3 — Did we answer the whole problem?

The problem statement is really describing a **broken loop**:

> Citizens speak → government listens → money is spent → someone checks it worked → citizens hear back

| Step in the loop | Do we handle it? |
|------------------|------------------|
| Citizens can speak (voice, text, WhatsApp, Telegram, many languages) | ✅ Yes |
| Their voice is compared with real data (population, water coverage, budgets) | ✅ Yes |
| This tells the government where to spend | ✅ Yes |
| **Someone checks whether the spending actually worked** | ❌ **No — this is our gap** (Phase 4 fixes it) |
| National leaders can see the whole country, not just one state | ✅ Built (Phase 5) — but only Karnataka's data is loaded so far |

---

## Part 4 — Rules we don't change

These were decided at the start and have proven right. Changing one needs a real
conversation first.

1. **The AI never decides the ranking.** Ranking is plain maths that anyone can check
   with a calculator. The AI only writes the explanation. *(If a judge asks "how do you
   know the AI isn't making things up?" — this is the answer.)*
2. **Every number the AI writes is checked by code.** If the AI writes a number that isn't
   in our evidence, the code rejects it.
3. **The dashboard never calls the AI.** The free AI plan allows only ~10–15 requests a
   minute. If the dashboard used AI, two judges clicking at once could break the demo. So
   all the AI work happens earlier, in the background, and the dashboard just reads saved
   results.
4. **A new country = a new folder of data files, not new code.**
5. **The government chooses the priorities, not us.** Whether to help the poorest place
   or the most people is a political choice, so those numbers live in a settings file.
6. **Every analysis is saved as a new version.** If one run crashes halfway, yesterday's
   results stay on screen instead of the dashboard going blank.
7. **We protect the people who complain.** We never store their real phone number or
   name, and we never show a complaint group with fewer than 5 different people in it,
   so nobody can be singled out.
8. **If the AI is down, citizens still get a reply.** We save the message and process it
   later.
9. **Every number on screen shows where it came from.**
10. **One feature = one folder, and features don't reach into each other.** (New rule,
    explained in Part 5.)

---

## Part 5 — How we work (the standard practices)

### Keeping the code simple (KISS)

Right now the code is organised like a restaurant where all the knives are in one room,
all the pans in another, and all the ingredients in a third. To cook one dish, you walk
between three rooms.

We're moving to **one room per dish**: everything for "budget simulator" lives in one
`simulator/` folder, everything for "impact" lives in one `impact/` folder, and so on.
To understand or change a feature, you open **one folder**.

Pages will also get **real web addresses**:

| Address | What you see |
|---------|--------------|
| `/` | The overview |
| `/priorities` | The ranked list |
| `/priorities/42` | One specific recommendation — you can send this link to someone |
| `/map` | The map |
| `/simulator` | "I have ₹500 crore, what should I fund?" |
| `/impact` | Did the money work? |
| `/report` | Where a citizen submits a problem |
| `/track/ABC123` | Where a citizen checks their request |

Today the web address never changes as you click around, so you can't share a link to a
specific priority and the Back button doesn't work.

### Keeping features independent

Rule: **features talk to each other through the database, never by reaching into each
other's code.**

Analogy: the kitchen and the waiters don't walk into each other's areas. The kitchen
puts a finished plate on the counter; the waiter picks it up from the counter. If the
kitchen reorganises its shelves, the waiter doesn't care — the counter is the same. In
Sangam, the "counter" is a database table.

We'll add a tool that **automatically fails the build** if someone breaks this rule, so
it can't happen by accident.

Also:
- Each page loads its own data. If the map breaks, only the map shows an error. The rest
  of the dashboard keeps working.
- Each optional feature has an **off switch** in settings.

### Adding a new feature later (the recipe)

1. Make a new folder for it (backend + frontend).
2. Add one line to the list of features (backend) and one line to the list of pages (frontend).
3. If it needs new database columns → write a **migration** (explained in Phase 2).
4. Write its tests.

That's it. Nothing else in the codebase needs to change.

### What "done" means

A task is only done when:
- it has tests, and all tests pass;
- it has been tried against a **real** database — not just fake test data (fake data has
  hidden four real bugs in this project before);
- if deployed, the quick live check (the "smoke test") passes;
- **you have tried it yourself.** Until then I say "deployed, needs your test", never "fixed".

---

## Part 6 — The phases at a glance

Listed in the order we'll do them. Phase numbers stay the same as the technical plan, which
is why they're not in number order.

| Order | Phase | In one sentence | Time (one person) | When |
|-------|-------|-----------------|-------------------|------|
| 1st | **0** | Fix the live system so it's safe and correct | ~1 day | Before submitting |
| 2nd | **1** | Make the video, slides, description (with the BRICS story), and tidy the project | ~2 days | Before submitting |
| 3rd | **2** | Strengthen the foundations so changes stop being risky | 3–4 days | Right after submitting |
| 3rd, same time | **6** (research part) | Your teammate finds real Brazil data | 3–5 days | Right after submitting |
| 4th | **6** (build part) | Brazil live on the dashboard | 1–2 days | After Phase 2 |
| 5th | **4** | Show whether money actually fixed the problem, and tell citizens | 2–3 days | After Brazil |
| 6th | **3** | Redesign the dashboard so it looks like a real product | 3–4 days | After Phase 4 |
| 7th | **5** | Add a whole-country view and show how far our reach goes | 2–3 days | After Phase 3 |
| 8th | **7** | Extra security and apply for official "public good" status | ~2 days | Before the final round |
| **8** | Things we've decided **not** to do (and why) | — | — |

---

## Part 7 — Each phase explained

### Phase 0 — Fix the live system

**Why first?** The video, the slides, and the link we hand the judges all show the live
system. If it's broken, everything we submit shows it broken.

**What we do:**

1. **Deploy a fix that's already written.** We added a new column to the database
   (`flagged_coordinated`, which marks suspicious floods of messages). The fix that adds
   this column to the live database is written but not deployed. Until it is, **new
   citizen reports might fail to save.** This is the most urgent item.
2. **Set the admin password (`ADMIN_TOKEN`) on Render.** Right now the admin pages lock
   everyone out, including us.
3. **Lock the Telegram door.** Telegram sends messages to a URL on our server. Right now
   that URL accepts anything from anyone — a stranger who finds it could post fake
   complaints. Telegram lets us set a secret word it includes with every real message; we
   reject anything without it. (WhatsApp already does this properly.)
4. **Limit who can call our API.** A browser setting called **CORS** decides which websites
   may talk to our server. Ours currently says "any website". We'll change it to "only our
   dashboard."
5. **Investigate the broken embeddings.** An **embedding** is a list of numbers that
   captures what a message *means*, so "no water" in Kannada and "पानी नहीं" in Hindi end up
   with similar numbers. That's how we group complaints across languages. **16 of our 24
   real messages have embeddings that are all zeros** — meaningless — so grouping across
   languages isn't working on real data. We'll find out why (my first guess is messages that
   arrived while the AI was down, but I'll test that, not assume it), fix it, and repair the
   16 rows.
6. **Test WhatsApp for real.** Send a real voice note from a real phone and watch it reach
   the dashboard. This has never been confirmed.
7. **Write a "smoke test"** — a small script that checks, in 10 seconds, that the live
   site's main parts work. We run it after every deploy from now on.

**How we'll know it's done:** you send one Telegram and one WhatsApp message from your
phone and see both on the dashboard.

**If something goes wrong:** the embedding investigation gets 3 hours maximum. If we
haven't found the cause by then, we put a guard in place so it can't get worse, and move
on. The demo matters more.

---

### Phase 1 — The submission package

**Why?** Judges spend minutes, not hours. They judge what they see in the video and the
slides.

**What we do:**

1. **Tidy the project.**
   - **Add a LICENSE file.** Right now there isn't one, and the README says "MIT" while we
     decided on "Apache-2.0". A public good *must* have a clear licence — this is a
     5-minute fix with a big consequence.
   - Delete the leftover `engine/` folder (old code nothing uses).
   - Rewrite the README so a stranger understands Sangam in 30 seconds.
   - Add a short guide on "how to add a new country."
2. **Prepare the demo data.** ✅ Done — 4,704 practice citizen messages. **These are made
   up, and we say so openly.** The places, the number of households and the water-tap
   coverage are real government data. **Since 29 Sep the demo also has made-up projects
   (spending) and made-up statistics for roads, power, health, sanitation and schools**, all
   labelled DEMO, so every verdict and page has something real to compute. The maths is real;
   only the inputs are fake.
3. **Record the video (3–5 minutes).** The order matters:
   1. **Start with the punchline:** a "delivery gap" — "The government's own water data says
      95% of homes here have a tap. These residents say the water never comes." Records say
      served; people say otherwise.
   2. Then show where it came from — voice notes in several languages.
   3. Send a real voice note **live** during recording.
   4. Show the budget simulator.
   5. Download the PDF report and show that every number has a source. Then drop it on the
      **Verify a brief** page — "Authentic" — and a copy with one character changed — "Altered".
   6. End with **"built for BRICS"**: show the India data folder, run the checker on screen,
      and say *"India runs on real data; Brazil is next — the engine doesn't change."* (There
      is no Brazil folder yet, so don't show one.)

   **Never start the video with the chatbot or the form.**
4. **Make the slides (10–12).** Problem → our insight (the join) → the verdicts → demo →
   how it works → why you can trust it → reach → **built for BRICS** → scale and how easy
   it is to deploy → competitors → roadmap (Brazil first) → team.
5. **Write the 2–3 line description.** Corrected draft (the first one wrongly said we use
   government spending records):
   > Sangam is an open-source Digital Public Good that hears citizens in their own language —
   > voice, text or photo, over WhatsApp, Telegram or the web — and sets what they report beside
   > official data, to show officials where public services are missing or failing on the
   > ground. It ranks priorities with transparent arithmetic, checks every AI-written number
   > against a cited source, and signs every brief so it cannot be quietly altered. A new BRICS
   > country is a folder of data, not new code; it runs today on real Indian government data.
6. **Tell the BRICS story honestly.** This is the question judges will ask most.
   - **What we *can* say, because it's true:**
     - the engine has nothing India-specific in it;
     - a country is a folder of data files;
     - languages, currency and priorities are settings in that folder;
     - a checker confirms a folder is complete before it's used;
     - grouping works across languages without special rules per language.
   - **What we must *not* do:** show the Brazil folder as if it works. It doesn't yet.
   - **Practise this answer:** *"What would South Africa need?"* → "A folder: its
     municipalities, its statistics, its budget lines, and a settings file listing isiZulu,
     Afrikaans and English. No engine code changes — the checker tells you when the folder
     is complete."

**How we'll know it's done:** all five things the hackathon asks for exist, and the live
link works on a phone in a private browser window.

---

### Phase 2 — Stronger foundations

**Why?** Right now, changing the database is risky. That's exactly how the Phase 0
column problem happened. Every later phase changes the database, so we fix this first.

**What we do:**

1. **Start using "migrations."** A **migration** is a small, numbered script that
   describes one change to the database — "add this column" — and can also undo it. The
   tool is called **Alembic**. It keeps a record of which changes the database already
   has, so it never applies one twice or skips one. Think of it as version history for the
   database's shape.
   - One careful step: our live database already exists. So instead of *running* the first
     migration on it, we *mark* it as already done (`alembic stamp`). Running it would try to
     create tables that already exist.
2. **Reorganise into feature folders** (the "one room per dish" idea from Part 5). We move
   files **one feature at a time**, running all tests after each move, and never change
   any logic in the same step as a move. That way, if something breaks, we know exactly
   which move broke it.
3. **Add the rule-checker** that fails the build if one feature reaches into another.
4. **Give the dashboard real web addresses** (React Router), and let each page load its own
   data (TanStack Query — a library that handles loading, caching and errors for you).
5. **Test the frontend automatically too.** Today the automatic checks on every push only
   test the backend.
6. **Add off switches** for optional features.

**How we'll know it's done:** the folders look like the plan, every page has an address,
and we've changed the live database through a migration at least once without trouble.

---

### Phase 3 — A dashboard that looks like a real product

**Why?** The current design has the tell-tale signs of AI-generated design: dark blue
background with a blue-to-purple gradient, glowing shadows, two different display fonts,
emoji. Real products (Linear, Stripe, Vercel) look calm and plain. A government official
should look at it and think "serious tool", not "hackathon demo".

**What we do:**

- **Light background by default, grey tones, one accent colour.** Colour is used **only**
  to mean something — the verdict colours (red for unserved gap, orange for stalled, etc.).
  If everything is colourful, nothing stands out.
- **One font.** Numbers line up neatly in columns.
- **Tables instead of card grids.** Officials scan rows; tables are faster to read.
- **A sidebar on the left** for moving between pages.
- **Every number gets a tiny marker** — hover over it and you see where it came from. This
  shows off our biggest strength on screen.
- **Proper "loading", "empty" and "error" screens** for every page.
- **Use ready-made building blocks** (Tailwind + shadcn/ui) so everything looks consistent
  without writing hundreds of lines of styling by hand.

**Rule for this phase:** only the look changes. No backend changes.

**How we'll know it's done:** someone new can find "why is this #1?" in two clicks.

---

### Phase 4 — Did the money work? And tell the citizen.

**Why?** The problem statement says governments have "no way to measure the impact."
This is the one part we don't answer yet. It also makes the best possible ending for the
demo: *"This water project finished in March. Complaints here fell 70%. The 43 people
who reported it got a message."*

**What we do:**

1. **Measure before and after.** For each finished project, count how many different
   people complained in the 3 months **before** it finished and the 3 months **after** (we
   skip one month in between, to give it time to take effect). Adjust for population.
   Then label it:
   - **Improved** — complaints fell by 30% or more
   - **No change**
   - **Worsened** — complaints rose by 30% or more
   - **Not enough data** — too few people in either period to say

   This is plain maths again, no AI.

   **Honesty point:** we say "complaints fell *after* the project finished", never "the
   project *caused* it." Other things could have changed too.
2. **An Impact page** showing each finished project and its label, with a simple
   before/after chart.
3. **Tell citizens what happened.** When their problem gets funded or fixed, send them a
   message.
   - ⚠️ **This one is your decision.** To message someone later, we need to keep a way to
     reach them. Today we deliberately don't — we only keep a scrambled version of their ID
     that can't be turned back into a phone number. To send updates, we'd have to store
     their chat ID **locked (encrypted)**, and delete it after we've messaged them or after
     6 months. That's a privacy trade-off, and it's yours to make, not mine.
4. **A tracking page** where a citizen types their tracking code and sees: received →
   grouped → prioritised → funded → completed.

**How we'll know it's done:** the Impact page shows a real project with the right label,
and a test phone receives an update message.

---

### Phase 5 — A whole-country view, and proving our reach

**Why?** The problem statement says "**national** policymakers." We're deep in Karnataka
but have no whole-country view. And 20% of the score is "Depth & Reach."

**What we do:**

1. **Zoom levels:** country → state → district → block. At the national level, show
   states ranked by how many unserved gaps and how much stuck money they have.
2. **A "reach" panel:** how many languages we've received, which channels people used,
   how many areas have reports, and — honestly — how many reports we **couldn't place on
   the map**.
3. **Future plans:** the problem statement mentions "public investment plans" — money
   that's *planned* but not yet given. We add "planned" as a project status, and a new
   verdict: "high need, only planned money — nothing started."

**How we'll know it's done:** you can go from the whole country to one specific
recommendation in three clicks.

**✅ Built 27 Sep.** Two changes from the plan above: (1) no "stuck money" ranking, because we
have no real spending data — districts are ranked by how many places need action instead;
(2) the unplaced-reports panel shows counts by reason only, never the text. Only Karnataka is
loaded, so the view opens on Karnataka's districts.

---

### Phase 6 — A second country: Brazil (first job after submitting)

**Why?** The brief says "across BRICS nations." We claim "a new country is just a folder of
data." Right now that's true in theory but never shown, so this is the first thing we build
after submitting.

**Who does what:** your teammate does the data research (step 1), starting the day after
we submit, while you work on Phase 2. You do steps 2–4 once Phase 2 is done.

**What we do:**

1. **Collect Brazil's real data** — this is research, not coding. Regions and population
   from IBGE, water/sanitation from SNIS, spending from Brazil's transparency portal.
   Start with one Brazilian state.
2. **Check it with our validator** (a script that checks the data files are complete and
   correctly formatted).
3. **Add a country switcher** to the dashboard.
4. **Send Portuguese messages** and check they're grouped correctly.

**The key test:** the scoring and grouping code **must not change**. If we have to edit
them to make Brazil work, our "just a folder" claim was wrong, and we fix the design, not
patch around it.

**Check-in after 2 days of research:** have we found *real* Brazilian water-spending data,
with sources? If not, stop searching and switch to the backup plan.

**Backup plan:** a second *Indian* state wouldn't answer "BRICS", so we stay in Brazil. We
load the Brazilian data we **can** find for real — regions, population, water coverage —
and leave spending empty. Sangam still runs on it unchanged and can still spot places
with poor water coverage and many complaints. The dashboard says clearly "spending data not
yet loaded" instead of pretending. That still proves the engine works in a second country,
which is the whole point.

---

### Phase 7 — Extra security and "public good" status

**✅ Built 28 Sep** (except step 4, which is yours). One change from the plan: the seal covers
the **whole PDF file**, not just the numbers — otherwise someone could change the visible text
and the seal would still look intact. Step 2 already runs every 12 hours through the
"keepalive" job, once its two GitHub secrets are set during deploy.

**What we do:**

1. **Signed reports.** When we export a PDF report, we add a **digital signature**. A
   digital signature is like a wax seal: if anyone changes even one number in the PDF
   afterwards, the seal "breaks", and anyone can check it. This is the **one place**
   where the public-key technology you asked about (PKI) is genuinely worth it. Building a
   full PKI for the whole app is not — the padlock (HTTPS) we already get free from
   Vercel and Render already covers the rest.
2. **Automatic clean-up.** Delete raw voice notes and photos after 90 days, as promised.
3. **A security check-up.** Every entry point is locked, no personal details end up in
   logs, and no known-vulnerable libraries are in use.
4. **Apply for Digital Public Good status** with the Digital Public Goods Alliance, the
   organisation that certifies them. **You submit this**, since it's a statement on behalf of
   the project.

---

### Phase 8 — What we've decided NOT to do

| Idea | Decision | Why |
|------|----------|-----|
| Login for officials (Clerk) | Later, after the final | Judges need an open link; a login is one more thing that can fail live |
| "Ask the data" chatbot | No | It would put the AI on the dashboard, breaking rule 3 |
| More chat apps | Later | Do three well rather than six badly |
| A full PKI for the whole app | No | Too much work for no real benefit; HTTPS + locked webhooks + signed reports cover it |
| Redis / job queue | Later | Not needed at our scale yet |
| Phone-call line for basic phones, Bhashini | Put on the roadmap slide | A great reach story, but not needed to win |

---

## Part 8 — Testing, simply

Think of tests as **checks that run automatically so we don't have to remember to check.**

| Kind | What it checks | Example |
|------|----------------|---------|
| **Unit tests** | One small piece of logic on its own | "Does the maths give the right score?" |
| **Route tests** | One web address behaves right | "Does the admin page refuse you without a password?" |
| **Integration tests** | Pieces working together with a real database | "Does a message actually land in the right district?" |
| **Frontend tests** | Screens behave right | "If the map breaks, does the rest still show?" |
| **Smoke test** | The live site, right after deploying | "Do the main pages load?" |
| **Real-phone test** | The whole journey | Voice note on WhatsApp → shows on dashboard |

**Our rules:**
- **Every bug gets a test first.** Write a test that shows the bug, watch it fail, fix
  the bug, watch it pass. The bug can never quietly come back.
- **Fake the AI and WhatsApp in tests, but never fake the database.** Fake databases have
  hidden real bugs from us before.

---

## Part 9 — Debugging, simply

When something breaks, **investigate before guessing.** Guessing has been wrong many times
on this project; evidence has always found the real cause.

1. **Make it happen again** on purpose. If we can't, add logging and wait.
2. **Find which part it's in:**
   - **Intake:** a message arriving
   - **Analysis:** the background grouping and scoring
   - **Dashboard:** showing results
3. **Check the boring things first:**
   - Right database?
   - Settings present?
   - Latest version actually deployed?
   - AI quota used up?
4. **Write down each guess**, test the cheapest one first, and cross out the wrong ones.
   Wrong guesses are useful — they narrow things down.
5. **Fix the cause, not the symptom.**
6. **Write a test for it**, then fix, then confirm on the real system.
7. **Report honestly:** what broke, why, what fixed it, and what still needs your test.

**Common problems and where to look first:**

| What you see | First place to look |
|--------------|---------------------|
| A citizen got no reply | Was the message rejected at the door? Did the AI fail? |
| A report never shows on the dashboard | Couldn't find its location? Fewer than 5 people in its group? Analysis not re-run? |
| Dashboard empty or old | Did the last analysis finish? Is the dashboard pointing at the right server? |
| Languages not grouping together | The zero-embeddings problem |
| A verdict looks wrong | Open its score breakdown and redo the maths by hand |

---

## Part 10 — Putting changes live (deploying)

Every time:
1. All automatic tests pass.
2. Confirm **which database** we're about to change. (This has bitten us twice.)
3. **Ask you first** — deploying affects real users.
4. Deploy the backend, then the frontend.
5. Run the smoke test.
6. If it fails, roll back to the previous version. That only works if our database changes
   only *add* things, never delete them — so that's the rule.

---

## Part 11 — Biggest risks

| Risk | What we do about it |
|------|---------------------|
| We run out of time before 30 Sep | Only Phases 0 and 1; follow the 4-day schedule; no new features in the last two days; submit by midday on the 30th |
| Judges mark us down because only India works | Tell the BRICS story honestly (Phase 1, step 6), practise the answer, build Brazil first after submitting |
| AI free plan hits its limit during the demo | The dashboard never uses AI, so it can't break |
| A database change breaks the live site | Migrations (Phase 2) plus the "which database?" check |
| Strangers post fake reports | Lock the Telegram door (Phase 0) |
| A judge asks "is this data real?" | We say it first: the messages are practice data; places, households and water coverage are real and sourced; we have no spending data yet, so we show none |
| Brazil spending data can't be found | 2-day check-in, then load real Brazil data without spending (see Phase 6) |
| Only one person knows the system | These two plan documents, plus tests that describe how things should work |

---

## Part 12 — Words you'll see

| Word | Simple meaning |
|------|----------------|
| **The join** | Putting complaints and spending side by side for the same place and need |
| **Verdict** | The label the join produces: unserved gap, stalled allocation, and so on |
| **Country pack** | A folder of data files describing one country |
| **Embedding** | Numbers that capture a message's meaning, so similar meanings match across languages |
| **Migration** | A numbered, undoable script that changes the database's shape |
| **Webhook** | The web address Telegram or WhatsApp sends messages to |
| **CORS** | The rule for which websites may talk to our server |
| **Smoke test** | A 10-second check that the live site works |
| **Off switch / kill switch** | A setting that turns a feature off without touching code |
| **Deploy** | Putting a new version live |
| **Roll back** | Going back to the previous version |
| **Digital signature** | A tamper-proof seal on a document |
| **DPG** | Digital Public Good — free, open software governments can use |
