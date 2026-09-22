"""
Scrapwisest main agent definition and orchestration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

from app.agent.models import routing_info, super_model
from app.agent.nemotron import everyday_model, resolve_region
from app.agent.persistence import checkpointer, store
from app.agent.prompts.system_prompt_en import SYSTEM_PROMPT_EN
from app.agent.tools.price_estimator import estimate_price
from app.agent.tools.tavily_search import search_scrap_market_news
from app.agent.workflows.subagents import scrap_pipeline_agent
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Runtime context passed to agent execution per-request."""
    picker_id: str


# Composite backend routes /memories/ to per-picker long-term storage
backend = CompositeBackend(
    default=StateBackend(),
    routes={
        "/memories/": StoreBackend(
            namespace=lambda rt: (rt.context.picker_id,),
            store=store,
        ),
    },
)

SYSTEM_PROMPT = SYSTEM_PROMPT_EN

_agents: dict[str, object] = {}


def _is_nebius() -> bool:
    return settings.resolved_llm_provider() == "nebius"


def get_agent(region_id: str | None = None):
    """Build the deep agent on first chat. Nebius can pin a Token Factory region."""
    if _is_nebius():
        cache_key = f"nebius:{resolve_region(region_id)}"
    else:
        cache_key = "xkiro"

    cached = _agents.get(cache_key)
    if cached is not None:
        return cached

    if _is_nebius():
        region = resolve_region(region_id)
        model = everyday_model(region)
        logger.info("Initializing Scrapwisest deep agent on Nebius region %s...", region)
    else:
        model = super_model()
        model_name = routing_info().get("everyday", {}).get("model", "unknown")
        logger.info("Initializing Scrapwisest deep agent with xKiro (%s)...", model_name)

    agent = create_deep_agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        subagents=[scrap_pipeline_agent],
        tools=[estimate_price, search_scrap_market_news],
        context_schema=AgentContext,
        checkpointer=checkpointer,
        store=store,
        backend=backend,
        memory=["/memories/picker_notes.md"],
    )
    _agents[cache_key] = agent
    logger.info("Deep agent initialized (%s).", cache_key)
    return agent


if __name__ == "__main__":
    result = get_agent().invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "bhai maine aaj do kilo plastic becha, teen sau rupay mila, income colony ke qareeb",
                }
            ]
        },
        config={"configurable": {"thread_id": "smoke-test-picker"}},
        context=AgentContext(picker_id="smoke-test-picker"),
    )
    print("Agent execution result:", result)
