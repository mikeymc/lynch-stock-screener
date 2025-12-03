# ABOUTME: Database migration to add overall_score and scored_at columns to screening_results table
# ABOUTME: Run this once to update the schema before deploying the re-scoring feature

from database import Database
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    db = Database()
    conn = db.get_connection()
    cursor = conn.cursor()

    try:
        # Add overall_score column if it doesn't exist
        cursor.execute("""
            ALTER TABLE screening_results
            ADD COLUMN IF NOT EXISTS overall_score REAL
        """)

        # Add scored_at timestamp column
        cursor.execute("""
            ALTER TABLE screening_results
            ADD COLUMN IF NOT EXISTS scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        """)

        conn.commit()
        logger.info("✓ Migration complete: added overall_score and scored_at columns")

    except Exception as e:
        conn.rollback()
        logger.error(f"✗ Migration failed: {e}")
        raise
    finally:
        db.return_connection(conn)

if __name__ == '__main__':
    migrate()
