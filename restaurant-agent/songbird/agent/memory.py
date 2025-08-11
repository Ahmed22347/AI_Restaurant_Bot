import os
import json
from datetime import datetime

# Directory to store long-term memory
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)


class Memory:
    """Handles per-user memory: short-term and long-term."""
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.history = []  # Short-term memory: active session
        self.summary_file = os.path.join(DATA_DIR, f"{user_id}_memory.jsonl")

    # ---- SHORT TERM MEMORY ----

    def add_user_message(self, msg: str):
        self.history.append({"role": "user", "content": msg})

    def add_bot_message(self, msg: str):
        self.history.append({"role": "assistant", "content": msg})

    def add_tool_result(self, msg: str):
        self.history.append({"role": "tool", "content": msg})

    def get_history(self):
        return self.history

    def clear(self):
        self.history = []

    # ---- LONG TERM MEMORY ----

    def store_summary(self, summary: str):
        """Appends a summarized conversation to the user’s memory file."""
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": summary,
            "messages": self.history
        }

        with open(self.summary_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def get_last_summary(self) -> str:
        """Returns the most recent summary string, if it exists."""
        if not os.path.exists(self.summary_file):
            return None

        try:
            with open(self.summary_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if not lines:
                    return None
                last_record = json.loads(lines[-1])
                return last_record.get("summary")
        except Exception:
            return None


class MemoryManager:
    """Manages all user memories."""
    def __init__(self):
        self.user_memories = {}

    def get_memory(self, user_id: str) -> Memory:
        """Get or create memory instance for a user."""
        if user_id not in self.user_memories:
            self.user_memories[user_id] = Memory(user_id)
        return self.user_memories[user_id]
