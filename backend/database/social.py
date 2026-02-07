# ABOUTME: Social sentiment tracking and AI agent conversation storage
# ABOUTME: Manages Reddit/social posts and chat agent message history

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import json

logger = logging.getLogger(__name__)


class SocialMixin:

    def save_social_sentiment(self, posts: List[Dict[str, Any]]) -> int:
        """
        Batch save social sentiment posts (from Reddit).

        Args:
            posts: List of post dicts with id, symbol, title, score, etc.

        Returns:
            Number of posts saved/updated
        """
        if not posts:
            return 0

        sql = """
            INSERT INTO social_sentiment
            (id, symbol, source, subreddit, title, selftext, url, author,
             score, upvote_ratio, num_comments, sentiment_score, created_utc, published_at,
             conversation_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                score = EXCLUDED.score,
                upvote_ratio = EXCLUDED.upvote_ratio,
                num_comments = EXCLUDED.num_comments,
                sentiment_score = EXCLUDED.sentiment_score,
                conversation_json = EXCLUDED.conversation_json,
                fetched_at = CURRENT_TIMESTAMP
        """

        count = 0
        for post in posts:
            try:
                # Serialize conversation data to JSON
                import json
                conversation = post.get('conversation')
                conversation_json = json.dumps(conversation) if conversation else None

                args = (
                    post.get('id'),
                    post.get('symbol'),
                    post.get('source', 'reddit'),
                    post.get('subreddit'),
                    post.get('title'),
                    post.get('selftext', '')[:10000],  # Limit text size
                    post.get('url'),
                    post.get('author'),
                    post.get('score', 0),
                    post.get('upvote_ratio'),
                    post.get('num_comments', 0),
                    post.get('sentiment_score'),
                    post.get('created_utc'),
                    post.get('created_at'),
                    conversation_json,
                )
                self.write_queue.put((sql, args))
                count += 1
            except Exception as e:
                logger.error(f"Error saving social sentiment post {post.get('id')}: {e}")

        return count

    def get_social_sentiment(self, symbol: str, limit: int = 20,
                            min_score: int = 0) -> List[Dict[str, Any]]:
        """
        Get social sentiment posts for a symbol.

        Args:
            symbol: Stock ticker
            limit: Max posts to return
            min_score: Minimum score filter

        Returns:
            List of post dicts sorted by score descending
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, source, subreddit, title, selftext, url, author,
                       score, upvote_ratio, num_comments, sentiment_score,
                       created_utc, published_at, fetched_at, conversation_json
                FROM social_sentiment
                WHERE symbol = %s AND score >= %s
                ORDER BY score DESC
                LIMIT %s
            """, (symbol, min_score, limit))

            rows = cursor.fetchall()
            return [{
                'id': row[0],
                'symbol': row[1],
                'source': row[2],
                'subreddit': row[3],
                'title': row[4],
                'selftext': row[5],
                'url': row[6],
                'author': row[7],
                'score': row[8],
                'upvote_ratio': row[9],
                'num_comments': row[10],
                'sentiment_score': row[11],
                'created_utc': row[12],
                'published_at': row[13].isoformat() if row[13] else None,
                'fetched_at': row[14].isoformat() if row[14] else None,
                'conversation': row[15],  # JSONB is auto-parsed by psycopg2
            } for row in rows]
        finally:
            self.return_connection(conn)

    def get_social_sentiment_summary(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """
        Get aggregated social sentiment summary for a symbol.

        Args:
            symbol: Stock ticker
            days: Number of days to look back

        Returns:
            Dict with post_count, avg_score, avg_sentiment, top_subreddits
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as post_count,
                    AVG(score) as avg_score,
                    AVG(sentiment_score) as avg_sentiment,
                    SUM(num_comments) as total_comments
                FROM social_sentiment
                WHERE symbol = %s
                  AND published_at >= NOW() - INTERVAL '%s days'
            """, (symbol, days))

            row = cursor.fetchone()

            # Get top subreddits
            cursor.execute("""
                SELECT subreddit, COUNT(*) as cnt
                FROM social_sentiment
                WHERE symbol = %s
                  AND published_at >= NOW() - INTERVAL '%s days'
                GROUP BY subreddit
                ORDER BY cnt DESC
                LIMIT 5
            """, (symbol, days))

            subreddits = [{'name': r[0], 'count': r[1]} for r in cursor.fetchall()]

            return {
                'post_count': row[0] or 0,
                'avg_score': round(row[1], 1) if row[1] else 0,
                'avg_sentiment': round(row[2], 2) if row[2] else 0,
                'total_comments': row[3] or 0,
                'top_subreddits': subreddits,
            }
        finally:
            self.return_connection(conn)

    # =========================================================================
    # Agent Chat Methods
    # =========================================================================

    def create_agent_conversation(self, user_id: int) -> int:
        """
        Create a new agent conversation.

        Args:
            user_id: User ID

        Returns:
            conversation_id
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agent_conversations (user_id, created_at, last_message_at)
                VALUES (%s, NOW(), NOW())
                RETURNING id
            """, (user_id,))
            conversation_id = cursor.fetchone()[0]
            conn.commit()
            return conversation_id
        finally:
            self.return_connection(conn)

    def get_agent_conversations(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get user's agent conversations, ordered by last_message_at DESC.

        Args:
            user_id: User ID
            limit: Maximum number of conversations to return

        Returns:
            List of conversation dicts
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, created_at, last_message_at
                FROM agent_conversations
                WHERE user_id = %s
                ORDER BY last_message_at DESC
                LIMIT %s
            """, (user_id, limit))

            rows = cursor.fetchall()
            return [
                {
                    'id': row[0],
                    'title': row[1],
                    'created_at': row[2].isoformat() if row[2] else None,
                    'last_message_at': row[3].isoformat() if row[3] else None,
                }
                for row in rows
            ]
        finally:
            self.return_connection(conn)

    def get_agent_messages(self, conversation_id: int) -> List[Dict[str, Any]]:
        """
        Get all messages for a conversation, ordered by created_at ASC.

        Args:
            conversation_id: Conversation ID

        Returns:
            List of message dicts
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, role, content, tool_calls, created_at
                FROM agent_messages
                WHERE conversation_id = %s
                ORDER BY created_at ASC
            """, (conversation_id,))

            rows = cursor.fetchall()
            return [
                {
                    'id': row[0],
                    'role': row[1],
                    'content': row[2],
                    'tool_calls': row[3],
                    'created_at': row[4].isoformat() if row[4] else None,
                }
                for row in rows
            ]
        finally:
            self.return_connection(conn)

    def save_agent_message(self, conversation_id: int, role: str, content: str, tool_calls: dict = None):
        """
        Save a message to conversation and update last_message_at.

        Args:
            conversation_id: Conversation ID
            role: 'user' or 'assistant'
            content: Message content
            tool_calls: Optional tool execution details (JSON)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # Insert message
            import json
            cursor.execute("""
                INSERT INTO agent_messages (conversation_id, role, content, tool_calls, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (conversation_id, role, content, json.dumps(tool_calls) if tool_calls else None))

            # Update conversation last_message_at
            cursor.execute("""
                UPDATE agent_conversations
                SET last_message_at = NOW()
                WHERE id = %s
            """, (conversation_id,))

            conn.commit()
        finally:
            self.return_connection(conn)

    def update_conversation_title(self, conversation_id: int, title: str):
        """
        Update conversation title (called after first message).

        Args:
            conversation_id: Conversation ID
            title: Conversation title (truncated from first message)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agent_conversations
                SET title = %s
                WHERE id = %s
            """, (title[:50], conversation_id))  # Truncate to 50 chars
            conn.commit()
        finally:
            self.return_connection(conn)

    def delete_agent_conversation(self, conversation_id: int, user_id: int) -> bool:
        """
        Delete an agent conversation (with ownership verification).

        Args:
            conversation_id: Conversation ID to delete
            user_id: User ID (for ownership check)

        Returns:
            True if deleted, False if not found or not owned by user
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Delete only if owned by user (CASCADE will delete messages)
            cursor.execute("""
                DELETE FROM agent_conversations
                WHERE id = %s AND user_id = %s
            """, (conversation_id, user_id))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self.return_connection(conn)
