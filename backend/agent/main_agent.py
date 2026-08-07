import logging
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from langchain_mistralai import ChatMistralAI
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

from agent.subagents.report_intaker import scrap_pipeline_agent
from agent.tools.price_estimator import estimate_price
from agent.persistence import checkpointer, store

logger = logging.getLogger(__name__)

# ---- chat model -----

mistral_model = ChatMistralAI(
    model="mistral-medium-3-5",
    temperature=0,
    model_kwargs={"reasoning_effort": "high"},
)


# ---- runtime context ----
# picker_id identifies WHO's messaging, independent of WHICH conversation
# thread they're in. main.py resolves it per-request and passes it via
# `context=` on agent.invoke(). It drives long-term memory's namespace
# below -- separate from the LangGraph thread_id (set via
# `config={"configurable": {"thread_id": ...}}`) so short-term and
# long-term memory stay independently reasoned about.

@dataclass
class AgentContext:
    picker_id: str


# ---- backend: routes /memories/ to per-picker long-term storage ----
# Everything else (scratch files, todos) stays in StateBackend, i.e.
# thread-scoped. Only /memories/ persists across threads, namespaced by
# picker_id so picker A's notes never leak into picker B's conversation.

backend = CompositeBackend(
    default=StateBackend(),
    routes={
        "/memories/": StoreBackend(
            namespace=lambda rt: (rt.context.picker_id,),
            store=store,
        ),
    },
)


# ---- main agent ----
# NOTE: image classification deliberately does NOT live here as a tool.
# "Was a photo attached?" is a boolean, not a judgment call -- it's resolved
# in main.py before the agent is ever invoked, same philosophy as the
# deterministic tiers in the anomaly agent. The agent only ever sees the
# *result* of classification as a plain fact, never the image or a tool.

SYSTEM_PROMPT = """\
# Role

You are the ScrapSense intake assistant. Waste pickers message you in English, Urdu, or Roman Urdu, for two reasons:

1. **Reporting a completed sale** — what they sold, how much, what they were paid.
2. **Asking what a material is worth** — before they've sold anything.

# Case 1: Logging a Completed Sale

Call the `scrap_report_pipeline` subagent with the picker's raw message. It returns a `price_report`, and — if the report was clean enough to score — an anomaly `verdict`.

Respond based on what comes back:

- **`price_report.needs_confirmation` is set** → Don't guess at missing or unclear fields yourself. Ask one short, specific follow-up question that resolves `confirmation_reason` (e.g. the exact weight or price), in the same language and register the picker used.
- **`verdict.is_anomalous` is `false`** → Confirm the sale was logged in one friendly sentence. Don't mention the checks that ran.
- **`verdict.is_anomalous` is `true`** → Still confirm the sale was logged, but gently ask about the specific thing that looks unusual (per `verdict.reason`), so a human reviewer isn't the picker's only recourse.

# Case 2: A Price Question, No Sale to Log

If the picker is asking what something is worth (e.g. *"plastic ka rate kya hai"*) rather than reporting a completed sale:

- Call `estimate_price` with the material and their neighborhood — **not** the pipeline subagent.
- Give the price as a plain, approximate figure per kg, in one short sentence, in their language.
- Never mention confidence scores, tiers, or how it was calculated.
- If you can't tell which material or neighborhood they mean, ask one short clarifying question first.

# Detected Material (from a photo, if one was attached)

If the message contains a line like `[detected_material: <material>, confidence: <0-1>]`, a photo was attached and already identified before you saw this message. You have no tool to classify images yourself — never ask the picker what the material is if this tag is present, and never mention that a photo, a model, or a confidence score was involved.

Just use `<material>` as the material type for whatever they're actually asking:
- Reporting a sale → treat it as the material for Case 1, don't ask them to name it again.
- Asking the price → call `estimate_price` with this material directly.
- Neither (rare) → confirm what the material is in one short sentence and stop there.

If instead you see `[image_analysis_failed]`, a photo came in but couldn't be read. Don't mention the failure — just proceed as if no photo was attached (ask for the material the normal way if you need it for Case 1).

# Long-Term Memory

You have a memory file at `/memories/picker_notes.md`, private to this picker, that persists across separate conversations.

- If the picker mentions something worth remembering for next time — their usual neighborhood, their preferred language/register, or a material they sell often — save or update it there with your file tools.
- Keep it to a few short bullet points, not a transcript. Update it, don't append duplicates.
- Never write anything sensitive (no phone numbers, no real names) — the picker_id already scopes this file privately to them.
- If the file already has a neighborhood or language preference noted, use it silently — reply in their preferred register, or skip re-asking something they've already told you — without mentioning that you checked a memory file.

# Output Rules

- Keep replies short — pickers are messaging from the field, often on a shared or low-end phone.
- Never show the picker raw JSON, `verdict` objects, `PriceEstimate` objects, internal tags, image paths, or internal field names.
"""

logger.info("Initializing ScrapSense deep agent with ChatMistralAI model...")
agent = create_deep_agent(
    model=mistral_model,
    system_prompt=SYSTEM_PROMPT,
    subagents=[scrap_pipeline_agent],
    tools=[estimate_price],
    context_schema=AgentContext,
    checkpointer=checkpointer,
    store=store,
    backend=backend,
    memory=["/memories/picker_notes.md"],
)
logger.info("Deep agent initialized successfully.")

# ---------------------------------------------------------------------------
# Manual smoke test. Guarded so importing `agent` (e.g. from the FastAPI app)
# never fires a live model call on its own.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import textwrap
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    def pretty_print_result(result):
        for msg in result["messages"]:
            print("─" * 80)
            if isinstance(msg, HumanMessage):
                print("👤 USER")
                print(msg.content)
            elif isinstance(msg, AIMessage):
                model = msg.response_metadata.get("model_name", "?")
                print(f"🤖 AI  ({model})")
                if isinstance(msg.content, list):
                    for block in msg.content:
                        if block.get("type") == "thinking":
                            text = "".join(t.get("text", "") for t in block.get("thinking", []))
                            print("  💭 thinking:")
                            print(textwrap.indent(text.strip(), "     "))
                        elif block.get("type") == "text":
                            print("  💬 text:")
                            print(textwrap.indent(block["text"].strip(), "     "))
                elif msg.content:
                    print(textwrap.indent(msg.content.strip(), "  "))
                for tc in msg.tool_calls:
                    print(f"  🔧 tool_call -> {tc['name']}")
                    print(textwrap.indent(json.dumps(tc["args"], indent=2), "     "))
            elif isinstance(msg, ToolMessage):
                print(f"🛠️  TOOL RESULT  ({msg.tool_call_id})")
                try:
                    parsed = json.loads(msg.content)
                    print(textwrap.indent(json.dumps(parsed, indent=2), "  "))
                except (json.JSONDecodeError, TypeError):
                    print(textwrap.indent(str(msg.content), "  "))
            print()

    result = agent.invoke(
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
    pretty_print_result(result)