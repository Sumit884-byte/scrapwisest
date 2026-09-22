"""
Persistence layer for Scrapwisest agent memory.
Manages episodic short-term conversation checkpoints and per-picker semantic memory.
"""

from __future__ import annotations

import logging
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore

from app.core.config import settings

logger = logging.getLogger(__name__)

settings.CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.MEMORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_checkpoint_conn = sqlite3.connect(
    str(settings.CHECKPOINT_DB_PATH),
    check_same_thread=False,
)
_memory_conn = sqlite3.connect(
    str(settings.MEMORY_DB_PATH),
    check_same_thread=False,
    isolation_level=None,  # autocommit
)

checkpointer = SqliteSaver(conn=_checkpoint_conn)
checkpointer.setup()

store = SqliteStore(conn=_memory_conn)
store.setup()

logger.info(
    "Agent persistence initialized: checkpoints=%s, long_term_memory=%s",
    settings.CHECKPOINT_DB_PATH,
    settings.MEMORY_DB_PATH,
)
