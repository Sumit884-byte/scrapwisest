# Nebius Token Factory & NVIDIA Nemotron Feedback

Feedback compiled during the development of **Scrapwisest** for the Nebius x NVIDIA Global AI Hackathon.

---

## 1. What Worked Exceptionally Well

### ⚡ Low-Latency OpenAI Compatibility
- **Seamless Integration:** Connecting `langchain-openai` to `https://api.tokenfactory.eu-north1.nebius.com/v1/` and `us-central1` required zero custom adapters.
- **Model Tiering Utility:**
  - **Nemotron-3-Nano (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`):** Excellent performance for rapid structured JSON extraction (`RawExtraction`). Highly cost-effective for high-volume text processing.
  - **Nemotron-3-Super (`nvidia/nemotron-3-super-120b-a12b`):** Outstanding conversational tone and tool execution capabilities (`estimate_price`). Handled Urdu and Roman Urdu speech-to-text input seamlessly.
  - **Nemotron-3-Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`):** Strong deep reasoning when adjudicating flagged edge-case anomaly reports.

### 🎯 Multi-Model Routing Strategy
- Splitting tasks across Nano, Super, and Ultra allowed us to maintain sub-second responsiveness for field pickers while conserving API credits and preserving Ultra exclusively for complex reasoning.

---

## 2. Feature Requests & Improvements

1. **Unified Regional Endpoints:**
   - Currently, Nano is hosted on `eu-north1` while Super and Ultra reside on `us-central1`. Having a unified multi-region gateway URL or auto-failover routing across regions would simplify client configuration.

2. **Structured Output Consistency on Nano:**
   - Under heavy load, `Nemotron-3-Nano` occasionally drops trailing fields in strict Pydantic schema validation when parsing complex mixed-language strings. Providing native JSON mode enforcement parameters in the Token Factory proxy help guarantee strict schema adherence.

3. **Streamlined Function Calling Metadata:**
   - Expanding telemetry in token factory response headers (e.g., token usage breakdowns per tool call) would help developers track costs per subagent workflow in real time.

---

## 3. Overall Impression

Nebius Token Factory provided an incredibly reliable, fast, and accessible platform to serve NVIDIA Nemotron open-weights models. It enabled us to build a production-grade multi-agent AI system for marginalized waste pickers with high accuracy and low latency.
