# ABOUTME: Tests for user-specific chart analysis operations
# ABOUTME: Validates chart analysis storage and retrieval per user

import pytest
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.database import Database


@pytest.fixture
def test_db(test_database):
    """Create Database instance using test PostgreSQL database"""
    db = Database(database=test_database)

    # Clean up before each test
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chart_analyses")
        cursor.execute("DELETE FROM users")
        conn.commit()
    finally:
        db.return_connection(conn)

    yield db

    # Clean up after test
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chart_analyses")
        cursor.execute("DELETE FROM users")
        conn.commit()
    finally:
        db.return_connection(conn)


def test_save_chart_analysis_for_user(test_db):
    """Test saving a chart analysis for a specific user"""
    # Create test user
    user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)

    # Save chart analysis for user
    test_db.set_chart_analysis(user_id, "AAPL", "growth", "Strong growth trajectory", "gemini-3-pro")

    # Verify it was saved
    analysis = test_db.get_chart_analysis(user_id, "AAPL", "growth")
    assert analysis is not None
    assert analysis['symbol'] == "AAPL"
    assert analysis['section'] == "growth"
    assert analysis['analysis_text'] == "Strong growth trajectory"
    assert analysis['model_version'] == "gemini-3-pro"


def test_different_users_have_separate_analyses(test_db):
    """Test that different users can have different analyses for the same stock/section"""
    # Create two users
    user1_id = test_db.create_user("google_123", "user1@example.com", "User One", None)
    user2_id = test_db.create_user("google_456", "user2@example.com", "User Two", None)

    # Each user saves their own analysis
    test_db.set_chart_analysis(user1_id, "AAPL", "growth", "User 1's growth analysis", "gemini-3-pro")
    test_db.set_chart_analysis(user2_id, "AAPL", "growth", "User 2's growth analysis", "gemini-3-pro")

    # Verify each user sees only their own analysis
    user1_analysis = test_db.get_chart_analysis(user1_id, "AAPL", "growth")
    user2_analysis = test_db.get_chart_analysis(user2_id, "AAPL", "growth")

    assert user1_analysis['analysis_text'] == "User 1's growth analysis"
    assert user2_analysis['analysis_text'] == "User 2's growth analysis"


def test_user_can_have_multiple_sections(test_db):
    """Test that a user can have analyses for all three sections"""
    user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)

    # Save all three sections
    test_db.set_chart_analysis(user_id, "AAPL", "growth", "Growth analysis", "gemini-3-pro")
    test_db.set_chart_analysis(user_id, "AAPL", "cash", "Cash analysis", "gemini-3-pro")
    test_db.set_chart_analysis(user_id, "AAPL", "valuation", "Valuation analysis", "gemini-3-pro")

    # Verify all three
    growth = test_db.get_chart_analysis(user_id, "AAPL", "growth")
    cash = test_db.get_chart_analysis(user_id, "AAPL", "cash")
    valuation = test_db.get_chart_analysis(user_id, "AAPL", "valuation")

    assert growth['analysis_text'] == "Growth analysis"
    assert cash['analysis_text'] == "Cash analysis"
    assert valuation['analysis_text'] == "Valuation analysis"


def test_update_existing_chart_analysis(test_db):
    """Test updating an existing chart analysis for a user"""
    user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)

    # Save initial analysis
    test_db.set_chart_analysis(user_id, "AAPL", "growth", "Initial analysis", "gemini-3-pro")

    # Update with new analysis
    test_db.set_chart_analysis(user_id, "AAPL", "growth", "Updated analysis", "gemini-3-pro")

    # Verify updated
    analysis = test_db.get_chart_analysis(user_id, "AAPL", "growth")
    assert analysis['analysis_text'] == "Updated analysis"


def test_get_nonexistent_chart_analysis(test_db):
    """Test getting chart analysis that doesn't exist returns None"""
    user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)

    analysis = test_db.get_chart_analysis(user_id, "AAPL", "growth")
    assert analysis is None


def test_chart_analysis_has_timestamp(test_db):
    """Test that generated_at timestamp is saved correctly"""
    user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)

    before_save = datetime.now()
    test_db.set_chart_analysis(user_id, "AAPL", "growth", "Test analysis", "gemini-3-pro")
    after_save = datetime.now()

    analysis = test_db.get_chart_analysis(user_id, "AAPL", "growth")
    generated_at = analysis['generated_at']

    assert before_save <= generated_at <= after_save
