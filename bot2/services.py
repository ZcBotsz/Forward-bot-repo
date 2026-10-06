"""Small shared service container passed to handler registration functions."""

from __future__ import annotations

from dataclasses import dataclass

from pyrogram import Client

from .config import Settings
from .db import Database
from .engine import ForwardEngine


@dataclass(slots=True)
class Services:
    config: Settings
    db: Database
    app: Client
    engine: ForwardEngine
