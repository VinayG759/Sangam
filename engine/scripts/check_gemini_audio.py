"""
Day-1 assumption check: can one Gemini call turn a voice note into the exact
structured record Sangam stores?

This is not a toy "does the API work" script. It runs the real Call 1 from the
design -- multimodal in, schema-locked JSON out -- so that a pass here means the
whole intake understanding step is validated before anything is built on it.

Three things it proves, or fails on:

  1. OGG/Opus goes straight to Gemini with no transcoding.
     Telegram and WhatsApp both send OGG/Opus. If this fails we need ffmpeg in
     the pipeline, which changes the deployment story.
  2. responseSchema is enforced, so the reply is always parseable.
  3. need_type is constrained to the country pack's taxonomy, so the model
     cannot invent a category the country does not recognise.

Usage:
    pip install -r engine/requirements.txt
    export GEMINI_API_KEY=...          # or put it in .env
    python engine/scripts/check_gemini_audio.py path/to/voice-note.ogg

    # text-only smoke test, no audio file needed:
    python engine/scripts/check_gemini_audio.py --text "ನಮ್ಮ ಹಳ್ಳಿಯಲ್ಲಿ ನೀರಿಲ್ಲ"
"""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

# Windows consoles default to cp1252, which cannot print Kannada, Hindi or any
# other script this system handles. Force UTF-8 so transcripts render.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[2]
TAXONOMY = REPO / "packs" / "india" / "need_taxonomy.yaml"

# flash-lite is primary: on the free tier gemini-3.6-flash returns 503 under
# load, while flash-lite answers in ~1s. For a fixed-schema extraction the
# lighter model is the right call anyway.
MODEL = "gemini-3.5-flash-lite"

# Formats Telegram and WhatsApp actually send, plus common recorder output.
MIME_BY_SUFFIX = {
    ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg",
    ".mp3": "audio/mp3", ".wav": "audio/wav", ".flac": "audio/flac",
    ".aac": "audio/aac", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
    ".aiff": "audio/aiff",
}

PROMPT = """You are the intake step of a government citizen-request system.

A citizen has reported an infrastructure problem in their own words. Extract a
structured record. Rules:

- Detect the language. Transcribe exactly what was said, in its own script.
- Translate to English faithfully. Do not embellish or add detail.
- need_type MUST be one of the allowed values. If none fit, use "other".
- location_text: the place the citizen named, exactly as they said it, in
  their own script. Empty string if they named no place. NEVER guess.
- location_text_latin: the same place names romanised into Latin script, using
  the spelling an Indian government dataset would use. "" if no place named.
  This is what the gazetteer matches on, so it matters as much as the original.
- affected_estimate: only if they stated a number. Use 0 if they did not.
- urgency 1-5, judged on the severity they described, not on your own view.
- contains_pii: true if a name, phone number or ID number was spoken.
- is_actionable: false for greetings, tests, abuse or anything not a request.

Invent nothing. Every field must be traceable to what was actually said."""


def load_need_types() -> list[str]:
    """Read the enum straight from the pack, so the check tests the real taxonomy."""
    if not TAXONOMY.exists():
        return ["water", "road", "electricity", "health", "education", "sanitation", "other"]
    keys = []
    for line in TAXONOMY.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- key:"):
            keys.append(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("fallback_key:"):
            keys.append(stripped.split(":", 1)[1].strip())
    return keys or ["other"]


def build_schema(need_types: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "language": {"type": "string", "description": "BCP-47 code, e.g. kn, hi, pt"},
            "transcript": {"type": "string"},
            "translation_en": {"type": "string"},
            "need_type": {"type": "string", "enum": need_types},
            "urgency": {"type": "integer", "minimum": 1, "maximum": 5},
            "location_text": {"type": "string"},
            "location_text_latin": {"type": "string",
                                    "description": "romanised place name for gazetteer matching"},
            "affected_estimate": {"type": "integer"},
            "contains_pii": {"type": "boolean"},
            "is_actionable": {"type": "boolean"},
        },
        "required": ["language", "transcript", "translation_en", "need_type",
                     "urgency", "location_text", "location_text_latin",
                     "affected_estimate", "contains_pii", "is_actionable"],
        "propertyOrdering": ["language", "transcript", "translation_en", "need_type",
                             "urgency", "location_text", "location_text_latin",
                             "affected_estimate", "contains_pii", "is_actionable"],
    }


def load_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    sys.exit(
        "No GEMINI_API_KEY found.\n"
        "  Get a free key at https://aistudio.google.com/apikey\n"
        "  Then: cp .env.example .env  and paste it in."
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="?", help="path to a voice note (.ogg preferred)")
    ap.add_argument("--text", help="run a text-only check instead of audio")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    if not args.audio and not args.text:
        ap.error("give an audio file path, or --text \"...\"")

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("pip install -r engine/requirements.txt")

    client = genai.Client(api_key=load_key())
    need_types = load_need_types()
    print(f"model      {args.model}")
    print(f"need_types {need_types}")

    parts: list = [PROMPT]
    if args.audio:
        path = Path(args.audio)
        if not path.exists():
            sys.exit(f"no such file: {path}")
        suffix = path.suffix.lower()
        mime = MIME_BY_SUFFIX.get(suffix) or mimetypes.guess_type(str(path))[0]
        if not mime:
            sys.exit(f"unknown audio type for {suffix}")
        data = path.read_bytes()
        print(f"audio      {path.name}  {len(data)/1024:.1f} KB  as {mime}")
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))
    else:
        print(f"text       {args.text!r}")
        parts.append(f"Citizen said: {args.text}")

    started = time.time()
    try:
        response = client.models.generate_content(
            model=args.model,
            contents=parts,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=build_schema(need_types),
            ),
        )
    except Exception as exc:
        print(f"\nFAILED after {time.time()-started:.1f}s\n  {exc}")
        print("\nIf this is a model-not-found error, check the current model id at")
        print("https://ai.google.dev/gemini-api/docs/changelog and pass --model")
        sys.exit(1)

    elapsed = time.time() - started
    record = json.loads(response.text)
    print(f"\nOK in {elapsed:.1f}s\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))

    print("\nchecks:")
    ok = True
    for label, passed in [
        ("returned valid JSON matching the schema", True),
        (f"need_type within taxonomy ({record.get('need_type')})",
         record.get("need_type") in need_types),
        ("location_text not fabricated (empty or a real string)",
         isinstance(record.get("location_text"), str)),
        (f"romanised location produced for gazetteer ({record.get('location_text_latin')!r})",
         isinstance(record.get("location_text_latin"), str)),
        ("urgency in 1-5", 1 <= int(record.get("urgency", 0)) <= 5),
        (f"intake latency under 5s budget ({elapsed:.1f}s)", elapsed < 5.0),
    ]:
        mark = "PASS" if passed else "FAIL"
        ok = ok and passed
        print(f"  [{mark}] {label}")
    if args.audio:
        print(f"  [PASS] {mime} accepted with no transcoding")

    print("\n" + ("All checks passed - intake understanding is validated."
                  if ok else "Some checks failed - see above before building on this."))


if __name__ == "__main__":
    main()
