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

    def execute_loop(self, user_text: str, chat_history: List[Dict[str, Any]]) -> str:
        """
        Phase 8: ReAct Reasoning Loop.
        """
        system_prompt = f"""
        You are ResilienceGPT, a reasoning AI assistant for the NDMA.
        You solve complex tasks by following a Thought-Action-Observation loop.

        Available Tools:
        - search_documents: For finding facts, procedures, or context. Input: A specific search query.
        - generate_image: For visual requests. Input: A descriptive prompt.

        Format your response exactly as follows:
        Thought: [Your reasoning about what to do next]
        Action: [Tool name: either 'search_documents' or 'generate_image']
        Action Input: [The input for the tool]

        Once you have enough information or if no tool is needed, respond with:
        Final Answer: [Your comprehensive final response]

        Rules:
        1. Always start with a Thought.
        2. If you use a tool, wait for the Observation before continuing.
        3. Mention citations naturally in your Final Answer if they were provided in search results.
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User: {user_text}\nHistory: {str(chat_history[-2:]) if chat_history else 'None'}"}
        ]

        # Start the loop
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            
            # Step 1: Get LLM Reasoning/Action
            # We use llama_summarize as a proxy for raw LLM call, but we might need a more general one
            # For now, let's craft a prompt that triggers the next step
            full_prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
            llm_output = self.llm_service.llama_summarize(full_prompt, max_words=200)
            print(f"Agent Reasoning Iteration {iteration}:\n{llm_output}")

            # Step 2: Parse Output
            if "Final Answer:" in llm_output:
                return llm_output.split("Final Answer:")[1].strip()

            if "Action:" in llm_output and "Action Input:" in llm_output:
                try:
                    action = llm_output.split("Action:")[1].split("\n")[0].strip()
                    action_input = llm_output.split("Action Input:")[1].split("\n")[0].strip()
                    
                    if action in self.tools:
                        observation = self.tools[action].run(action_input)
                        print(f"Observation: {observation[:100]}...")
                        
                        # Add to context
                        messages.append({"role": "assistant", "content": llm_output})
                        messages.append({"role": "user", "content": f"Observation: {observation}"})
                        continue
                    else:
                        messages.append({"role": "user", "content": f"System: Tool '{action}' not found. Try one of {list(self.tools.keys())}."})
                except IndexError:
                    messages.append({"role": "user", "content": "System: Invalid format. Use Action: [Tool] and Action Input: [Input]."})
            else:
                # If LLM didn't follow format but didn't give final answer, try to force it
                return self.vector_store.call_llm("", user_text, chat_history, [])

        return "I apologize, but I couldn't complete your request within the reasoning limit."

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
