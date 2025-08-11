import json
from songbird.agent.memory import MemoryManager
from songbird.agent.llm import GeminiLLM
from songbird.agent import tools
from songbird.agent.tools import ToolError


class ConversationalAgent:
    def __init__(self):
        self.llm = GeminiLLM()
        self.tool_registry = {
            "check_availability": tools.check_availability,
            "make_reservation": tools.make_reservation,
            "check_reservation": tools.check_reservation,
            "modify_reservation": tools.modify_reservation,
            "cancel_reservation": tools.cancel_reservation
        }
        self.memory_manager = MemoryManager()

    def start_conversation(self, user_id: str) -> str:
        """Returns a welcome message based on prior user history."""
        memory = self.memory_manager.get_memory(user_id)
        user_summary = memory.get_last_summary()

        if user_summary:
            greeting = f"👋 Welcome back! Last time, you said: \"{user_summary}\". How can I assist you today?"
        else:
            greeting = "👋 Hello! I’m your restaurant assistant. How can I help you make or manage a reservation?"

        memory.add_bot_message(greeting)
        return greeting

    def handle_user_input(self, user_id: str, user_input: str) -> str:
        """Processes user input and returns LLM or tool result."""

        memory = self.memory_manager.get_memory(user_id)
        memory.add_user_message(user_input)

        # LLM decides what to do: ask more, respond, or call tool
        llm_reply = self.llm.process(memory.get_history())
        # CASE 1: Structured tool call
        i=0
        while isinstance(llm_reply, dict) and "tool_call" in llm_reply and i<4:
            i+=1
            print("tool called")
            tool_result = self.execute_tool(llm_reply["tool_call"])
            memory.add_tool_result(tool_result)
            llm_reply = self.llm.process(memory.get_history())
        if i>3:
            print(f"!!Error!!")
            llm_reply = "Sorry, I have encountered an error, please can you repeat your request"

        print(f"llm_reply{llm_reply}")
        memory.add_bot_message(llm_reply)
        return llm_reply

    def execute_tool(self, tool_call: dict) -> str:
        """Handles actual tool execution and safe error reporting."""
        tool_name = tool_call.get("name")
        args = tool_call.get("args", {})

        tool_func = self.tool_registry.get(tool_name)
        if not tool_func:
            print(f"tool error,")
            return f"[Error] Unknown tool: `{tool_name}`"

        try:
            result = tool_func(**args)
            return result
        except ToolError as e:
            print(f"Toolerror:{e}")
            return f"[Tool Error] {str(e)}"
        except Exception as e:
            print(f"error:{e}")
            return f"[Execution Error] Something went wrong while using `{tool_name}`: {str(e)}"

    def end_session(self, user_id: str) -> str:
        """Summarizes conversation and clears short-term memory."""
        memory = self.memory_manager.get_memory(user_id)
        summary = self.llm.summarize(memory.get_history())
        memory.store_summary(summary)
        memory.clear()
        return f"📝 Thanks for chatting! I've saved this summary: \n\n\"{summary}\""
