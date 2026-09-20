# ScrapSense

A scrap-price copilot waste pickers would actually use.

Message what you sold, or ask what something is worth, in English, Urdu, or Roman Urdu. ScrapSense turns that messy field note into a trusted price — and remembers the neighborhood so the next check is faster.

Built for the **Best Apps and Agents** track: a real workflow, powered by **Nemotron on Nebius Token Factory**, with Ultra reserved for hard judgment and Nano/Super on the everyday calls.

---

## Why this exists

Dealers already know the market. Pickers usually don't. Their only price reference is often the same person they are negotiating with. Research on informal recycling markets has found pickers paid as little as **59.5% of materials' true value**.

The product is not "point a camera at scrap." It is: **walk into the next sale with a number**.

Two things a picker does every day:

1. **Ask a price** — *plastic ka rate kya hai*
2. **Log a sale** — *maine 2 kilo plastic becha, 300 rupay mile, income colony ke qareeb*

The agent routes those itself. Price math and cheap fraud checks stay in code. LLMs only run where judgment is required.

---

## MVP (what works now)

| Flow | What happens |
| --- | --- |
| Price question | Super calls `estimate_price` (local reports → city → seed prices). One short reply in the picker's language. |
| Sale report | Nano extracts material / kg / PKR / area. Rules validate it. Isolation Forest can flag weird price+quantity. **Ultra** only runs if those cheaper tiers already flagged the report. |
| Follow-up | If a field is missing, Super asks **one** specific question. Conversation stays on the picker id. |
| Photo | Optional helper. CNN if a model is present; otherwise the agent just asks what it is. No LLM spent on pixels. |

Out of scope for this MVP (and not needed to demo): forecasting, a reporter-trust score, a trained CNN in the default deploy.

---

## Nemotron routing (Token Factory)

The track brief is the architecture: **Ultra when you need serious reasoning. Nano or Super for the fast, everyday calls.** That keeps the chat responsive and the credits on the calls that matter.

| Call | Model | Why |
| --- | --- | --- |
| Extract a messy sale message | **Nemotron 3 Nano** `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | High volume, structured, cheap |
| Picker chat, tools, memory | **Nemotron 3 Super** `nvidia/nemotron-3-super-120b-a12b` | Everyday copilot loop |
| "Is this flagged sale real or junk?" | **Nemotron 3 Ultra** `nvidia/Nemotron-3-Ultra-550b-a55b` | Real judgment, rare |

All three go through Nebius Token Factory (OpenAI-compatible). Nano is on `eu-north1`; Super and Ultra on `us-central1`. Override with environment variables if your project is pinned to one region.

```text
Picker message

      │
      ▼

Super (everyday) ── price question ──► estimate_price (no LLM)
      │
      └── sale report ──► Nano extract ──► rules ──► Isolation Forest
                                                  │
                                            flagged? ── yes ──► Ultra judge
                                                  │
                                                no ──► store + confirm
