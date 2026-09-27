"""Walking the region tree: which places sit under a given place, whatever each level is called."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Region


def country_regions(db: Session, country_code: str) -> dict[str, Region]:
    return {r.id: r for r in db.scalars(select(Region).where(Region.country_code == country_code))}


def subtree_ids(regions: dict[str, Region], root_id: str) -> set[str]:
    """The place itself and every place below it."""
    children: dict[str, list[str]] = {}
    for region in regions.values():
        if region.parent_id:
            children.setdefault(region.parent_id, []).append(region.id)
    found, stack = set(), [root_id]
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(children.get(current, []))
    return found
