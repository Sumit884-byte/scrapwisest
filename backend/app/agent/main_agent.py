"""
ScrapSense main agent definition and orchestration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

from app.agent.models import routing_info, super_model
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

_agent = None


def get_agent():
    """Build the deep agent copilot on first chat, not at import time."""
    global _agent
    if _agent is None:
        provider_name = settings.LLM_PROVIDER
        model_name = routing_info().get("everyday", {}).get("model", "unknown")
        logger.info("Initializing ScrapSense deep agent with %s (%s)...", provider_name, model_name)
        _agent = create_deep_agent(
            model=super_model(),
            system_prompt=SYSTEM_PROMPT,
            subagents=[scrap_pipeline_agent],
            tools=[estimate_price, search_scrap_market_news],
            context_schema=AgentContext,
            checkpointer=checkpointer,
            store=store,
            backend=backend,
            memory=["/memories/picker_notes.md"],
        )
        logger.info("Deep agent initialized successfully.")
    return _agent


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
