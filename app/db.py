import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get('DB_PATH', 'data.sqlite3')


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def migrate():
    with get_conn() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              role TEXT NOT NULL CHECK(role IN ('dispatcher','master'))
            );
            CREATE TABLE IF NOT EXISTS requests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              clientName TEXT NOT NULL,
              phone TEXT NOT NULL,
              address TEXT NOT NULL,
              problemText TEXT NOT NULL,
              status TEXT NOT NULL CHECK(status IN ('new','assigned','in_progress','done','canceled')) DEFAULT 'new',
              assignedTo INTEGER NULL,
              createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (assignedTo) REFERENCES users(id)
            );
            CREATE TRIGGER IF NOT EXISTS requests_updatedAt
            AFTER UPDATE ON requests
            FOR EACH ROW
            BEGIN
              UPDATE requests SET updatedAt = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END;
            """
        )


def seed():
    with get_conn() as conn:
        c = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if c:
            return
        conn.execute("INSERT INTO users (name, role) VALUES ('dispatcher_anna', 'dispatcher')")
        conn.execute("INSERT INTO users (name, role) VALUES ('master_ivan', 'master')")
        conn.execute("INSERT INTO users (name, role) VALUES ('master_olga', 'master')")
        m1 = conn.execute("SELECT id FROM users WHERE name='master_ivan'").fetchone()[0]
        m2 = conn.execute("SELECT id FROM users WHERE name='master_olga'").fetchone()[0]
        conn.execute("""INSERT INTO requests (clientName, phone, address, problemText, status)
          VALUES ('Петр Петров', '+79990000001', 'ул. Ленина, 1', 'Не работает розетка', 'new')""")
        conn.execute("""INSERT INTO requests (clientName, phone, address, problemText, status, assignedTo)
          VALUES ('Мария Иванова', '+79990000002', 'ул. Мира, 5', 'Течет кран', 'assigned', ?)""", (m1,))
        conn.execute("""INSERT INTO requests (clientName, phone, address, problemText, status, assignedTo)
          VALUES ('Илья Смирнов', '+79990000003', 'пр. Победы, 10', 'Сломан замок', 'in_progress', ?)""", (m2,))
