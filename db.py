import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    """Return a PostgreSQL database connection using Supabase URL from environment."""
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL environment variable not set. "
                           "Please set it to your Supabase PostgreSQL connection string.")
    # RealDictCursor returns rows as dictionaries (like mysql.connector's dictionary=True)
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn
"Abrar2005@%24-> supabase password"
