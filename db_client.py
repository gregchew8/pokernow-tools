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

    def load_venmo_mapping(self):
        mapping = {}
        import csv
        db_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(db_dir, "payment_info.csv")
        if os.path.exists(filepath):
            try:
                with open(filepath, newline='', encoding='utf-8') as file:
                    reader = csv.reader(file)
                    headers = [h.strip() for h in next(reader)]
                    for row in reader:
                        mapped_row = dict(zip(headers, row))
                        nickname = mapped_row.get("PN Alias")
                        venmo = mapped_row.get("Venmo / other")
                        if nickname and venmo:
                            mapping[nickname.strip().lower()] = venmo.strip()
            except Exception as e:
                print(f"[DBClient] Error reading payment_info.csv: {e}")
        return mapping

    def get_player_stats(self, start_date=None, end_date=None):
        venmo_map = self.load_venmo_mapping()
        
        query = """
            SELECT player_nickname, player_id, buy_in, net
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
            
        cursor = self.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        groups = {}
        for r in rows:
            if self.is_postgres:
                nickname = r[0]
                pid = r[1]
                buy_in = int(r[2])
                net = int(r[3])
            else:
                nickname = r["player_nickname"]
                pid = r["player_id"]
                buy_in = r["buy_in"]
                net = r["net"]
                
            import re
            venmo_id = venmo_map.get(nickname.strip().lower())
            if not venmo_id:
                # Strip trailing numbers, spaces, and punctuation (e.g. "Billy Berns 1" -> "Billy Berns")
                stripped = re.sub(r'[\s\d\-\#\_!]+$', '', nickname).strip().lower()
                venmo_id = venmo_map.get(stripped)
            
            # Filter out entries not tied to a valid Venmo ID (e.g. placeholders, unmapped players)
            if not venmo_id or not venmo_id.startswith('@'):
                continue
                
            resolved_id = venmo_id
            
            if resolved_id not in groups:
                groups[resolved_id] = {
                    "player_nickname": resolved_id,
                    "player_id": resolved_id,
                    "buy_ins": [],
                    "nets": [],
                    "sessions_count": 0,
                    "win_count": 0,
                    "aliases": set()
                }
            
            groups[resolved_id]["buy_ins"].append(buy_in)
            groups[resolved_id]["nets"].append(net)
            groups[resolved_id]["sessions_count"] += 1
            groups[resolved_id]["aliases"].add(nickname)
            if net > 0:
                groups[resolved_id]["win_count"] += 1
                
        result = []
        for rid, g in groups.items():
            total_net = sum(g["nets"]) / 100.0
            total_buy_in = sum(g["buy_ins"]) / 100.0
            avg_buy_in = (sum(g["buy_ins"]) / len(g["buy_ins"])) / 100.0 if g["buy_ins"] else 0.0
            
            # Sort aliases and omit the Venmo ID itself if it matches
            sorted_aliases = sorted(list(g["aliases"]))
            
            result.append({
                "player_nickname": g["player_nickname"],
                "player_id": g["player_id"],
                "total_sessions": g["sessions_count"],
                "total_net": round(total_net, 2),
                "total_buy_in": round(total_buy_in, 2),
                "avg_buy_in": round(avg_buy_in, 2),
                "win_count": g["win_count"],
                "aliases": sorted_aliases
            })
            
        result.sort(key=lambda x: x["player_nickname"].lower())
        return result

    def get_player_history(self, start_date=None, end_date=None):
        venmo_map = self.load_venmo_mapping()
        
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
            
        cursor = self.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        history_map = {}
        for r in rows:
            if self.is_postgres:
                nickname = r[0]
                net = int(r[2])
                date = r[3]
            else:
                nickname = r["player_nickname"]
                net = r["net"]
                date = r["ledger_date"]
                
            import re
            venmo_id = venmo_map.get(nickname.strip().lower())
            if not venmo_id:
                stripped = re.sub(r'[\s\d\-\#\_!]+$', '', nickname).strip().lower()
                venmo_id = venmo_map.get(stripped)
            
            if not venmo_id or not venmo_id.startswith('@'):
                continue
                
            resolved_id = venmo_id
            
            key = (resolved_id, date)
            history_map[key] = history_map.get(key, 0) + net
            
        result = []
        for (resolved_id, date), net in history_map.items():
            result.append({
                "player_nickname": resolved_id,
                "player_id": resolved_id,
                "net": round(net / 100.0, 2),
                "ledger_date": date
            })
            
        result.sort(key=lambda x: (x["ledger_date"], x["player_nickname"].lower()))
        return result
