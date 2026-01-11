# ABOUTME: Smart Chat Agent using ReAct (Reasoning + Acting) pattern
# ABOUTME: Orchestrates multi-step reasoning with tool calls to answer complex questions

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Generator
from google import genai
from google.genai.types import GenerateContentConfig, Content, Part, Tool

from agent_tools import AGENT_TOOLS, TOOL_DECLARATIONS, ToolExecutor
from rag_context import RAGContext

logger = logging.getLogger(__name__)

# Maximum number of reasoning steps before forcing a final answer
MAX_ITERATIONS = 15


class SmartChatAgent:
    """
    An agentic chat assistant that uses ReAct pattern to answer questions.
    
    The agent can:
    1. Reason about what information it needs
    2. Call tools to fetch data
    3. Observe the results
    4. Continue reasoning or provide a final answer
    """
    
    def __init__(self, db, gemini_api_key: Optional[str] = None):
        """
        Initialize the Smart Chat Agent.
        
        Args:
            db: Database instance for data access
            gemini_api_key: Optional API key (defaults to GEMINI_API_KEY env var)
        """
        self.db = db
        self.rag_context = RAGContext(db)
        self.tool_executor = ToolExecutor(db, rag_context=self.rag_context)
        
        # Lazy client initialization
        import os
        self._api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        self._client = None
        
        self.model_name = "gemini-2.5-flash"
    
    @property
    def client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            if self._api_key:
                self._client = genai.Client(api_key=self._api_key)
            else:
                self._client = genai.Client()
        return self._client
    
    def _build_system_prompt(self, primary_symbol: str, user_id: Optional[int] = None) -> str:
        """Build the system prompt for the agent."""
        current_date_str = datetime.now().strftime('%Y-%m-%d')

        # Determine paths
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompts_dir = os.path.join(base_dir, 'prompts')

        # Load persona based on active character setting
        persona_content = "You are a pragmatic, data-driven investment analyst."
        try:
            from characters import get_character
            if user_id is not None:
                character_id = self.db.get_user_character(user_id)
            else:
                # Fallback to global setting for backwards compatibility
                character_id = self.db.get_setting('active_character', 'lynch')
            character = get_character(character_id)
            if character:
                persona_path = os.path.join(prompts_dir, character.persona_prompt)
            else:
                persona_path = os.path.join(prompts_dir, 'agent', 'personas', 'lynch.md')

            if os.path.exists(persona_path):
                with open(persona_path, 'r') as f:
                    persona_content = f.read()
        except Exception as e:
            logger.error(f"Failed to load agent persona: {e}")

        # Load system prompt template
        system_prompt_content = ""
        try:
            system_path = os.path.join(prompts_dir, 'agent', 'agent_global.md')
            if os.path.exists(system_path):
                with open(system_path, 'r') as f:
                    system_prompt_content = f.read()
            else:
                logger.error(f"System prompt file not found at {system_path}")
                # Fallback minimal prompt
                return f"{persona_content}\nCurrent Date: {current_date_str}\nPrimary Symbol: {primary_symbol}"
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            return f"{persona_content}\nCurrent Date: {current_date_str}"
            
        # Format the template
        try:
            return system_prompt_content.format(
                persona_content=persona_content,
                current_date=current_date_str,
                primary_symbol=primary_symbol
            )
        except Exception as e:
            logger.error(f"Failed to format system prompt: {e}")
            return f"{persona_content}\nCurrent Date: {current_date_str}"

    def _get_enabled_tools(self):
        """Get the list of tools enabled for the current session based on feature flags."""
        alerts_enabled = self.db.get_setting("feature_alerts_enabled") is True
        
        if alerts_enabled:
            return AGENT_TOOLS
        else:
            # Filter out manage_alerts if disabled
            filtered_decls = [
                d for d in TOOL_DECLARATIONS 
                if d.name != "manage_alerts"
            ]
            return Tool(function_declarations=filtered_decls)

    def chat(
        self,
        primary_symbol: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process a user message and return an agent response.

        Args:
            primary_symbol: The stock symbol for context (e.g., 'NVDA')
            user_message: The user's question
            conversation_history: Optional list of previous messages
            user_id: Optional user ID for personalized character

        Returns:
            Dict with 'response', 'tool_calls', and 'iterations'
        """
        primary_symbol = primary_symbol.upper()

        # Build initial contents
        system_prompt = self._build_system_prompt(primary_symbol, user_id)
        
        # Start with system instruction and user message
        contents = []
        
        # Add conversation history if provided
        if conversation_history:
            for msg in conversation_history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(Content(role=role, parts=[Part(text=msg["content"])]))
        
        # Add the current user message
        contents.append(Content(role="user", parts=[Part(text=user_message)]))
        
        # Configure generation with tools
        tools = self._get_enabled_tools()
        config = GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[tools],
            temperature=0.3,  # Lower = more deterministic, less hallucination
        )
        
        # ReAct loop
        tool_calls_log = []
        iterations = 0
        
        while iterations < MAX_ITERATIONS:
            iterations += 1
            
            # Generate response
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            
            # Check if model wants to call a tool
            if response.candidates and response.candidates[0].content.parts:
                parts = response.candidates[0].content.parts
                
                # Check for function calls
                function_calls = [p for p in parts if hasattr(p, 'function_call') and p.function_call]
                
                if function_calls:
                    # Execute the function calls
                    function_responses = []
                    
                    for part in function_calls:
                        fc = part.function_call
                        tool_name = fc.name
                        tool_args = dict(fc.args) if fc.args else {}
                        
                        # Inject user_id context for alerts management
                        if tool_name == "manage_alerts" and user_id:
                            tool_args["user_id"] = user_id
                        
                        logger.info(f"[Agent] Calling tool: {tool_name}({tool_args})")
                        
                        # Execute the tool
                        result = self.tool_executor.execute(tool_name, tool_args)
                        
                        tool_calls_log.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result_summary": str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                        })
                        
                        # Build function response
                        import json
                        function_responses.append(Part.from_function_response(
                            name=tool_name,
                            response={"result": json.dumps(result, default=str)}
                        ))
                    
                    # Add the model's response (with function calls) to contents
                    contents.append(response.candidates[0].content)
                    
                    # Add the function results
                    contents.append(Content(role="user", parts=function_responses))
                    
                    # Continue the loop to let the model process the results
                    continue
                
                # No function calls - this is the final text response
                text_parts = [p for p in parts if hasattr(p, 'text') and p.text]
                if text_parts:
                    final_response = "".join(p.text for p in text_parts)
                    return {
                        "response": final_response,
                        "tool_calls": tool_calls_log,
                        "iterations": iterations,
                    }
            
            # Fallback: if we get here, something unexpected happened
            if response.text:
                return {
                    "response": response.text,
                    "tool_calls": tool_calls_log,
                    "iterations": iterations,
                }
            
            # No usable response
            break
        
        # Max iterations reached or no response
        return {
            "response": "I was unable to fully answer your question after multiple attempts. Please try rephrasing or asking a simpler question.",
            "tool_calls": tool_calls_log,
            "iterations": iterations,
        }
    
    def chat_stream(
        self,
        primary_symbol: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        user_id: Optional[int] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Stream a chat response with real-time token yield.

        Yields dicts with 'type' and 'data':
        - {'type': 'thinking', 'data': 'Calling get_peers...'}
        - {'type': 'token', 'data': 'NVDA...'}
        - {'type': 'tool_call', 'data': {'tool': 'get_peers', 'args': {...}}}
        - {'type': 'done', 'data': {'tool_calls': [...], 'iterations': N}}
        """
        primary_symbol = primary_symbol.upper()

        system_prompt = self._build_system_prompt(primary_symbol, user_id)
        
        contents = []
        if conversation_history:
            for msg in conversation_history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(Content(role=role, parts=[Part(text=msg["content"])]))
        
        contents.append(Content(role="user", parts=[Part(text=user_message)]))
        
        tools = self._get_enabled_tools()
        config = GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[tools],
        )
        
        tool_calls_log = []
        iterations = 0
        
        while iterations < MAX_ITERATIONS:
            iterations += 1
            
            # For the final response, we want to stream tokens
            # First, check if this iteration will have tool calls
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            
            if response.candidates and response.candidates[0].content.parts:
                parts = response.candidates[0].content.parts
                function_calls = [p for p in parts if hasattr(p, 'function_call') and p.function_call]
                
                if function_calls:
                    # Process tool calls
                    function_responses = []
                    
                    for part in function_calls:
                        fc = part.function_call
                        tool_name = fc.name
                        tool_args = dict(fc.args) if fc.args else {}
                        
                        # Inject user_id context for alerts management
                        if tool_name == "manage_alerts" and user_id:
                            tool_args["user_id"] = user_id
                        
                        yield {"type": "thinking", "data": f"Calling {tool_name}..."}
                        yield {"type": "tool_call", "data": {"tool": tool_name, "args": tool_args}}
                        
                        result = self.tool_executor.execute(tool_name, tool_args)
                        
                        tool_calls_log.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result_summary": str(result)[:200]
                        })
                        
                        import json
                        function_responses.append(Part.from_function_response(
                            name=tool_name,
                            response={"result": json.dumps(result, default=str)}
                        ))
                    
                    contents.append(response.candidates[0].content)
                    contents.append(Content(role="user", parts=function_responses))
                    continue
                
                # Final text response - stream it in chunks for better UX
                text_parts = [p for p in parts if hasattr(p, 'text') and p.text]
                if text_parts:
                    import time
                    for part in text_parts:
                        # Stream the text in chunks to simulate real-time streaming
                        text = part.text
                        chunk_size = 30  # Characters per chunk
                        for i in range(0, len(text), chunk_size):
                            yield {"type": "token", "data": text[i:i+chunk_size]}
                            time.sleep(0.015)  # 15ms delay between chunks
                    
                    yield {"type": "done", "data": {"tool_calls": tool_calls_log, "iterations": iterations}}
                    return
            
            if response.text:
                # Stream in chunks
                import time
                text = response.text
                chunk_size = 30
                for i in range(0, len(text), chunk_size):
                    yield {"type": "token", "data": text[i:i+chunk_size]}
                    time.sleep(0.015)
                yield {"type": "done", "data": {"tool_calls": tool_calls_log, "iterations": iterations}}
                return
            
            break
        
        yield {"type": "error", "data": "Max iterations reached"}
        yield {"type": "done", "data": {"tool_calls": tool_calls_log, "iterations": iterations}}
