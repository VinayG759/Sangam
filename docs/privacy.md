# Privacy

> **Draft for review.** This describes what the code in this repository does. The
> maintainer must review it before it is used in a Digital Public Goods Alliance application
> or published as a deployment's privacy notice. Each deployment is responsible for adding
> its own operator name, contact and legal basis.

Sangam lets residents report problems with public services (water, roads, power and so on)
by WhatsApp, Telegram or a web form, in their own language, by text, voice or photo. It
groups those reports by place and need and sets them beside official statistics. This page
explains what it keeps, for how long, and who can see it.

## What is collected

| Data | Kept? | How |
|---|---|---|
| Phone number / Telegram ID / web browser ID | **Never stored in readable form** | Turned into a one-way keyed hash (HMAC-SHA-256 with a server-only secret). The hash lets Sangam count *distinct* people and limit abuse; it cannot be turned back into the number. |
| Message text | Stored, **after redaction** | Email addresses, phone numbers and long digit runs (such as 12-digit ID numbers) are replaced with `[redacted]` before storage, after the AI model's own redaction pass. |
| Voice notes and photos | **Temporary** | Kept only until they have been understood, then deleted. Anything not yet processed is deleted after the country pack's `media_retention_days` (90 days for India). |
| Place | Stored | The administrative area (for example a block or district), matched from the place named, a shared location, or a picker. Precise coordinates are stored only when the resident shares them. |
| Chat ID for a status update | **Encrypted, temporary, optional** | Only if the deployment has an encryption key configured. Encrypted with a key held only in the server's environment, used once to tell the resident their report reached the priority list, then deleted. Unused ones are deleted after `contact_retention_days` (180 days). Without a key, nothing is kept. |
| IP address | Not stored | Used in memory only, to rate-limit public endpoints. |

## Who sees what

- **The public dashboard never shows who reported anything.** No hash, tracking ID or
  contact detail appears on any screen, export or API response for officials.
- **Report text is shown only in aggregate places.** A place and need appear on any screen,
  and their redacted report text becomes readable, only once at least
  `min_distinct_reporters` different people (5 for India) have reported there. Smaller groups
  still count toward the statistics but are never displayed, so a single resident in a small
  village cannot be singled out.
- **Reports that could not be placed on the map are shown only as counts by reason**, never
  as text: with no place, they can never meet the threshold above.
- **The resident** can look up their own report's progress with the tracking ID they were
  given. The tracking page shows the stage and verdict, not other people's reports.

## Third parties

- **Google Gemini** processes the text, voice and photo of each report to transcribe,
  translate, classify and redact it, and writes plain-language summaries of aggregated
  evidence. Only the report content is sent, never the resident's phone number or chat ID.
  Deployments should check the data-use terms of the Gemini tier they use.
- **Sarvam AI** (optional, when `SARVAM_API_KEY` is set) receives the audio of voice notes and
  returns a transcript in the speaker's language. Only the audio is sent, never the resident's
  phone number or chat ID. If Sarvam is not configured or fails, Gemini transcribes instead.
  Deployments should check Sarvam's data-use terms.
- **Hosting:** the reference deployment uses Render (API), Supabase (PostgreSQL database)
  and Vercel (dashboard). Each deployment chooses its own hosts.
- **Messaging:** WhatsApp (Meta) and Telegram deliver messages to and from residents under
  their own privacy terms.

## Demonstration data

The public demonstration uses **synthetic** citizen reports (marked `is_synthetic` in the
database and labelled on screen). The places, household counts and water-coverage figures
are real, published government data, each linked to its source.

## Security

Webhooks are authenticated (Telegram secret token, WhatsApp HMAC signature). Public
endpoints are rate-limited. Administrative endpoints require a bearer token and are off when
none is configured. Secrets live only in environment variables. Exported briefs are
digitally signed so recipients can detect alteration (see `docs/brief-signing-key.pub`).

## Where this is enforced in code

| Promise | Code |
|---|---|
| Sender IDs hashed | `backend/app/core/security.py` (`reporter_hash`) |
| Redaction | `backend/app/core/text.py` |
| Media deletion | `backend/app/features/intake/service.py`, `backend/app/features/analysis/run.py` |
| Encrypted contacts | `backend/app/core/crypto.py`, `backend/app/features/notify/service.py` |
| Display threshold | `backend/app/features/analysis/run.py` (`displayable`), every read endpoint |
| Unplaced reports as counts only | `backend/app/features/overview/router.py` (`/unlocated`) |
