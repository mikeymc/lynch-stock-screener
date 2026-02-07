# ABOUTME: AI agent chat endpoints for conversational stock analysis
# ABOUTME: Manages agent conversations, message history, and streaming responses

from flask import Blueprint, jsonify, request, Response, stream_with_context
from app import deps
from app.helpers import generate_conversation_title, clean_nan_values
from auth import require_user_auth
import json
import logging

logger = logging.getLogger(__name__)

agent_bp = Blueprint('agent', __name__)

_smart_chat_agent = None


def get_smart_chat_agent():
    """Get or create the Smart Chat Agent singleton."""
    global _smart_chat_agent
    if _smart_chat_agent is None:
        from smart_chat_agent import SmartChatAgent
        _smart_chat_agent = SmartChatAgent(deps.db)
    return _smart_chat_agent


@agent_bp.route('/api/chat/<symbol>/agent', methods=['POST'])
@require_user_auth
def agent_chat(symbol, user_id):
    """
    Smart Chat Agent endpoint using ReAct pattern.

    The agent can:
    - Reason about what data it needs
    - Call tools to fetch financial data
    - Synthesize a comprehensive answer

    Streams response via Server-Sent Events.
    """
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400

        user_message = data['message']
        conversation_history = data.get('history', [])
        character_id = data.get('character')

        agent = get_smart_chat_agent()

        def generate():
            """Generate Server-Sent Events for agent response."""
            try:
                for event in agent.chat_stream(symbol.upper(), user_message, conversation_history, user_id, character_id):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                logger.error(f"Agent chat stream error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        logger.error(f"Error in agent chat for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/api/chat/<symbol>/agent/sync', methods=['POST'])
@require_user_auth
def agent_chat_sync(symbol, user_id):
    """
    Synchronous Smart Chat Agent endpoint (non-streaming).

    Useful for testing or clients that don't support SSE.
    """
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400

        user_message = data['message']
        conversation_history = data.get('history', [])
        character_id = data.get('character')

        agent = get_smart_chat_agent()
        result = agent.chat(symbol.upper(), user_message, conversation_history, user_id, character_id)

        return jsonify(clean_nan_values(result))

    except Exception as e:
        logger.error(f"Error in sync agent chat for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Agent Conversation Persistence Endpoints
# =============================================================================

@agent_bp.route('/api/agent/conversations', methods=['GET'])
@require_user_auth
def get_agent_conversations_list(user_id):
    """Get user's agent conversation list."""
    try:
        conversations = deps.db.get_agent_conversations(user_id, limit=10)
        return jsonify({'conversations': conversations})
    except Exception as e:
        logger.error(f"Error getting agent conversations: {e}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/api/agent/conversations', methods=['POST'])
@require_user_auth
def create_agent_conversation_endpoint(user_id):
    """Create a new agent conversation."""
    try:
        conversation_id = deps.db.create_agent_conversation(user_id)
        return jsonify({'conversation_id': conversation_id})
    except Exception as e:
        logger.error(f"Error creating agent conversation: {e}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/api/agent/conversation/<int:conversation_id>/messages', methods=['GET'])
@require_user_auth
def get_agent_conversation_messages(conversation_id, user_id):
    """Get messages for an agent conversation."""
    try:
        messages = deps.db.get_agent_messages(conversation_id)
        return jsonify({'messages': messages})
    except Exception as e:
        logger.error(f"Error getting agent messages: {e}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/api/agent/conversation/<int:conversation_id>/messages', methods=['POST'])
@require_user_auth
def save_agent_conversation_message(conversation_id, user_id):
    """Save a message to an agent conversation."""
    try:
        data = request.get_json()
        if not data or 'role' not in data or 'content' not in data:
            return jsonify({'error': 'role and content required'}), 400

        deps.db.save_agent_message(
            conversation_id,
            data['role'],
            data['content'],
            data.get('tool_calls')
        )

        # Auto-generate title from first user message using LLM
        title = None
        if data['role'] == 'user':
            messages = deps.db.get_agent_messages(conversation_id)
            if len(messages) == 1:  # This is the first message
                title = generate_conversation_title(data['content'])
                deps.db.update_conversation_title(conversation_id, title)

        return jsonify({'success': True, 'title': title})
    except Exception as e:
        logger.error(f"Error saving agent message: {e}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/api/agent/conversation/<int:conversation_id>', methods=['DELETE'])
@require_user_auth
def delete_agent_conversation(conversation_id, user_id):
    """Delete an agent conversation (verifies ownership)."""
    try:
        deleted = deps.db.delete_agent_conversation(conversation_id, user_id)
        if deleted:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Conversation not found or not owned by user'}), 404
    except Exception as e:
        logger.error(f"Error deleting agent conversation: {e}")
        return jsonify({'error': str(e)}), 500
