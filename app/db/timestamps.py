# app/db/timestamps.py
from sqlalchemy import event
from . import Base
from ..utils.timez import now_local

@event.listens_for(Base, "before_insert", propagate=True)
def _set_created_updated(mapper, connection, target):
    now = now_local().replace(tzinfo=None)
    if hasattr(target, "created_at") and getattr(target, "created_at", None) is None:
        target.created_at = now
    if hasattr(target, "updated_at") and getattr(target, "updated_at", None) is None:
        target.updated_at = now

@event.listens_for(Base, "before_update", propagate=True)
def _touch_updated(mapper, connection, target):
    if hasattr(target, "updated_at"):
        target.updated_at = now_local().replace(tzinfo=None)
