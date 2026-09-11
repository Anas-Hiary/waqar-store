"""
Waqar Store - PostgreSQL Connection & Health Check Script
Usage:
    python test_db_connection.py [OPTIONAL_POSTGRES_URL]
"""
import os
import sys

def check_connection(custom_url=None):
    from database import get_database_url, is_postgres
    import psycopg2
    from psycopg2.extras import DictCursor

    url = custom_url or get_database_url()
    if not url:
        print("[!] No DATABASE_URL found in environment or arguments.")
        print("    You can test by running:")
        print("    python test_db_connection.py \"postgresql://user:password@host/dbname\"")
        return False

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    masked_target = url.split('@')[-1] if '@' in url else 'PostgreSQL'
    print(f"Connecting to PostgreSQL (...@{masked_target})...")

    try:
        conn = psycopg2.connect(url, connect_timeout=10)
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"[OK] Connected successfully!\n     Version: {version[:50]}...")

        # Check tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = [r[0] for r in cur.fetchall()]

        if not tables:
            print("[INFO] Connected, but no tables exist yet. Run 'init_db()' or 'python migrate_to_postgres.py' to initialize.")
        else:
            print(f"[OK] Found {len(tables)} tables in PostgreSQL database:")
            for t in tables:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "{t}";')
                    cnt = cur.fetchone()[0]
                    print(f"     - {t}: {cnt} rows")
                except Exception:
                    pass

        conn.close()
        return True

    except Exception as e:
        print(f"[ERROR] Failed to connect to PostgreSQL: {e}")
        return False

if __name__ == '__main__':
    arg_url = sys.argv[1] if len(sys.argv) > 1 else None
    check_connection(arg_url)

