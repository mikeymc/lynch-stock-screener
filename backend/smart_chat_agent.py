# ABOUTME: Smart Chat Agent using ReAct (Reasoning + Acting) pattern
# ABOUTME: Orchestrates multi-step reasoning with tool calls to answer complex questions

import logging
from typing import Dict, Any, List, Optional, Generator
from google import genai
from google.genai.types import GenerateContentConfig, Content, Part

from agent_tools import AGENT_TOOLS, ToolExecutor
from rag_context import RAGContext

logger = logging.getLogger(__name__)

# Maximum number of reasoning steps before forcing a final answer
MAX_ITERATIONS = 8


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
    
    def _build_system_prompt(self, primary_symbol: str) -> str:
        """Build the system prompt for the agent."""
        return f"""You are a financial research assistant with access to tools for fetching stock data.

Your primary context is {primary_symbol}, but you can fetch data about other stocks to make comparisons.

INSTRUCTIONS:
1. When a user asks a question, think about what data you need to answer it.
2. Use the available tools to fetch the data. You can make multiple tool calls.
3. After gathering enough data, synthesize a clear, accurate answer.
4. If data is missing or unavailable, say so rather than guessing.
5. Be concise but thorough. Use specific numbers when available.
6. For comparisons, present data in a structured format when helpful.

CHART OUTPUT:
When comparing multiple data points (especially across companies or years), you can output an interactive chart.
Use a code block with language "chart" and JSON data in this format:

```chart
{{
  "type": "bar",
  "title": "Revenue Comparison (in billions USD)",
  "data": [
    {{"name": "2022", "AMD": 23.6, "NVDA": 26.9}},
    {{"name": "2023", "AMD": 22.7, "NVDA": 27.0}},
    {{"name": "2024", "AMD": 25.8, "NVDA": 60.9}}
  ]
}}
```

Chart types: "bar" (for comparisons), "line" (for trends over time)
Always include a descriptive title. Data values should be numbers (not strings).

IMPORTANT RULES:
1. When the user mentions a company name, use search_company to find the ticker.
2. Always try calling tools before saying data doesn't exist.
3. If a tool returns an error, explain that data was unavailable.
4. Use recent data when possible (prefer current year and last 1-2 years)."""


    def chat(
        self, 
        primary_symbol: str, 
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Process a user message and return an agent response.
        
        Args:
            primary_symbol: The stock symbol for context (e.g., 'NVDA')
            user_message: The user's question
            conversation_history: Optional list of previous messages
            
        Returns:
            Dict with 'response', 'tool_calls', and 'iterations'
        """
        primary_symbol = primary_symbol.upper()
        
        # Build initial contents
        system_prompt = self._build_system_prompt(primary_symbol)
        
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
        config = GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[AGENT_TOOLS],
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
        conversation_history: Optional[List[Dict[str, str]]] = None
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
        
        system_prompt = self._build_system_prompt(primary_symbol)
        
        contents = []
        if conversation_history:
            for msg in conversation_history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(Content(role=role, parts=[Part(text=msg["content"])]))
        
        contents.append(Content(role="user", parts=[Part(text=user_message)]))
        
        config = GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[AGENT_TOOLS],
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
                
                # Final text response - stream it
                text_parts = [p for p in parts if hasattr(p, 'text') and p.text]
                if text_parts:
                    for part in text_parts:
                        yield {"type": "token", "data": part.text}
                    
                    yield {"type": "done", "data": {"tool_calls": tool_calls_log, "iterations": iterations}}
                    return
            
            if response.text:
                yield {"type": "token", "data": response.text}
                yield {"type": "done", "data": {"tool_calls": tool_calls_log, "iterations": iterations}}
                return
            
            break
        
        yield {"type": "error", "data": "Max iterations reached"}
        yield {"type": "done", "data": {"tool_calls": tool_calls_log, "iterations": iterations}}
