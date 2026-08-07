"""
Persistence layer for ScrapSense's agent memory.

Two distinct things live here, and they are NOT interchangeable:

- checkpointer (short-term / episodic memory)
    Keyed by thread_id. Holds the full back-and-forth of one ongoing
    picker conversation, so a follow-up like "which neighborhood?" ->
    "income colony" resolves correctly instead of arriving as a
    contextless new message. Without this, /chat has no way to answer
    its own `needs_confirmation` follow-up questions.

- store (long-term / semantic memory)
    Keyed by picker_id, independent of thread_id. Holds small persistent
    facts about a picker -- usual neighborhood, preferred language/
    register -- exposed to the agent as a file under /memories/, so they
    carry across separate conversations (new day, new session).

Both are SQLite-backed, matching the pattern already used in
backend/db_store.py -- no new infra for the hackathon build.

KNOWN LIMITATION: LangGraph's own docs say SqliteSaver / SqliteStore are
"meant for lightweight, synchronous use cases (demos and small projects)
and do not scale to multiple threads." FastAPI serves each /chat request
off asyncio.to_thread's threadpool, so concurrent requests CAN hit these
connections concurrently -- fine at hackathon/field-testing scale, but
swap for PostgresSaver / PostgresStore (same package family, same API)
before real concurrent traffic. Same upgrade the project overview already
flags for backend/db_store.py.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore

logger = logging.getLogger(__name__)

_DATA_DIR = Path("data")
_DATA_DIR.mkdir(parents=True, exist_ok=True)

CHECKPOINT_DB_PATH = _DATA_DIR / "checkpoints.db"
MEMORY_DB_PATH = _DATA_DIR / "long_term_memory.db"

# check_same_thread=False -- required since requests are handled off
# FastAPI's threadpool (see main.py's asyncio.to_thread calls), so a
# different OS thread may use this connection on each call. This does
# NOT make concurrent *writes* safe -- see module docstring above.
_checkpoint_conn = sqlite3.connect(str(CHECKPOINT_DB_PATH), check_same_thread=False)
_memory_conn = sqlite3.connect(
    str(MEMORY_DB_PATH),
    check_same_thread=False,
    isolation_level=None,  # autocommit; SqliteStore manages BEGIN/COMMIT itself
)

checkpointer = SqliteSaver(conn=_checkpoint_conn)
checkpointer.setup()

store = SqliteStore(conn=_memory_conn)
store.setup()

logger.info(
    "Agent persistence initialized: checkpoints=%s, long_term_memory=%s",
    CHECKPOINT_DB_PATH,
    MEMORY_DB_PATH,
)