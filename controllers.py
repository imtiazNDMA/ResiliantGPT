import os
import io
import base64
from uuid import uuid4
from config import Config
from services.llm_service import LLMService
from services.vector_store import VectorStore
from werkzeug.datastructures import FileStorage
from services.speech_service import transcribe
from typing import Optional, Union, List, Any, Dict


from tools.search_tool import SearchTool
from tools.image_tool import ImageTool
from services.llm_service import LLMService

class AgentController:
    """
    Agentic Controller with ReAct (Thought-Action-Observation) loop.
    Enables multi-step reasoning and tool orchestration.
    """
    def __init__(self, mode: str, vector_store: VectorStore):
        self.mode = mode
        self.vector_store = vector_store
        self.llm_service = LLMService()
        self.max_iterations = 3
        
        # Initialize Tools
        self.tools = {
            "search_documents": SearchTool(vector_store=self.vector_store),
            "generate_image": ImageTool(llm_service=self.llm_service)
        }

    def _parse_llm_output(self, llm_output: str) -> Optional[str]:
        """Parse LLM output for Final Answer or natural response."""
        if "Final Answer:" in llm_output:
            return llm_output.split("Final Answer:")[1].strip()
        
        # Fallback: If model responds naturally without "Final Answer:" tag
        if len(llm_output) > 20 and "Thought:" not in llm_output and "Action:" not in llm_output:
            return llm_output.strip()
        
        return None

    def _handle_action(self, llm_output: str, messages: List[Dict[str, str]]) -> bool:
        """Parse and execute tool actions. Returns True if an action was processed."""
        if "Action:" in llm_output and "Action Input:" in llm_output:
            try:
                action_line = [line for line in llm_output.split("\n") if "Action:" in line][0]
                input_line = [line for line in llm_output.split("\n") if "Action Input:" in line][0]
                
                action = action_line.split("Action:")[1].strip()
                action_input = input_line.split("Action Input:")[1].strip()
                
                if action in self.tools:
                    observation = self.tools[action].run(action_input)
                    messages.append({"role": "assistant", "content": llm_output})
                    messages.append({"role": "user", "content": f"Observation: {observation}"})
                    return True
                else:
                    messages.append({"role": "user", "content": f"System: Tool '{action}' is invalid. Use {list(self.tools.keys())}."})
            except (IndexError, ValueError):
                messages.append({"role": "user", "content": "System: Command format error. Use Action: [Tool] and Action Input: [Input]."})
        return False

    def execute_loop(self, user_text: str, chat_history: List[Dict[str, Any]]) -> str:
        """Phase 10: High-Fidelity Reasoning Loop."""
        system_prompt = f"""
        # IDENTITY
        You are ResilienceGPT, a Disaster Management Expert representing the National Disaster Management Authority (NDMA) of Pakistan. 
        Trained and developed by the NEOC AI team.

        # TONE & STYLE
        - **Professional & Natural**: Expert advisor tone.
        - **Cultural Nuance**: Use appropriate greetings (e.g., "Salam").
        - **Information Density**: technical/actionable advice with markdown formatting.
        - **Citations**: Integrate references (e.g., "[1]") naturally.
        - **Formatting**: Use tables and bolding for clarity.

        # REASONING PROTOCOL (ReAct)
        Thought -> Action -> Observation
        
        Available Tools: {list(self.tools.keys())}

        OUTPUT FORMAT:
        Thought: [Reasoning]
        Action: [Tool]
        Action Input: [Input]
        
        Final Answer: [Your polished response]
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User Message: {user_text}\nContext: {str(chat_history[-3:]) if chat_history else 'None'}"}
        ]

        for iteration in range(self.max_iterations):
            llm_output = self.llm_service.chat(messages, temperature=0.6)
            
            # 1. Try to get final answer
            final_answer = self._parse_llm_output(llm_output)
            if final_answer:
                return final_answer
            
            # 2. Try to handle tool action
            if self._handle_action(llm_output, messages):
                continue
            
            # 3. Force finalization if loop is stuck
            messages.append({"role": "user", "content": "System: Please provide your Final Answer now."})

        # Fallback to direct call
        return self.vector_store.call_llm("", user_text, chat_history, [])

    def route_and_execute(self, user_text: str, chat_history: List[Dict[str, Any]]) -> str:
        """Deprecating in favor of execute_loop in Phase 8."""
        return self.execute_loop(user_text, chat_history)


def process_chat_request(
    user_text: str,
    action: str,
    mode: str,
    chat_history: List[Dict[str, Any]],
    files: Optional[List[FileStorage]] = None,
    path: Optional[str] = None,
    vector_store: Optional[VectorStore] = None,
    use_agent: bool = False,
) -> Union[str, bytes]:
    """
    Main controller function handling different types of requests.
    Supports legacy hardcoded routing and new Agentic routing.
    """

    text = ""
    if vector_store is None:
        try:
            from app import vector_store_instances
            vector_store = vector_store_instances.get(
                mode, vector_store_instances.get("general")
            )
        except ImportError:
            from services.vector_store import VectorStore
            vector_store = VectorStore(mode=mode)
            
        if vector_store is None:
             raise ValueError(f"No VectorStore available for mode: {mode}")

    # Use Agentic Routing if requested (Phase 7+)
    if use_agent:
        agent = AgentController(mode=mode, vector_store=vector_store)
        return agent.route_and_execute(user_text, chat_history)

    if action == "insert":
        if not files:
            return "No files provided"
        results = vector_store.insert_docs(files)
        
        success_count = sum(1 for r in results if r["status"] == "success")
        failure_count = len(results) - success_count
        
        if failure_count == 0:
            return f"Successfully processed {success_count} documents."
        else:
            failures = [f"{r['filename']} ({r['error']})" for r in results if r['status'] == 'failed']
            return f"Processed {success_count} files. Failed: {', '.join(failures)}"

    elif action == "search":
        context, ref = vector_store.search_documents(user_text)
        text = vector_store.call_llm(context, user_text, chat_history, ref)
        return text

    elif action == "audio":
        filename = f"audio_{uuid4()}.wav"
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(user_text)

        user_message = transcribe(filepath)
        return user_message

    elif action == "image":
        summary = LLMService().llama_summarize(text=user_text)
        image = LLMService().call_stable_diffusion(summary)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        image_base64 = base64.b64encode(buf.read()).decode("utf-8")
        return image_base64

    else:
        return text
