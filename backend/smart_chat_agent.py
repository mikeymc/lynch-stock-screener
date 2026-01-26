# ABOUTME: Smart Chat Agent using ReAct (Reasoning + Acting) pattern
# ABOUTME: Orchestrates multi-step reasoning with tool calls to answer complex questions

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Generator
import time
from google import genai
from google.genai.types import GenerateContentConfig, Content, Part, Tool

from agent_tools import AGENT_TOOLS, TOOL_DECLARATIONS, ToolExecutor
from stock_context import StockContext

logger = logging.getLogger(__name__)

# Maximum number of reasoning steps before forcing a final answer
MAX_ITERATIONS = 50


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
        self.stock_context = StockContext(db)
        self.tool_executor = ToolExecutor(db, stock_context=self.stock_context)
        
        # Lazy client initialization
        import os
        self._api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        self._client = None
        
        self.model_name = "gemini-2.5-flash"
        self.fallback_model_name = "gemini-2.0-flash"
    
    @property
    def client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            if self._api_key:
                self._client = genai.Client(api_key=self._api_key)
            else:
                self._client = genai.Client()
        return self._client
    
    def _detect_character_mention(self, message: str) -> Optional[str]:
        """Detect if a message contains a character mention (e.g. @buffett)."""
        if not message or '@' not in message:
            return None
            
        # We want to match @name at the start or distinct words
        # Simple heuristic: look for @name in component words
        # but spec says "direct question at that character", usually implies starts with or addressed to.
        # Let's support "@buffett message" or "message @buffett"
        
        try:
            from characters import list_characters
            available_ids = {c.id for c in list_characters()}
            
            import re
            # Regex to find @mentions, robust to markdown (e.g. **@buffett**) and punctuation
            # Matches @ followed by word characters (alphanumeric + underscore)
            matches = re.findall(r'@([a-zA-Z0-9_]+)', message.lower())
            
            for potential_id in matches:
                if potential_id in available_ids:
                    return potential_id

        except Exception as e:
            logger.error(f"Error detecting character mention: {e}")
            
        return None

    def _build_system_prompt(self, primary_symbol: str, user_id: Optional[int] = None, override_character_id: Optional[str] = None) -> str:
        """Build the system prompt for the agent."""
        current_date_str = datetime.now().strftime('%Y-%m-%d')
        
        current_date_str = datetime.now().strftime('%Y-%m-%d')


        # Determine paths
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompts_dir = os.path.join(base_dir, 'prompts')

        # Load persona based on active character setting
        persona_content = "You are a pragmatic, data-driven investment analyst."
        try:
            from characters import get_character
            
            character_id = None
            
            # Check for override first
            if override_character_id:
                character_id = override_character_id
            elif user_id is not None:
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
            else:
                logger.error(f"Persona file not found at: {persona_path}")
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

        # Check for character mention override (e.g. @buffett)
        override_character_id = self._detect_character_mention(user_message)

        # Build initial contents
        system_prompt = self._build_system_prompt(primary_symbol, user_id, override_character_id)

        
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
            
            # Generate response with retry logic and fallback
            response = None
            
            models_to_try = [self.model_name, self.fallback_model_name]
            
            for model_index, model in enumerate(models_to_try):
                retry_count = 0
                max_retries = 3
                base_delay = 1
                model_success = False
                
                while retry_count <= max_retries:
                    try:
                        response = self.client.models.generate_content(
                            model=model,
                            contents=contents,
                            config=config,
                        )
                        model_success = True
                        break
                    except Exception as e:
                        is_overloaded = "503" in str(e) or "overloaded" in str(e).lower()
                        
                        # If retries left for this model, wait and retry
                        if is_overloaded and retry_count < max_retries:
                            sleep_time = base_delay * (2 ** retry_count)
                            logger.warning(f"Gemini API ({model}) overloaded. Retrying in {sleep_time}s (attempt {retry_count + 1}/{max_retries})")
                            time.sleep(sleep_time)
                            retry_count += 1
                            continue
                        
                        # If we are here, this model failed all retries (or non-retriable error)
                        # If it's the last model, or not an overload error, raise it
                        if model_index == len(models_to_try) - 1 or not is_overloaded:
                            raise e
                        
                        # Otherwise break inner loop to try next model
                        logger.warning(f"Primary model {model} failed. Switching to fallback...")
                        break
                
                if model_success:
                    break
            
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
                        
                        # Inject user_id context for alerts and portfolios
                        portfolio_tools = ["create_portfolio", "get_my_portfolios", "get_portfolio_status", "buy_stock", "sell_stock"]
                        if (tool_name == "manage_alerts" or tool_name in portfolio_tools) and user_id:
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
        user_id: Optional[int] = None,
        initial_character_id: Optional[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Stream a chat response with real-time token yield.
        Supports multi-turn conversations (e.g. Lynch -> Buffett) in a single stream.
        """
        
        # Max turns for multi-character dialogue
        MAX_TURNS = 5
        current_turn = 0
        
        # Track state across turns
        current_message = user_message
        current_history = conversation_history or []
        accumulated_tool_calls_log = []
        accumulated_iterations = 0
        
        # Explicitly track who should speak next if determined by a previous turn
        forced_next_character = None
        
        while current_turn < MAX_TURNS:
            current_turn += 1
            
            # Detect character override for this turn
            # Priority: 
            # 1. Forced handoff from previous turn (Tool call)
            # 2. User mention in current_message (only valid if current_turn == 1)
            # 3. Initial character selection (only valid if current_turn == 1)
            
            override_character_id = None
            if forced_next_character:
                override_character_id = forced_next_character
            else:
                # Only check text for the first turn (User message). 
                # For subsequent turns (Model messages), we rely STRICTLY on tools to avoid accidental handoffs.
                if current_turn == 1:
                    # Check for text tag overwrite first
                    text_override = self._detect_character_mention(current_message)
                    if text_override:
                        override_character_id = text_override
                    elif initial_character_id:
                        # Fallback to UI selection
                        override_character_id = initial_character_id
            
            # Temporary storage for this turn's response to check for next mention
            turn_response_text = ""
            
            # Emit active character event for this turn so frontend can update avatar immediately
            if override_character_id:
                 yield {"type": "active_character", "data": {"character": override_character_id}}
            
            # Track if a handoff tool was called in this turn
            handoff_target = None
            
            # Stream this turn
            for event in self._chat_stream_single_turn(
                primary_symbol, 
                current_message, 
                current_history, 
                user_id,
                override_character_id
            ):
                if event['type'] == 'done':
                    # Accumulate stats but DON'T yield done yet
                    data = event['data']
                    if 'tool_calls' in data:
                        accumulated_tool_calls_log.extend(data['tool_calls'])
                    if 'iterations' in data:
                        accumulated_iterations += data['iterations']
                    continue
                
                if event['type'] == 'token':
                    turn_response_text += event['data']
                    
                # Intercept handoff tool call
                if event['type'] == 'tool_call' and event['data']['tool'] == 'handoff_to_character':
                    args = event['data']['args']
                    handoff_target = args.get('target_character')
                    # We continue yielding seeing the tool call, but we note the handoff
                    
                yield event
            
            # Check for next turn trigger
            # STRICTLY use the tool call result. Ignore text mentions in model output.
            next_character_id = handoff_target
            
            # If no handoff tool called, we are done
            if not next_character_id:
                break
                
            # If we found a handoff, prepare for next turn
            # 1. Add the user message and the model response to history
            current_history.append({"role": "user", "content": current_message})
            current_history.append({"role": "model", "content": turn_response_text})
            
            # 2. Valid handoff
            yield {"type": "next_turn", "data": {"character": next_character_id}}
            
            # 3. Setup state for next loop
            current_message = turn_response_text # Next prompt is previous answer
            forced_next_character = next_character_id # Force the speaker for next turn
            
        # Yield final done event
        yield {
            "type": "done",
            "data": {
                "tool_calls": accumulated_tool_calls_log,
                "iterations": accumulated_iterations
            }
        }

    def _chat_stream_single_turn(
        self,
        primary_symbol: str,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        user_id: Optional[int],
        override_character_id: Optional[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Internal method for a single turn of chat.
        """
        primary_symbol = primary_symbol.upper()

        if not override_character_id:
             override_character_id = self._detect_character_mention(user_message)

        system_prompt = self._build_system_prompt(primary_symbol, user_id, override_character_id)
        
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
            response = None
            
            models_to_try = [self.model_name, self.fallback_model_name]
            
            for model_index, model in enumerate(models_to_try):
                retry_count = 0
                max_retries = 3
                base_delay = 1
                model_success = False

                while retry_count <= max_retries:
                    try:
                        response = self.client.models.generate_content(
                            model=model,
                            contents=contents,
                            config=config,
                        )
                        model_success = True
                        break
                    except Exception as e:
                        is_overloaded = "503" in str(e) or "overloaded" in str(e).lower()
                        
                        if is_overloaded and retry_count < max_retries:
                            sleep_time = base_delay * (2 ** retry_count)
                            # Yield a thinking status so the user knows we are retrying
                            yield {"type": "thinking", "data": f"Model overloaded, retrying in {sleep_time}s..."}
                            logger.warning(f"Gemini API ({model}) overloaded. Retrying in {sleep_time}s (attempt {retry_count + 1}/{max_retries})")
                            time.sleep(sleep_time)
                            retry_count += 1
                            continue
                        
                        # If we are here, this model failed
                        if model_index == len(models_to_try) - 1 or not is_overloaded:
                            raise e
                        
                        # Fallback
                        yield {"type": "thinking", "data": f"Primary model overloaded. Switching to fallback ({self.fallback_model_name})..."}
                        logger.warning(f"Primary model {model} failed. Switching to fallback...")
                        break
                
                if model_success:
                    break
            
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
                        
                        # Inject user_id context for alerts and portfolios
                        portfolio_tools = ["create_portfolio", "get_my_portfolios", "get_portfolio_status", "buy_stock", "sell_stock"]
                        if (tool_name == "manage_alerts" or tool_name in portfolio_tools) and user_id:
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

                        # If this was a handoff, we should STOP here and let the next turn logic handle it
                        if tool_name == "handoff_to_character":
                             yield {"type": "done", "data": {"tool_calls": tool_calls_log, "iterations": iterations}}
                             return
                    
                    contents.append(response.candidates[0].content)
                    contents.append(Content(role="user", parts=function_responses))
                    continue
                
                # Final text response - stream it in chunks for better UX
                text_parts = [p for p in parts if hasattr(p, 'text') and p.text]
                if text_parts:
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
                text = response.text
                chunk_size = 30
                for i in range(0, len(text), chunk_size):
                    yield {"type": "token", "data": text[i:i+chunk_size]}
                    time.sleep(0.015)
                yield {"type": "done", "data": {"tool_calls": tool_calls_log, "iterations": iterations}}
                return
            
            break
        
        yield {"type": "error", "data": "Max LLM iterations reached. Please try your request again or ask it in a different way."}
        yield {"type": "done", "data": {"tool_calls": tool_calls_log, "iterations": iterations}}
