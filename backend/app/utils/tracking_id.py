import random

def generate_tracking_id() -> str:
    """
    Generate a short, human-typeable tracking code for citizen reports.
    Format: SNG-XXXXXX (where X is uppercase letter or digit, excluding O/0/I/1 for readability)

    6 chars over a 32-symbol alphabet is ~1.07 billion combinations -- large
    enough that GET /citizens/{tracking_id} (unauthenticated, no rate limit)
    can't be scraped end-to-end in any practical time, while staying short
    enough to read back over a voice/text channel like Telegram.
    """
    # Alphabet optimized for readability (no O, 0, I, 1)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    random_chars = ''.join(random.choices(alphabet, k=6))
    return f"SNG-{random_chars}"
