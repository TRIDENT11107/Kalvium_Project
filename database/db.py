"""Legacy SQLite persistence helper for the original business-module tests. The web application uses PostgreSQL in backend/app/database.py."""
import json, sqlite3
from pathlib import Path
from contextlib import contextmanager
from config import DATABASE_URL

def connect():
    Path(DATABASE_URL).parent.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(DATABASE_URL); db.row_factory=sqlite3.Row; db.execute("PRAGMA foreign_keys=ON")
    return db

@contextmanager
def connection():
    db=connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    with connection() as d:
        d.executescript("""CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, title TEXT NOT NULL, objective TEXT NOT NULL, lesson_json TEXT NOT NULL, sources_json TEXT NOT NULL DEFAULT '[]', factual_json TEXT, instructional_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY, lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE, lesson_json TEXT NOT NULL, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);""")

def create_lesson(title, objective, lesson, sources, factual=None, instructional=None):
    with connection() as d:
        cur=d.execute("INSERT INTO lessons(title,objective,lesson_json,sources_json,factual_json,instructional_json) VALUES(?,?,?,?,?,?)",(title,objective,json.dumps(lesson),json.dumps(sources),json.dumps(factual) if factual else None,json.dumps(instructional) if instructional else None))
        lid=cur.lastrowid
        d.execute("INSERT INTO revisions(lesson_id,lesson_json,note) VALUES(?,?,?)",(lid,json.dumps(lesson),"Generated"))
        return lid

def update_lesson(lid, title, objective, lesson, factual=None, instructional=None, note="Instructor revision"):
    with connection() as d:
        d.execute("UPDATE lessons SET title=?,objective=?,lesson_json=?,factual_json=COALESCE(?,factual_json),instructional_json=COALESCE(?,instructional_json),updated_at=CURRENT_TIMESTAMP WHERE id=?",(title,objective,json.dumps(lesson),json.dumps(factual) if factual else None,json.dumps(instructional) if instructional else None,lid))
        d.execute("INSERT INTO revisions(lesson_id,lesson_json,note) VALUES(?,?,?)",(lid,json.dumps(lesson),note))

def get_lesson(lid):
    with connection() as d:
        row=d.execute("SELECT * FROM lessons WHERE id=?",(lid,)).fetchone()
        return dict(row) if row else None

def list_lessons():
    with connection() as d: return [dict(x) for x in d.execute("SELECT id,title,objective,created_at,updated_at FROM lessons ORDER BY updated_at DESC")]

def delete_lesson(lid):
    with connection() as d: d.execute("DELETE FROM lessons WHERE id=?",(lid,))

def get_revisions(lid):
    with connection() as d: return [dict(x) for x in d.execute("SELECT * FROM revisions WHERE lesson_id=? ORDER BY id DESC",(lid,))]
