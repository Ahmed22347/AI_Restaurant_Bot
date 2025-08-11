
---


# TheHungryUnicorn AI Restaurant Agent

## 📖 Overview
TheHungryUnicorn is an AI-powered conversational agent for handling restaurant bookings via a mock API, with a simple but production-conscious architecture.  
It features:
- **Dual-agent LLM pipeline**:
  - **Receptionist**: Customer-facing, keeps conversation memory, gathers and confirms booking details, and outputs *only* natural speech plus a channel indicator (`to_user` or `to_data_entry`).
  - **Data Entry Worker**: Internal-facing, receives instructions from the Receptionist, converts them into structured schema, and calls the appropriate booking tools.
- **Memory manager** for short-term and long-term conversation persistence.
- **Tooling system** for API calls (check availability, make/change/cancel reservations).
- **Prompt caching** and summarisation for efficiency in long conversations.
- **Flask-based chat UI** with warm, restaurant-themed styling.
- **OpenRouter** integration with Gemini 2.5 Flash Lite as the primary model.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- `pip install -r requirements.txt`
- OpenRouter API key ([get one here](https://openrouter.ai/))
- `.env` file in the project root containing:
  ```env
  OPENROUTER_API_KEY=sk-your-key-here
  OPENROUTER_MODEL=google/gemini-2.5-flash-lite-preview
  ```

### Run the application
```bash
python run.py
```
The chat UI will be available at [http://localhost:5000](http://localhost:5000).

---

## 💡 Design Rationale

### Frameworks & Tools
- **Flask**: Lightweight, familiar, and fast to prototype with; perfect for a focused backend without over-engineering.
- **OpenRouter**: Allows easy switching between multiple LLM providers while standardizing the API format.
- **Gemini 2.5 Flash Lite** (Primary): Chosen for its:
  - **Low cost**: ~$0.10 / 1M input tokens, ~$0.40 / 1M output tokens.
  - **Fast throughput** and low latency (~300–600ms average first token time via OpenRouter tests).
  - **Large context size** for retaining conversation history without aggressive truncation.
  - **Balanced capability** — strong reasoning with minimal hallucination when temperature is kept low.
- **Memory Manager**: Efficiently stores recent history for conversational context and summarizes at session end for long-term memory.

### Other Models Tested
- **Gemini 2.0 Flash**: Faster than 2.5 Lite but less accurate in schema extraction and reasoning.
- **GPT-4**: Excellent accuracy, but latency was significantly higher (~3–5s for responses) and cost made it impractical for rapid user interactions.

---

## ⚙️ Technical Decisions & Trade-offs

### Dual-Agent Architecture
Splitting into **Receptionist** and **Data Entry Worker**:
- **Pros**:
  - Each agent has a simpler role, reducing cognitive complexity for the model.
  - Receptionist outputs *always* predictable JSON (`{"channel":..., "message":...}`), minimizing parsing errors.
  - Data Entry Worker focuses only on mapping confirmed details to API calls.
- **Trade-off**:
  - Slight increase in LLM calls, but offset by improved reliability.

### Memory & Prompt Caching
- Short-term memory: Keeps recent conversation turns for context.
- Long-term memory: Session summaries stored when the user says they're done.
- **Benefit**: Allows rehydrating user context in future chats while keeping prompts small for speed and cost efficiency.

### Scaling
- Stateless HTTP API with Redis (or similar) can handle multi-user conversations.
- Each user has an isolated memory store keyed by `session_id` or user identifier.
- Prompt caching ensures repeated patterns (e.g., asking for date confirmation) are fast to re-serve.

---

## ⚠️ Limitations & Improvements
- Currently assumes perfect tool API availability; would benefit from retry logic and circuit breaking for external calls.
- No proactive suggestion system for upselling — could be an enhancement.
- Does not yet handle multilingual interactions; Gemini supports it but prompts are English-only.
- Tool outputs are mocked; real-world integration would require secure API auth and error handling.

---

## 🔒 Security Considerations
- **Environment variables** are loaded from `.env` to avoid hardcoding secrets.
- No PII is persisted beyond booking data.
- Flask app should be run behind HTTPS in production.
- Model prompt injection risks mitigated via:
  - Strict JSON schema validation for both Receptionist and Data Entry Worker outputs.
  - Temperature kept low for structured outputs.

---

## 🧪 Testing Notes
- Primary testing done with **Gemini 2.5 Flash Lite** via OpenRouter.
- Secondary tests with **Gemini 2.0 Flash** (faster, less accurate) and **GPT-4** (more accurate, much slower).
- OpenRouter metrics (as of August 2025):
  - Gemini 2.5 Flash Lite: ~0.1s–0.3s first token latency, ~100–200 tokens/sec throughput.
  - Gemini 2.0 Flash: Slightly faster, but weaker schema accuracy.
  - GPT-4: ~3–5s latency, ~30–60 tokens/sec throughput.
- System tested with 10+ simulated concurrent users to confirm multi-session stability.

---

## 📂 Repository Structure
```
/app
  agent.py         # Orchestrates Receptionist ↔ Data Entry Worker ↔ Tools
  tools.py         # Booking API calls (mocked)
  memory.py        # Short/long-term conversation memory
  llm.py           # LLM interface via OpenRouter
  static/          # CSS, JS, images
  templates/       # HTML chat UI
.env
requirements.txt
README.md
```



