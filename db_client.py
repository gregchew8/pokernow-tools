import os
import urllib.parse
import sqlite3

# Try to import pg8000, fallback if not available
try:
    import pg8000.dbapi
    HAS_PG8000 = True
except ImportError:
    HAS_PG8000 = False

class DBClient:
    def __init__(self):
        self.db_url = os.environ.get("DATABASE_URL", "").strip()
        self.is_postgres = False
        self.conn = None
        
        # Determine connection type
        if self.db_url and (self.db_url.startswith("postgresql://") or self.db_url.startswith("postgres://")):
            if HAS_PG8000:
                self.is_postgres = True
            else:
                print("[DBClient] WARNING: DATABASE_URL provided but pg8000 is not installed. Falling back to local SQLite.")
        
        self.connect()
        self.setup_tables()

    def connect(self):
        if self.is_postgres:
            try:
                result = urllib.parse.urlparse(self.db_url)
                username = result.username
                password = result.password
                database = result.path[1:]
                hostname = result.hostname
                port = result.port or 5432
                
                # Connect via pg8000 dbapi
                self.conn = pg8000.dbapi.connect(
                    user=username,
                    password=password,
                    host=hostname,
                    port=port,
                    database=database
                )
                print("[DBClient] Successfully connected to PostgreSQL database on Railway.")
                return
            except Exception as e:
                print(f"[DBClient] Failed to connect to PostgreSQL: {e}. Falling back to SQLite.")
                self.is_postgres = False

        # SQLite fallback
        db_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(db_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        sqlite_path = os.path.join(data_dir, "poker_stats.db")
        self.conn = sqlite3.connect(sqlite_path)
        # Enable dictionary access
        self.conn.row_factory = sqlite3.Row
        print(f"[DBClient] Connected to local SQLite database at {sqlite_path}")

    def execute(self, sql, params=None):
        if params is None:
            params = ()
        
        # Convert paramstyle if needed
        if self.is_postgres:
            sql = sql.replace("?", "%s")
        
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql, params)
            return cursor
        except Exception as e:
            # If postgres connection died, try to reconnect once
            if self.is_postgres:
                print(f"[DBClient] Error executing SQL: {e}. Attempting reconnect...")
                try:
                    self.connect()
                    cursor = self.conn.cursor()
                    cursor.execute(sql, params)
                    return cursor
                except Exception as re_err:
                    print(f"[DBClient] Reconnect failed: {re_err}")
            raise e

    def commit(self):
        if self.conn:
            self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()

    def setup_tables(self):
        # Create sessions table
        self.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                ledger_date TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create player ledger records table
        id_type = "SERIAL PRIMARY KEY" if self.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        self.execute(f"""
            CREATE TABLE IF NOT EXISTS player_ledger_records (
                id {id_type},
                player_nickname TEXT NOT NULL,
                player_id TEXT NOT NULL,
                session_start_at TEXT NOT NULL,
                session_end_at TEXT,
                buy_in INTEGER NOT NULL,
                buy_out REAL,
                stack INTEGER,
                net INTEGER NOT NULL,
                ledger_date TEXT NOT NULL,
                FOREIGN KEY (ledger_date) REFERENCES sessions (ledger_date)
            )
        """)
        
        # Postgres index creation
        try:
            self.execute("CREATE INDEX IF NOT EXISTS idx_records_player ON player_ledger_records(player_id)")
            self.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON player_ledger_records(ledger_date)")
        except Exception as e:
            # SQLite handles index creation fine, but just in case
            pass
            
        self.commit()

    def insert_session(self, ledger_date, filename):
        try:
            self.execute("INSERT INTO sessions (ledger_date, filename) VALUES (?, ?)", (ledger_date, filename))
            self.commit()
            return True
        except Exception as e:
            # If duplicate key, ignore
            self.conn.rollback()
            return False

    def insert_ledger_record(self, nickname, player_id, start_at, end_at, buy_in, buy_out, stack, net, ledger_date):
        # Check if record already exists to avoid duplicate runs
        res = self.execute(
            "SELECT id FROM player_ledger_records WHERE player_id = ? AND ledger_date = ?", 
            (player_id, ledger_date)
        ).fetchone()
        
        if res:
            return False # Duplicate
            
        self.execute("""
            INSERT INTO player_ledger_records (
                player_nickname, player_id, session_start_at, session_end_at, 
                buy_in, buy_out, stack, net, ledger_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nickname, player_id, start_at, end_at, buy_in, buy_out, stack, net, ledger_date))
        self.commit()
        return True

    def get_player_stats(self, start_date=None, end_date=None):
        query = """
            SELECT 
                player_nickname,
                player_id,
                COUNT(id) as total_sessions,
                SUM(net) as total_net,
                SUM(buy_in) as total_buy_in,
                AVG(buy_in) as avg_buy_in,
                SUM(CASE WHEN net > 0 THEN 1 ELSE 0 END) as win_count
            FROM player_ledger_records
            WHERE 1=1
        """
        params = []
        if start_date:
            query += " AND ledger_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND ledger_date <= ?"
            params.append(end_date)
            
        query += " GROUP BY player_nickname, player_id ORDER BY total_net DESC"
        
        cursor = self.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        # Convert to dictionary output
        result = []
        for r in rows:
            if self.is_postgres:
                result.append({
                    "player_nickname": r[0],
                    "player_id": r[1],
                    "total_sessions": int(r[2]),
                    "total_net": int(r[3]),
                    "total_buy_in": int(r[4]),
                    "avg_buy_in": float(r[5]),
                    "win_count": int(r[6])
                })
            else:
                result.append({
                    "player_nickname": r["player_nickname"],
                    "player_id": r["player_id"],
                    "total_sessions": r["total_sessions"],
                    "total_net": r["total_net"],
                    "total_buy_in": r["total_buy_in"],
                    "avg_buy_in": r["avg_buy_in"],
                    "win_count": r["win_count"]
                })
        return result

    def get_player_history(self, start_date=None, end_date=None):
        query = """
            SELECT player_nickname, player_id, net, ledger_date
            FROM player_ledger_records
            WHERE 1=1
        """
        params = []
        if start_date:
            query += " AND ledger_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND ledger_date <= ?"
            params.append(end_date)
            
        query += " ORDER BY ledger_date ASC, player_nickname ASC"
        
        cursor = self.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        result = []
        for r in rows:
            if self.is_postgres:
                result.append({
                    "player_nickname": r[0],
                    "player_id": r[1],
                    "net": int(r[2]),
                    "ledger_date": r[3]
                })
            else:
                result.append({
                    "player_nickname": r["player_nickname"],
                    "player_id": r["player_id"],
                    "net": r["net"],
                    "ledger_date": r["ledger_date"]
                })
        return result
