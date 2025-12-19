# ABOUTME: Tests for user-specific conversation operations
# ABOUTME: Validates conversation storage and retrieval per user

import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from conversation_manager import ConversationManager


@pytest.fixture
def conv_manager(test_db):
    """Create ConversationManager with test database"""
    return ConversationManager(test_db)


def test_create_conversation_for_user(test_db, conv_manager):
    """Test creating a conversation for a specific user"""
    # Create test user
    user_id = test_db.create_user("google_123", "test_create_conversation@example.com", "Test User", None)

    # Create stock (required for foreign key)
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before creating conversation

    # Create conversation for user
    conv_id = conv_manager.create_conversation(user_id, "AAPL", "Apple Discussion")

    assert conv_id is not None
    assert isinstance(conv_id, int)

    # Verify conversation exists and belongs to user
    conversations = conv_manager.list_conversations(user_id, "AAPL")
    assert len(conversations) == 1
    assert conversations[0]['id'] == conv_id
    assert conversations[0]['title'] == "Apple Discussion"


def test_different_users_have_separate_conversations(test_db, conv_manager):
    """Test that different users have separate conversations"""
    # Create two users
    user1_id = test_db.create_user("google_123", "user1@example.com", "User One", None)
    user2_id = test_db.create_user("google_456", "user2@example.com", "User Two", None)

    # Create stock (required for foreign key)
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before creating conversation

    # Each user creates a conversation for the same symbol
    conv1_id = conv_manager.create_conversation(user1_id, "AAPL", "User 1's Apple Chat")
    conv2_id = conv_manager.create_conversation(user2_id, "AAPL", "User 2's Apple Chat")

    # Verify each user sees only their own conversations
    user1_convs = conv_manager.list_conversations(user1_id, "AAPL")
    user2_convs = conv_manager.list_conversations(user2_id, "AAPL")

    assert len(user1_convs) == 1
    assert len(user2_convs) == 1
    assert user1_convs[0]['id'] == conv1_id
    assert user2_convs[0]['id'] == conv2_id
    assert user1_convs[0]['title'] == "User 1's Apple Chat"
    assert user2_convs[0]['title'] == "User 2's Apple Chat"


def test_add_message_to_conversation(test_db, conv_manager):
    """Test adding messages to a user's conversation"""
    user_id = test_db.create_user("google_123", "test_empty_conversation@example.com", "Test User", None)

    # Create stock (required for foreign key)
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before creating conversation

    conv_id = conv_manager.create_conversation(user_id, "AAPL", "Test Chat")

    # Add messages
    msg1_id = conv_manager.add_message(conv_id, "user", "What's the PE ratio?")
    msg2_id = conv_manager.add_message(conv_id, "assistant", "The PE ratio is 25.5")

    # Get messages
    messages = conv_manager.get_messages(conv_id)
    assert len(messages) == 2
    assert messages[0]['role'] == "user"
    assert messages[0]['content'] == "What's the PE ratio?"
    assert messages[1]['role'] == "assistant"
    assert messages[1]['content'] == "The PE ratio is 25.5"


def test_get_empty_conversation_list(test_db, conv_manager):
    """Test getting conversations when user has none"""
    user_id = test_db.create_user("google_123", "test_user_isolation@example.com", "Test User", None)

    conversations = conv_manager.list_conversations(user_id, "AAPL")
    assert conversations == []


def test_user_cannot_see_other_user_conversations(test_db, conv_manager):
    """Test that a user cannot see another user's conversations"""
    user1_id = test_db.create_user("google_123", "user1@example.com", "User One", None)
    user2_id = test_db.create_user("google_456", "user2@example.com", "User Two", None)

    # Create stock (required for foreign key)
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before creating conversation

    # User 1 creates a conversation
    conv_manager.create_conversation(user1_id, "AAPL", "User 1's Chat")

    # User 2 should not see user 1's conversations
    user2_convs = conv_manager.list_conversations(user2_id, "AAPL")
    assert len(user2_convs) == 0
