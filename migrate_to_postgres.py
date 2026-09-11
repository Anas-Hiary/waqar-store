"""
Waqar Store - SQLite to PostgreSQL Safe Data Migration Script
Transfers all data from local waqar_store.db to Render PostgreSQL.
Preserves existing IDs, relationships, and updates PostgreSQL sequences.
"""
import os
import sys
import sqlite3

def get_pg_url(custom_url=None):
    url = custom_url or os.environ.get('DATABASE_URL')
    if url and url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url

def migrate(sqlite_path='waqar_store.db', pg_url=None):
    import psycopg2
    from psycopg2.extras import DictCursor

    url = get_pg_url(pg_url)
    if not url:
        print("[ERROR] No PostgreSQL URL provided and DATABASE_URL is not set.")
        print("Usage: python migrate_to_postgres.py [POSTGRES_DATABASE_URL]")
        return False

    if not os.path.exists(sqlite_path):
        print(f"[ERROR] Source SQLite database not found at: {sqlite_path}")
        return False

    print("=" * 65)
    print("  متجر وَقّار - ترحيل البيانات من SQLite إلى PostgreSQL")
    print(f"  Source: {sqlite_path}")
    masked_url = url.split('@')[-1] if '@' in url else 'PostgreSQL'
    print(f"  Target: ...@{masked_url}")
    print("=" * 65)

    # 1. Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    # 2. Connect to PostgreSQL
    try:
        pg_conn = psycopg2.connect(url)
        pg_cur = pg_conn.cursor(cursor_factory=DictCursor)
        print("[OK] Successfully connected to PostgreSQL.")
    except Exception as e:
        print(f"[ERROR] Failed to connect to PostgreSQL: {e}")
        return False

    # 3. Ensure tables exist in PostgreSQL
    from database import init_postgres_tables, reset_postgres_sequences
    print("\n[1/3] Initializing PostgreSQL tables...")
    init_postgres_tables(pg_conn)
    print("[OK] PostgreSQL schema verified.")

    # 4. Migrate tables in dependency order
    TABLES = [
        ('store_settings', 'key'),
        ('admins', 'id'),
        ('delivery_zones', 'id'),
        ('coupons', 'id'),
        ('customers', 'id'),
        ('categories', 'id'),
        ('products', 'id'),
        ('product_images', 'id'),
        ('product_variants', 'id'),
        ('orders', 'id'),
        ('order_items', 'id'),
        ('product_reviews', 'id'),
        ('wishlists', 'id'),
    ]

    print("\n[2/3] Migrating table data...")
    total_migrated = 0

    for table, pkey in TABLES:
        # Check if table exists in SQLite
        sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not sqlite_cur.fetchone():
            print(f"  - {table}: (table skipped, not in sqlite)")
            continue

        sqlite_cur.execute(f"SELECT * FROM {table}")
        rows = sqlite_cur.fetchall()
        if not rows:
            print(f"  - {table}: 0 rows found in SQLite")
            continue

        cols = [col[0] for col in sqlite_cur.description]
        cols_str = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))

        if pkey == 'key':
            insert_sql = f"""
                INSERT INTO {table} ({cols_str})
                VALUES ({placeholders})
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """
        else:
            insert_sql = f"""
                INSERT INTO {table} ({cols_str})
                VALUES ({placeholders})
                ON CONFLICT ({pkey}) DO NOTHING
            """

        inserted_count = 0
        for row in rows:
            values = [row[c] for c in cols]
            pg_cur.execute(insert_sql, values)
            inserted_count += 1

        pg_conn.commit()
        total_migrated += inserted_count
        print(f"  ✓ {table}: {inserted_count} rows migrated successfully.")

    # 5. Sync sequences
    print("\n[3/3] Syncing PostgreSQL sequences...")
    reset_postgres_sequences(pg_conn)
    print("[OK] All PostgreSQL primary key sequences synchronized.")

    sqlite_conn.close()
    pg_conn.close()

    print("\n" + "=" * 65)
    print(f"  [SUCCESS] Data migration completed! Total rows processed: {total_migrated}")
    print("=" * 65)
    return True

if __name__ == '__main__':
    arg_url = sys.argv[1] if len(sys.argv) > 1 else None
    success = migrate(pg_url=arg_url)
    sys.exit(0 if success else 1)

