"""
Turns a place name or a GPS point into a region. No network calls.

Place names are fuzzy-matched against every region's name and name_variants,
so different spellings and scripts of one place land on the same region. The
score (0-100) decides what happens next — accept, ask "did you mean…?", or
ask for the place — using thresholds from pack.yaml. Which levels can be
matched, and which words merely describe a kind of place, also come from the
pack.
"""

import math
import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pack import Pack
from app.models import Region

# English words that describe a kind of place rather than name it. Each pack adds its own.
BASE_GENERIC = {"city", "town", "village", "rural", "urban", "near", "in", "at", "the", "of", "and", "road", "main"}
NEAREST_DEEPEST_KM = 30


@dataclass
class Match:
    region_id: str
    name: str
    score: float


def normalise(text: str, generic: set[str] = frozenset(BASE_GENERIC)) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(w for w in text.split() if w not in generic)


def _phrases(text: str, generic: set[str]) -> list[str]:
    """The whole text plus every 1- and 2-word window, so 'near bus stand Riverton' finds 'riverton'."""
    words = normalise(text, generic).split()
    phrases = {" ".join(words)} if words else set()
    for n in (1, 2):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            if len(phrase) >= 4:
                phrases.add(phrase)
    return [p for p in phrases if p]


class Gazetteer:
    def __init__(self, regions: list[Region], min_level: int = 2, generic_words: list[str] = ()):
        self.regions = {r.id: r for r in regions}
        self.min_level = min_level
        self.generic = BASE_GENERIC | {w.casefold() for w in generic_words}
        self.entries: list[tuple[str, Region]] = []
        for region in regions:
            if region.level < min_level:
                continue
            for name in [region.name, *region.name_variants]:
                key = normalise(name, self.generic)
                if key:
                    self.entries.append((key, region))

    @classmethod
    def for_pack(cls, db: Session, pack: Pack) -> "Gazetteer":
        regions = list(db.scalars(select(Region).where(Region.country_code == pack.country_code)))
        return cls(regions, pack.places.min_match_level, pack.places.generic_words)

    def resolve(self, candidates: list[str]) -> Match | None:
        """Best match across all candidate strings. Ties go to the more specific (deeper) region."""
        best: tuple[float, int, Region] | None = None
        for candidate in candidates:
            for phrase in _phrases(candidate, self.generic):
                for key, region in self.entries:
                    score = fuzz.ratio(phrase, key)
                    if best is None or (score, region.level) > (best[0], best[1]):
                        best = (score, region.level, region)
        if best is None:
            return None
        return Match(best[2].id, best[2].name, round(best[0], 1))

    def nearest(self, lat: float, lon: float) -> Match | None:
        """Nearest place at the deepest level within NEAREST_DEEPEST_KM, else the nearest at min_level."""
        def km(region: Region) -> float:
            return _haversine_km(lat, lon, region.lat, region.lon)

        placed = [r for r in self.regions.values() if r.lat is not None and r.level >= self.min_level]
        deepest = max((r.level for r in placed), default=self.min_level)
        nearest_deep = min((r for r in placed if r.level == deepest), key=km, default=None)
        if nearest_deep is not None and km(nearest_deep) <= NEAREST_DEEPEST_KM:
            return Match(nearest_deep.id, nearest_deep.name, 100.0)
        nearest_upper = min((r for r in placed if r.level == self.min_level), key=km, default=None)
        return Match(nearest_upper.id, nearest_upper.name, 100.0) if nearest_upper else None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))
