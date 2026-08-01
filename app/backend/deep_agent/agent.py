from langchain_mistralai import ChatMistralAI
from deepagents import create_deep_agent
from app.backend.agents.report_intaker import scrap_pipeline_agent

from app.backend.agents.price_estimator import estimate_price

from dotenv import load_dotenv
load_dotenv()


# ---- chat model -----

mistral_model = ChatMistralAI(
    model="mistral-medium-3-5",
    temperature=0,
    model_kwargs={"reasoning_effort": "high"},
)


# ---- main agent ----

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

# Output Rules

- Keep replies short — pickers are messaging from the field, often on a shared or low-end phone.
- Never show the picker raw JSON, `verdict` objects, `PriceEstimate` objects, or internal field names.
"""

agent = create_deep_agent(
    model=mistral_model,
    system_prompt=SYSTEM_PROMPT,
    subagents=[scrap_pipeline_agent],
    tools=[estimate_price],
)

result = agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "bhai maine aaj do kilo plastic becha, teen sau rupay mila, income colony ke qareeb",
            }
        ]
    }
)

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

            # content can be a plain string or a list of blocks (thinking/text)
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


pretty_print_result(result)