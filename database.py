import os
import re
import json
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'waqar_store.db')

def get_database_url():
    """Get sanitized PostgreSQL URL from environment if present."""
    url = os.environ.get('DATABASE_URL')
    if url and url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url

def is_postgres():
    """Check if PostgreSQL should be used."""
    return bool(get_database_url())

def _replace_placeholders(sql):
    """Replace '?' with '%s' in SQL queries while preserving quoted strings."""
    result = []
    in_single_quote = False
    in_double_quote = False
    i = 0
    while i < len(sql):
        c = sql[i]
        if c == "'" and not in_double_quote:
            if in_single_quote and i + 1 < len(sql) and sql[i + 1] == "'":
                result.append("''")
                i += 2
                continue
            in_single_quote = not in_single_quote
            result.append(c)
        elif c == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            result.append(c)
        elif c == '?' and not in_single_quote and not in_double_quote:
            result.append('%s')
        else:
            result.append(c)
        i += 1
    return "".join(result)

class PostgresCursorWrapper:
    """Wrapper around psycopg2 DictCursor to provide sqlite3-compatible cursor behavior."""
    def __init__(self, raw_cursor, conn_wrapper):
        self.raw_cursor = raw_cursor
        self.conn_wrapper = conn_wrapper
        self.lastrowid = None

    def execute(self, sql, params=None):
        cleaned_sql = sql.strip()

        # 1. Translate GROUP_CONCAT to STRING_AGG for PostgreSQL
        cleaned_sql = re.sub(
            r'GROUP_CONCAT\s*\(\s*(DISTINCT\s+)?([a-zA-Z0-9_\.]+)\s*\)',
            r"STRING_AGG(\1\2, ',')",
            cleaned_sql,
            flags=re.IGNORECASE
        )

        # 2. Translate INSERT OR IGNORE to ON CONFLICT DO NOTHING
        if re.search(r'INSERT\s+OR\s+IGNORE\s+INTO', cleaned_sql, re.IGNORECASE):
            cleaned_sql = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', cleaned_sql, flags=re.IGNORECASE)
            if 'ON CONFLICT' not in cleaned_sql.upper():
                cleaned_sql = cleaned_sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'

        # 3. Handle lastrowid via RETURNING id for INSERTs
        is_insert = cleaned_sql.upper().startswith("INSERT INTO")
        appended_returning = False
        if is_insert and "RETURNING" not in cleaned_sql.upper():
            table_match = re.search(r'INSERT\s+INTO\s+([a-zA-Z0-9_]+)', cleaned_sql, re.IGNORECASE)
            table_name = table_match.group(1).lower() if table_match else ''
            if table_name not in ('store_settings',):
                cleaned_sql = cleaned_sql.rstrip().rstrip(';') + " RETURNING id"
                appended_returning = True

        # 4. Replace parameter placeholders '?' -> '%s'
        cleaned_sql = _replace_placeholders(cleaned_sql)

        # 5. Execute
        if params is not None:
            if not isinstance(params, (list, tuple)):
                params = (params,)
            self.raw_cursor.execute(cleaned_sql, params)
        else:
            self.raw_cursor.execute(cleaned_sql)

        # 6. Capture lastrowid if RETURNING id was appended
        if appended_returning:
            try:
                row = self.raw_cursor.fetchone()
                if row:
                    self.lastrowid = row['id'] if isinstance(row, dict) or hasattr(row, 'get') else row[0]
                    self.conn_wrapper._last_inserted_id = self.lastrowid
            except Exception:
                self.lastrowid = None
        else:
            self.lastrowid = self.conn_wrapper._last_inserted_id

        return self

    def executemany(self, sql, seq_of_params):
        cleaned_sql = _replace_placeholders(sql)
        return self.raw_cursor.executemany(cleaned_sql, seq_of_params)

    def fetchone(self):
        return self.raw_cursor.fetchone()

    def fetchall(self):
        return self.raw_cursor.fetchall()

    def fetchmany(self, size=None):
        return self.raw_cursor.fetchmany(size) if size is not None else self.raw_cursor.fetchmany()

    @property
    def rowcount(self):
        return self.raw_cursor.rowcount

    @property
    def description(self):
        return self.raw_cursor.description

    def close(self):
        self.raw_cursor.close()

    def __iter__(self):
        return iter(self.raw_cursor)

class PostgresConnectionWrapper:
    """Wrapper around psycopg2 connection to provide sqlite3-compatible interface."""
    def __init__(self, raw_conn):
        self.raw_conn = raw_conn
        self._last_inserted_id = None
        self._last_cursor = None

    def cursor(self):
        import psycopg2.extras
        cur = PostgresCursorWrapper(
            self.raw_conn.cursor(cursor_factory=psycopg2.extras.DictCursor),
            self
        )
        cur.lastrowid = self._last_inserted_id
        self._last_cursor = cur
        return cur

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.raw_conn.commit()

    def rollback(self):
        self.raw_conn.rollback()

    def close(self):
        self.raw_conn.close()

    @property
    def lastrowid(self):
        return self._last_inserted_id

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

def get_db():
    """Get a database connection (PostgreSQL if DATABASE_URL is set, else SQLite)."""
    if is_postgres():
        import psycopg2
        url = get_database_url()
        raw_conn = psycopg2.connect(url)
        return PostgresConnectionWrapper(raw_conn)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

def init_postgres_tables(conn):
    """Create all required tables in PostgreSQL."""
    cur = conn.cursor()

    cur.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS customers (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        email TEXT,
        password_hash TEXT,
        governorate TEXT,
        city TEXT,
        address TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT,
        image_url TEXT,
        display_order INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT,
        base_price REAL NOT NULL,
        discount_price REAL,
        sku TEXT,
        material TEXT,
        fit TEXT,
        season TEXT,
        care_instructions TEXT,
        is_featured INTEGER DEFAULT 0,
        is_new INTEGER DEFAULT 0,
        is_bestseller INTEGER DEFAULT 0,
        is_offer INTEGER DEFAULT 0,
        is_published INTEGER DEFAULT 1,
        views_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS product_images (
        id SERIAL PRIMARY KEY,
        product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
        image_url TEXT NOT NULL,
        is_primary INTEGER DEFAULT 0,
        sort_order INTEGER DEFAULT 0
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS product_variants (
        id SERIAL PRIMARY KEY,
        product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
        color_name TEXT NOT NULL,
        color_hex TEXT NOT NULL,
        size_name TEXT NOT NULL,
        stock_quantity INTEGER NOT NULL DEFAULT 0,
        sku_variant TEXT,
        UNIQUE(product_id, color_name, size_name)
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS delivery_zones (
        id SERIAL PRIMARY KEY,
        governorate_name TEXT NOT NULL,
        fee REAL NOT NULL,
        estimated_time TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS coupons (
        id SERIAL PRIMARY KEY,
        code TEXT UNIQUE NOT NULL,
        discount_type TEXT NOT NULL,
        discount_value REAL NOT NULL,
        min_order_amount REAL DEFAULT 0,
        max_uses INTEGER,
        used_count INTEGER DEFAULT 0,
        expires_at DATE,
        is_active INTEGER DEFAULT 1
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        order_number TEXT UNIQUE NOT NULL,
        customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        customer_governorate TEXT NOT NULL,
        customer_city TEXT NOT NULL,
        customer_address TEXT NOT NULL,
        notes TEXT,
        subtotal REAL NOT NULL,
        discount_amount REAL DEFAULT 0,
        coupon_code TEXT,
        delivery_fee REAL NOT NULL,
        total_amount REAL NOT NULL,
        payment_method TEXT DEFAULT 'cash_on_delivery',
        status TEXT DEFAULT 'new',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS order_items (
        id SERIAL PRIMARY KEY,
        order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
        product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
        product_name TEXT NOT NULL,
        color_name TEXT NOT NULL,
        size_name TEXT NOT NULL,
        unit_price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        total_price REAL NOT NULL,
        product_image TEXT
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS product_reviews (
        id SERIAL PRIMARY KEY,
        product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
        customer_name TEXT NOT NULL,
        rating INTEGER CHECK(rating >= 1 AND rating <= 5),
        comment TEXT NOT NULL,
        is_approved INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS wishlists (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
        product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(customer_id, product_id)
    );
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS store_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    ''')

    conn.commit()

def reset_postgres_sequences(conn):
    """Sync PostgreSQL auto-increment sequences to the max id in each table."""
    tables = [
        'admins', 'customers', 'categories', 'products', 'product_images',
        'product_variants', 'delivery_zones', 'coupons', 'orders',
        'order_items', 'product_reviews', 'wishlists'
    ]
    cur = conn.cursor()
    for table in tables:
        try:
            cur.execute(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1)
                );
            """)
        except Exception:
            pass
    conn.commit()

def init_db():
    """Initialize database tables for whichever engine is active."""
    if is_postgres():
        conn = get_db()
        init_postgres_tables(conn)
        
        # Auto-migrate from SQLite on first deploy if PostgreSQL is empty
        try:
            prod_row = conn.execute("SELECT COUNT(*) as cnt FROM products").fetchone()
            prod_count = prod_row['cnt'] if isinstance(prod_row, dict) or hasattr(prod_row, 'get') else prod_row[0]
            if prod_count == 0 and os.path.exists(DB_PATH):
                print("[PostgreSQL] Empty store detected on Render. Running automatic migration from SQLite...")
                from migrate_to_postgres import migrate
                migrate(sqlite_path=DB_PATH, pg_url=get_database_url())
        except Exception as e:
            print(f"[PostgreSQL] Auto-migration check note: {e}")
            
        conn.close()
    else:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT,
            governorate TEXT,
            city TEXT,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            image_url TEXT,
            display_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            base_price REAL NOT NULL,
            discount_price REAL,
            sku TEXT,
            material TEXT,
            fit TEXT,
            season TEXT,
            care_instructions TEXT,
            is_featured INTEGER DEFAULT 0,
            is_new INTEGER DEFAULT 0,
            is_bestseller INTEGER DEFAULT 0,
            is_offer INTEGER DEFAULT 0,
            is_published INTEGER DEFAULT 1,
            views_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            image_url TEXT NOT NULL,
            is_primary INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            color_name TEXT NOT NULL,
            color_hex TEXT NOT NULL,
            size_name TEXT NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            sku_variant TEXT,
            UNIQUE(product_id, color_name, size_name)
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS delivery_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            governorate_name TEXT NOT NULL,
            fee REAL NOT NULL,
            estimated_time TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_type TEXT NOT NULL,
            discount_value REAL NOT NULL,
            min_order_amount REAL DEFAULT 0,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            expires_at DATE,
            is_active INTEGER DEFAULT 1
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE NOT NULL,
            customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
            customer_name TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            customer_governorate TEXT NOT NULL,
            customer_city TEXT NOT NULL,
            customer_address TEXT NOT NULL,
            notes TEXT,
            subtotal REAL NOT NULL,
            discount_amount REAL DEFAULT 0,
            coupon_code TEXT,
            delivery_fee REAL NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT DEFAULT 'cash_on_delivery',
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
            product_name TEXT NOT NULL,
            color_name TEXT NOT NULL,
            size_name TEXT NOT NULL,
            unit_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            product_image TEXT
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            customer_name TEXT NOT NULL,
            rating INTEGER CHECK(rating >= 1 AND rating <= 5),
            comment TEXT NOT NULL,
            is_approved INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS wishlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(customer_id, product_id)
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS store_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        ''')

        conn.commit()
        conn.close()

def get_setting(key, default=''):
    """Fetch a store setting by key."""
    conn = get_db()
    row = conn.execute("SELECT value FROM store_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return row['value'] if isinstance(row, dict) or hasattr(row, 'get') else row[0]
    return default

def set_setting(key, value):
    """Set or update a store setting."""
    conn = get_db()
    conn.execute(
        "INSERT INTO store_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value))
    )
    conn.commit()
    conn.close()

def get_all_settings():
    """Fetch all store settings as a dictionary."""
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM store_settings").fetchall()
    conn.close()
    result = {}
    for row in rows:
        k = row['key'] if isinstance(row, dict) or hasattr(row, 'get') else row[0]
        v = row['value'] if isinstance(row, dict) or hasattr(row, 'get') else row[1]
        result[k] = v
    return result

def generate_order_number():
    """Generate a clean unique Jordanian order number like #WAQ-1001."""
    conn = get_db()
    last = conn.execute("SELECT id FROM orders ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if last:
        last_id = last['id'] if isinstance(last, dict) or hasattr(last, 'get') else last[0]
        next_id = last_id + 1001
    else:
        next_id = 1001
    return f"#WAQ-{next_id}"
