# Do no harm

> **Draft for review.** The maintainer must review this before it is used in a Digital
> Public Goods Alliance application. It states the risks we see and what the code does about
> each; it is not a guarantee.

Sangam tells public officials where residents' reports and official data disagree, so they
can decide where to fund or audit. That is useful precisely because it can shift attention
and money — which is also how it could cause harm. These are the risks we design against.

## 1. Exposing the people who report

**Risk.** A resident who complains about a local official or contractor could face
retaliation if identified.

**What Sangam does.** Phone numbers and chat IDs are never stored in readable form (one-way
keyed hash). Personal details in text are redacted before storage. No place and need is shown
until at least 5 different people have reported it (configurable per country), so no single
voice can be singled out. Reports that cannot be placed are shown only as counts. Chat IDs
kept for status updates are encrypted, used once and deleted. See `docs/privacy.md`.

## 2. Being gamed

**Risk.** An organised group floods reports to pull money toward one place, or to discredit
another.

**What Sangam does.** Demand counts *distinct* people, not messages. Each person is capped per
day. Near-identical messages from several people in a short window are flagged as possibly
coordinated and held out of the analysis for review. Rankings compare each place with the
typical place for the same need, not raw totals.

## 3. Being wrong with confidence

**Risk.** An AI-generated recommendation states a figure that is not true, and an official
acts on it.

**What Sangam does.** The ranking is transparent arithmetic with published weights, never an
AI judgement. The AI only writes the explanation, and code rejects any explanation that
contains a number not present in the sourced evidence; a fixed template is used instead.
Every figure on screen and in exported briefs carries its source. Where no official
statistic exists, Sangam says so (`DEMAND_HOTSPOT` — verify on the ground) instead of
calling a place unserved.

## 4. Inventing evidence

**Risk.** Demonstration or placeholder data is mistaken for real government records.

**What Sangam does.** Sangam never fabricates spending data: if none is loaded, no money
figures appear. Synthetic citizen reports are marked in the database and labelled on every
screen and brief. Exported briefs are digitally signed so a recipient can detect an altered
copy.

## 5. Excluding people who cannot use it

**Risk.** Priorities tilt toward places with more smartphones, literacy or a dominant
language, and away from those most in need.

**What Sangam does.** Residents can report by voice, in their own language, on WhatsApp,
Telegram or the web. Demand is measured per household, not in raw counts, and set beside
official coverage data so a quiet, badly served place still shows a deficit.
**What it does not yet do:** reach people without a phone (an IVR or missed-call line is on
the roadmap). Officials should treat low report volume as "not yet heard", not "no problem".

## 6. Replacing human judgement

**Risk.** A ranked list is treated as a decision rather than an input.

**What Sangam does.** Every verdict is framed as a recommended action for a person to take
(fund, audit, verify, monitor), with the evidence and the arithmetic shown so it can be
challenged. Sangam does not allocate money or trigger any action on its own.

## Reporting a harm

If you believe Sangam has caused or could cause harm, open an issue in this repository, or
contact the maintainer privately for anything involving personal safety.
