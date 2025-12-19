# ABOUTME: Tests for user-specific Lynch analysis operations
# ABOUTME: Validates Lynch analysis storage and retrieval per user

import pytest
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


def test_save_lynch_analysis_for_user(test_db):
    """Test saving a Lynch analysis for a specific user"""
    # Create test user
    user_id = test_db.create_user("google_123", "test_save_lynch@example.com", "Test User", None)

    # Create stock (required for foreign key)
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before saving analysis

    # Save Lynch analysis for user
    test_db.save_lynch_analysis(user_id, "AAPL", "Strong buy candidate", "gemini-3-pro-preview")

    # Verify it was saved
    analysis = test_db.get_lynch_analysis(user_id, "AAPL")
    assert analysis is not None
    assert analysis['symbol'] == "AAPL"
    assert analysis['analysis_text'] == "Strong buy candidate"
    assert analysis['model_version'] == "gemini-3-pro-preview"


def test_different_users_have_separate_lynch_analyses(test_db):
    """Test that different users can have different analyses for the same stock"""
    # Create two users
    user1_id = test_db.create_user("google_123", "user1@example.com", "User One", None)
    user2_id = test_db.create_user("google_456", "user2@example.com", "User Two", None)

    # Create stock (required for foreign key)
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before saving analysis

    # Each user saves their own analysis
    test_db.save_lynch_analysis(user1_id, "AAPL", "User 1's analysis", "gemini-3-pro-preview")
    test_db.save_lynch_analysis(user2_id, "AAPL", "User 2's analysis", "gemini-3-pro-preview")

    # Verify each user sees only their own analysis
    user1_analysis = test_db.get_lynch_analysis(user1_id, "AAPL")
    user2_analysis = test_db.get_lynch_analysis(user2_id, "AAPL")

    assert user1_analysis['analysis_text'] == "User 1's analysis"
    assert user2_analysis['analysis_text'] == "User 2's analysis"


def test_update_existing_lynch_analysis(test_db):
    """Test updating an existing Lynch analysis for a user"""
    user_id = test_db.create_user("google_123", "test_update_lynch@example.com", "Test User", None)

    # Create stock (required for foreign key)
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before saving analysis

    # Save initial analysis
    test_db.save_lynch_analysis(user_id, "AAPL", "Initial analysis", "gemini-3-pro-preview")

    # Update with new analysis
    test_db.save_lynch_analysis(user_id, "AAPL", "Updated analysis", "gemini-3-pro-preview")

    # Verify updated
    analysis = test_db.get_lynch_analysis(user_id, "AAPL")
    assert analysis['analysis_text'] == "Updated analysis"


def test_get_nonexistent_lynch_analysis(test_db):
    """Test getting Lynch analysis that doesn't exist returns None"""
    user_id = test_db.create_user("google_123", "test_nonexistent_lynch@example.com", "Test User", None)

    analysis = test_db.get_lynch_analysis(user_id, "AAPL")
    assert analysis is None


def test_lynch_analysis_has_timestamp(test_db):
    """Test that generated_at timestamp is saved correctly"""
    user_id = test_db.create_user("google_123", "test_lynch_timestamp@example.com", "Test User", None)

    # Create stock (required for foreign key)
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before saving analysis

    before_save = datetime.now()
    test_db.save_lynch_analysis(user_id, "AAPL", "Test analysis", "gemini-3-pro-preview")
    after_save = datetime.now()

    analysis = test_db.get_lynch_analysis(user_id, "AAPL")
    generated_at = analysis['generated_at']

    assert before_save <= generated_at <= after_save
