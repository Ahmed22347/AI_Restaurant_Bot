# app/agent/llm.py
from datetime import datetime
from dotenv import load_dotenv
import os
import json
import requests
from typing import List, Dict, Union, Optional, Tuple

"""
Two-actor LLM orchestrator over OpenRouter:

- Receptionist (customer-facing, has memory):
    ALWAYS returns a SINGLE JSON object with EXACTLY two keys:
      {
        "channel": "to_user" | "to_data_entry",
        "message": "<human-friendly speech>"
      }
    • Use "to_user" while gathering/confirming details.
    • Use "to_data_entry" ONLY when message contains all confirmed details ready for action.
    • No extra keys, no prose outside JSON.

- Data Entry Worker (back-office):
    Receives the receptionist's 'message' (natural language), extracts structured fields,
    validates against tool schemas, and returns a strict tool_call JSON of the form:
      {
        "tool_call": {
          "name": "<tool_name>",
          "args": { ... }
        }
      }

"""


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    # Default to Gemini 2.5 Flash Lite; override via env OPENROUTER_MODEL if desired.
    #"google/gemini-2.5-flash-lite-preview"
    "google/gemini-2.5-flash-lite"
    #"mistralai/devstral-small"
    #"google/gemma-3n-e2b-it:free"
    #"deepseek/deepseek-r1-0528-qwen3-8b",
    #"qwen/qwen3-4b:free"
    #"openai/gpt-4.1-nano"
    #"openai/gpt-4.1-mini"
    #"google/gemini-2.5-flash"
    #"google/gemini-2.0-flash-001"
)
NOT_GEMINI_MODEL = False
# Schemas keyed by tool function name (the worker emits this as "name")
SCHEMAS = {
    "check_availability": {
        "required": ["date", "people"],
        "optional": []
    },
    "make_reservation": {
        "required": ["date", "time", "people"],
        "optional": ["SpecialRequests", "IsLeaveTimeConfirmed", "RoomNumber", "Customer[Title]","Customer[FirstName]","Customer[Surname]", "Customer[Email]","Customer[Mobile]","Customer[Phone]", "Customer[MobileCountryCode]","Customer[PhoneCountryCode]", "Customer[ReceiveEmailMarketing]", "Customer[ReceiveSmsMarketing]"]
    },
    "check_reservation": {
        "required": ["booking_reference"],
        "optional": []
    },
    "modify_reservation": {
        "required": ["booking_reference"],
        "optional": ["VisitDate", "VisitTime", "PartySize", "SpecialRequests", "IsLeaveTimeConfirmed"]
    },
    "cancel_reservation": {
        "required": ["booking_reference"],
        "optional": []
    }
}
load_dotenv()

class GeminiLLM:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY",)
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set.")
        self.model = DEFAULT_MODEL

    # ---------------- Public API ----------------

    def process(self, history: List[Dict[str, str]]) -> Union[str, dict]:
        """
        Orchestrates:
          1) Receptionist → returns {"channel":..., "message":...}
          2) If channel == "to_user": return message (string)
             If channel == "to_data_entry": run worker → return {"tool_call": ...} OR fallback question (string)
        """
        rec_obj = self._receptionist(history)

        # Fail-safe if receptionist couldn't be parsed:
        if not rec_obj:
            return "I’m having trouble understanding,could you confirm the date, time, and (if booking) the number of people?"

        channel = rec_obj.get("channel", "to_user")
        msg = rec_obj.get("message", "").strip()

        if channel == "to_user" or not msg:
            # Customer-facing response
            return msg or "Could you share a bit more detail so I can help?"

        if channel == "to_data_entry":
            # Convert receptionist speech → strict tool_call
            tool_call = self._data_entry_worker(msg, history)
            
            if tool_call and self._validate_tool_call(tool_call):
                return {"tool_call": tool_call}
                        
            print(f"tool: {tool_call}")
            # If worker failed validation, ask for missing information
            missing = self._missing_from_tool_call(tool_call) if tool_call else []
            if missing:
                return self._compose_missing_question(missing)
            print(f"!!!!!Error!!!!!!!")
            # Generic fallback
            return "Sorry, I encountered some technical errors, can you resate your request?"

        # Unknown channel → treat as customer-facing
        return msg or "Could you clarify your request?"

    def summarize(self, history: List[Dict[str, str]]) -> str:
        """Summarize conversation for long-term memory."""
        system = (
            "Summarize this conversation focusing on intents, any bookings/changes, "
            "booking references, dates/times/party sizes, and final outcomes. Keep it concise."
        )
        if len(history)==1 or NOT_GEMINI_MODEL:
            content = str(history)
        else:
            content = []
            for i in range(len(history)):
                if i == len(history)-2:
                    text_dict={"type": "text", "text": str(history[i]),"cache_control": {"type": "ephemeral"}}
                else:
                    text_dict={"type": "text", "text": str(history[i])}
                content.append(text_dict)

        raw = self._call_openrouter( 
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
            temperature=0.3
        )
        return raw or "[Summary unavailable]"

    # ---------------- Receptionist ----------------

    def _receptionist(self, history: List[Dict[str, str]]) -> Optional[dict]:
        """
        Receptionist MUST return exactly:
          {"channel":"to_user" | "to_data_entry", "message":"<human-friendly speech>"}
        """
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%H:%M")
        current_context = f"Today is {date_str}, and the current time is {time_str}."
        system = (
            f"{current_context}\n"
            "You are a warm, efficient Receptionist for The Hungry Unicorn (a restaurant).\n"
            "Keep short-term conversation memory.\n"
            "You provide the following services:\n"
            f"{SCHEMAS}\n"
            "You must ALWAYS output ONE JSON object with EXACTLY two keys:\n"
            "  1) channel: 'to_user' or 'to_data_entry'\n"
            "  2) message: a single string of natural, human-friendly speech\n\n"
            "Rules:\n"
            "- Use 'to_user' to gather any missing mandatory details or to present availability/options.\n"
            "- Use 'to_data_entry' ONLY when all mandatory details for exactly ONE service action are present.\n"
            "- Never include more than one service action in a single 'to_data_entry' message.\n"
            "- Ask only for mandatory information; do NOT ask optional questions.\n"
            "- Do NOT repeat or ask the user to confirm information they already provided.\n"
            "- Do NOT claim a booking/change is done—only tools/back office confirm that.\n"
            "- Use the current date/time to resolve relative dates (e.g., today, tomorrow, "
            "  this weekend = the upcoming Saturday and Sunday).\n"
            " You may process a request that requires more than one service, process only one at a time, and get back to the user when the entire request is complete\n"
            "  Always make the dates of booking, modifying or availabilty clear to the user.\n"
            "- Keep responses concise, friendly, and helpful.\n"
            "- Do NOT add any other keys and do NOT include any text outside the JSON.\n\n"
            "Output Examples:\n"
            "{\"channel\":\"to_user\",\"message\":\"Sure—what date and time would you like to book?\"}\n"
            "{\"channel\":\"to_data_entry\",\"message\":\"Please make a resevation on 2025-08-10 at 7:00 PM for 4 people.\"}\n"
        )


        # Try up to two attempts to get clean JSON-only output
        for _ in range(2):


            if len(history)==1 or NOT_GEMINI_MODEL:
                content = str(history)
            else:
                content = []
                for i in range(len(history)):
                    if i == len(history)-2:
                        text_dict={"type": "text", "text": str(history[i]),"cache_control": {"type": "ephemeral"}}
                    else:
                        text_dict={"type": "text", "text": str(history[i])}
                    content.append(text_dict)

            raw = self._call_openrouter( 
                messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
                temperature=0.2
            )
            obj = self._safe_json_load(raw)
            if self._validate_receptionist_json(obj):
                return obj
            print(f"raw: {raw}")
        # Fallback
        return {"channel": "to_user", "message": "Could you confirm the date and time (and number of people if booking)?"}

    def _validate_receptionist_json(self, obj: Optional[dict]) -> bool:
        if not isinstance(obj, dict):
            return False
        if set(obj.keys()) != {"channel", "message"}:
            return False
        if obj["channel"] not in ("to_user", "to_data_entry"):
            return False
        if not isinstance(obj["message"], str):
            return False
        return True

    # ---------------- Data Entry Worker ----------------

    def _data_entry_worker(self, receptionist_speech: str, history: List[Dict[str, str]]) -> Optional[dict]:
        """
        Convert receptionist speech → strict tool_call JSON.
        STRICT OUTPUT (no prose, no markdown, just JSON):
        {
          "tool_call": {
            "name": "<check_availability|make_reservation|check_reservation|modify_reservation|cancel_reservation>",
            "args": { ...validated args... }
          }
        }
        """
        system = (
            "You are the Data Entry Worker. You do NOT converse with customers.\n"
            "Your ONLY job is to convert the Receptionist's natural-language instruction into a SINGLE JSON object named tool_call.\n"
            "Select the correct tool and extract validated arguments.\n\n"
            f"Tools and arguments keys:{SCHEMAS}\n"
            "You must always return only one tool call ever, even if you receive a request for more than one."
            "All arguments mandatory and optional should be in the agruments field, with the argument names being keys.\n"
            "Time must be in HH:MM"
            "STRICT OUTPUT: JSON ONLY (no markdown, no prose):\n"
            "{\n"
            "  \"tool_call\": {\n"
            "    \"name\": \"<tool_name>\",\n"
            "    \"args\": { ... }\n"
            "  }\n"
            "}"
        )

        print(f"Receptionist speech:{receptionist_speech}")
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Receptionist speech (final, confirmed):\n"
                    f"\"\"\"\n{receptionist_speech}\n\"\"\"\n\n"
                ),
            },
        ]

        # Two attempts for robustness
        for _ in range(2):
            raw = self._call_openrouter(messages, temperature=0.1)
            tool_call = self._extract_tool_call(raw)
            print(f"tool_call: {tool_call}")
            if tool_call:
                # Normalize simple coercions here if needed (e.g., integer party size)
                if "people" in tool_call.get("args", {}):
                    try:
                        tool_call["args"]["people"] = int(tool_call["args"]["people"])
                    except Exception:
                        pass
                return tool_call
        return None

    # ---------------- Validation & Helpers ----------------

    def _validate_tool_call(self, tool_call: dict) -> bool:
        """Validate tool name & required args; enforce modify rule."""
        try:
            name = tool_call.get("name")
            args = tool_call.get("args", {}) or {}
            if name not in SCHEMAS:
                return False
            required = SCHEMAS[name]["required"]
            if not all(self._present(args.get(k)) for k in required):
                return False
            # people -> int coercion final check
            if "people" in args:
                try:
                    args["people"] = int(args["people"])
                    tool_call["args"] = args
                except Exception:
                    return False
            return True
        except Exception:
            return False

    def _missing_from_tool_call(self, tool_call: Optional[dict]) -> List[str]:
        if not tool_call:
            return []
        name = tool_call.get("name")
        args = tool_call.get("args", {}) or {}
        if name not in SCHEMAS:
            return []
        missing = [k for k in SCHEMAS[name]["required"] if not self._present(args.get(k))]
        if name == "modify_reservation" and not (self._present(args.get("new_date")) or self._present(args.get("new_time"))):
            missing.append("new_date_or_new_time")
        return missing

    def _compose_missing_question(self, missing: List[str]) -> str:
        if not missing:
            return "I need a bit more detail to proceed—could you confirm the date and time?"
        if "new_date_or_new_time" in missing:
            return "Would you like to change the date, the time, or both for your reservation? Please provide the new values."
        if len(missing) == 1:
            return f"Got it, could you please share the {missing[0].replace('_',' ')}?"
        return "Thanks! I still need: " + ", ".join(m.replace('_',' ') for m in missing[:2]) + "."

    def _present(self, v) -> bool:
        return v is not None and str(v).strip() != ""

    def _safe_json_load(self, text: Optional[str]) -> Optional[dict]:
        if not text:
            print(f"json_text {text}")
            return None
        s = text.strip()
        # tolerate accidental fences
        if s.startswith("```"):
            s = s.strip("`")
            if s.lower().startswith("json"):
                s = s[4:].strip()
        try:
            return json.loads(s)
        except Exception:
            return None

    def _extract_tool_call(self, text: Optional[str]) -> Optional[dict]:
        """Parse a JSON object with a 'tool_call' top key. No markdown expected."""
        if not text:
            return None
        # Direct JSON first
        print(f"extract data text: {text}\n")
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tool_call" in data and isinstance(data["tool_call"], dict):
                return data["tool_call"]
        except Exception:
            pass
        # Relax: locate a JSON object within text
        lb = text.find("{")
        rb = text.rfind("}")
        if lb != -1 and rb != -1 and rb > lb:
            try:
                data = json.loads(text[lb:rb+1])
                if isinstance(data, dict) and "tool_call" in data and isinstance(data["tool_call"], dict):
                    return data["tool_call"]
            except Exception:
                pass
        return None

    # ---------------- OpenRouter plumbing ----------------

    def _call_openrouter(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3
    ) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }
        try:
            resp = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=50)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Error , LLM call {e}")
            return None
