# ABOUTME: Manages conversation state and persistence for RAG chat
# ABOUTME: Handles creating, loading, and updating conversations and messages

from typing import Dict, Any, List, Optional
from datetime import datetime
from database import Database
import google.generativeai as genai
from rag_context import RAGContext


class ConversationManager:
    """Manages chat conversations and integrates with Gemini AI"""

    def __init__(self, db: Database, gemini_api_key: Optional[str] = None):
        """
        Initialize conversation manager

        Args:
            db: Database instance
            gemini_api_key: Optional Gemini API key (defaults to GEMINI_API_KEY env var)
        """
        self.db = db
        self.rag_context = RAGContext(db)

        # Configure Gemini
        import os
        api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)

        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def create_conversation(self, symbol: str, title: Optional[str] = None) -> int:
        """
        Create a new conversation for a stock

        Args:
            symbol: Stock ticker symbol
            title: Optional conversation title

        Returns:
            Conversation ID
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO conversations (symbol, title, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (symbol, title))

        conversation_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return conversation_id

    def get_conversation(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """Get conversation metadata"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, symbol, title, created_at, updated_at
            FROM conversations
            WHERE id = ?
        """, (conversation_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'id': row[0],
            'symbol': row[1],
            'title': row[2],
            'created_at': row[3],
            'updated_at': row[4]
        }

    def list_conversations(self, symbol: str) -> List[Dict[str, Any]]:
        """Get all conversations for a stock"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, symbol, title, created_at, updated_at
            FROM conversations
            WHERE symbol = ?
            ORDER BY updated_at DESC
        """, (symbol,))

        rows = cursor.fetchall()
        conn.close()

        return [{
            'id': row[0],
            'symbol': row[1],
            'title': row[2],
            'created_at': row[3],
            'updated_at': row[4]
        } for row in rows]

    def get_messages(self, conversation_id: int) -> List[Dict[str, Any]]:
        """Get all messages in a conversation"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, role, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
        """, (conversation_id,))

        rows = cursor.fetchall()
        conn.close()

        return [{
            'id': row[0],
            'role': row[1],
            'content': row[2],
            'created_at': row[3]
        } for row in rows]

    def add_message(self, conversation_id: int, role: str, content: str, sources: Optional[List[str]] = None) -> int:
        """
        Add a message to a conversation

        Args:
            conversation_id: Conversation ID
            role: 'user' or 'assistant'
            content: Message content
            sources: Optional list of section names that were referenced

        Returns:
            Message ID
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Insert message
        cursor.execute("""
            INSERT INTO messages (conversation_id, role, content, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (conversation_id, role, content))

        message_id = cursor.lastrowid

        # Add sources if provided
        if sources:
            for section_name in sources:
                # Get filing info for this section
                cursor.execute("""
                    SELECT filing_type, filing_date
                    FROM filing_sections
                    WHERE symbol = (SELECT symbol FROM conversations WHERE id = ?)
                    AND section_name = ?
                    ORDER BY filing_date DESC
                    LIMIT 1
                """, (conversation_id, section_name))

                filing_info = cursor.fetchone()
                filing_type = filing_info[0] if filing_info else None
                filing_date = filing_info[1] if filing_info else None

                cursor.execute("""
                    INSERT INTO message_sources (message_id, section_name, filing_type, filing_date)
                    VALUES (?, ?, ?, ?)
                """, (message_id, section_name, filing_type, filing_date))

        # Update conversation updated_at timestamp
        cursor.execute("""
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (conversation_id,))

        conn.commit()
        conn.close()

        return message_id

    def send_message(self, conversation_id: int, user_message: str) -> Dict[str, Any]:
        """
        Send a message and get AI response

        Args:
            conversation_id: Conversation ID
            user_message: User's message

        Returns:
            Dict with assistant_message, sources, and message_id
        """
        # Get conversation info
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        symbol = conversation['symbol']

        # Get conversation history
        history = self.get_messages(conversation_id)
        conversation_history = [{'role': msg['role'], 'content': msg['content']} for msg in history]

        # Get stock context with smart section selection
        context = self.rag_context.get_stock_context(symbol, user_query=user_message)
        if not context:
            raise ValueError(f"Could not load context for {symbol}")

        # Format prompt for LLM
        prompt = self.rag_context.format_for_llm(context, user_message, conversation_history)

        # Generate response using Gemini
        response = self.model.generate_content(prompt)
        assistant_message = response.text

        # Save user message
        self.add_message(conversation_id, 'user', user_message)

        # Save assistant message with sources
        sources = context['selected_sections']
        assistant_msg_id = self.add_message(conversation_id, 'assistant', assistant_message, sources)

        return {
            'message': assistant_message,
            'sources': sources,
            'message_id': assistant_msg_id
        }

    def send_message_stream(self, conversation_id: int, user_message: str):
        """
        Send a message and stream AI response

        Args:
            conversation_id: Conversation ID
            user_message: User's message

        Yields:
            Dict with type ('token', 'sources', 'done', 'error') and data
        """
        try:
            # Get conversation info
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                yield {'type': 'error', 'data': f"Conversation {conversation_id} not found"}
                return

            symbol = conversation['symbol']

            # Get conversation history
            history = self.get_messages(conversation_id)
            conversation_history = [{'role': msg['role'], 'content': msg['content']} for msg in history]

            # Get stock context with smart section selection
            context = self.rag_context.get_stock_context(symbol, user_query=user_message)
            if not context:
                yield {'type': 'error', 'data': f"Could not load context for {symbol}"}
                return

            # Send sources first
            sources = context['selected_sections']
            yield {'type': 'sources', 'data': sources}

            # Format prompt for LLM
            prompt = self.rag_context.format_for_llm(context, user_message, conversation_history)

            # Stream response from Gemini
            response = self.model.generate_content(prompt, stream=True)

            full_message = []
            for chunk in response:
                if chunk.text:
                    full_message.append(chunk.text)
                    yield {'type': 'token', 'data': chunk.text}

            # Save user message
            self.add_message(conversation_id, 'user', user_message)

            # Save assistant message with sources
            assistant_message = ''.join(full_message)
            assistant_msg_id = self.add_message(conversation_id, 'assistant', assistant_message, sources)

            yield {'type': 'done', 'data': {'message_id': assistant_msg_id}}

        except Exception as e:
            yield {'type': 'error', 'data': str(e)}

    def get_or_create_conversation(self, symbol: str) -> int:
        """
        Get the most recent conversation for a stock, or create a new one

        Args:
            symbol: Stock ticker symbol

        Returns:
            Conversation ID
        """
        conversations = self.list_conversations(symbol)

        if conversations:
            # Return most recent conversation
            return conversations[0]['id']
        else:
            # Create new conversation
            return self.create_conversation(symbol, title=f"Chat about {symbol}")
