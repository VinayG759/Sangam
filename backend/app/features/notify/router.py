"""Admin endpoint that sends pending status updates. Called on a schedule (see keepalive workflow)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.core.security import require_admin
from app.features.notify.service import send_updates

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/notify")
def notify(db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    return send_updates(db, pack)
