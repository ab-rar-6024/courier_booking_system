import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    conn = psycopg2.connect(
        host="aws-1-ap-southeast-1.pooler.supabase.com",
        port=6543,
        dbname="postgres",
        user="postgres.fqiyiarxocjhfbaopwyh",
        password=os.environ.get("DB_PASSWORD", "NtSVdOBjFlofDx0H"),
        cursor_factory=RealDictCursor
    )
    return conn