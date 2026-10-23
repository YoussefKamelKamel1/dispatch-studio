from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException, Request

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return secrets.token_hex(12)


@dataclass
class Settings:
    data_dir: Path = ROOT / 'data'
    api_key: str = ''
    model: str = 'gpt-4.1-mini'
    mode: str = 'demo'
    email: str = 'demo@example.com'
    password: str = 'demo-password'
    reviewer_name: str = 'Youssef Kamel'
    base_url: str = 'http://127.0.0.1:8012'
    sandbox_token: str = ''
    worker: bool = True
    seed: bool = True
    website_provider: str = 'local'
    social_provider: str = 'sandbox'
    wordpress_url: str = ''
    wordpress_user: str = ''
    wordpress_password: str = ''
    linkedin_token: str = ''
    linkedin_author: str = ''
    linkedin_version: str = '202610'

    @classmethod
    def environment(cls):
        key = os.getenv('OPENAI_API_KEY', '')
        mode = os.getenv('AI_MODE', 'auto')
        return cls(data_dir=Path(os.getenv('DATA_DIR', str(ROOT / 'data'))).resolve(),
                   api_key=key, model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'),
                   mode=('live' if key else 'demo') if mode == 'auto' else mode,
                   email=os.getenv('REVIEWER_EMAIL', 'demo@example.com'),
                   password=os.getenv('REVIEWER_PASSWORD', 'demo-password'),
                   reviewer_name=os.getenv('REVIEWER_NAME', 'Youssef Kamel'),
                   base_url=os.getenv('DISPATCH_BASE_URL', 'http://127.0.0.1:8012').rstrip('/'),
                   sandbox_token=os.getenv('SANDBOX_API_TOKEN', ''),
                   website_provider=os.getenv('WEBSITE_PROVIDER', 'local').strip().lower(),
                   social_provider=os.getenv('SOCIAL_PROVIDER', 'sandbox').strip().lower(),
                   wordpress_url=os.getenv('WORDPRESS_URL', '').strip().rstrip('/'),
                   wordpress_user=os.getenv('WORDPRESS_USERNAME', '').strip(),
                   wordpress_password=os.getenv('WORDPRESS_APPLICATION_PASSWORD', ''),
                   linkedin_token=os.getenv('LINKEDIN_ACCESS_TOKEN', '').strip(),
                   linkedin_author=os.getenv('LINKEDIN_AUTHOR_URN', '').strip(),
                   linkedin_version=os.getenv('LINKEDIN_API_VERSION', '202610').strip())


class Database:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY,name TEXT NOT NULL,color TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS items (
              id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),title TEXT NOT NULL,
              source TEXT NOT NULL,update_type TEXT NOT NULL,audience TEXT NOT NULL,cta TEXT NOT NULL,
              status TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,provider TEXT NOT NULL DEFAULT '',
              warnings TEXT NOT NULL DEFAULT '[]',error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revisions (
              item_id TEXT NOT NULL REFERENCES items(id),revision INTEGER NOT NULL,
              content TEXT NOT NULL,channels TEXT NOT NULL,created_at TEXT NOT NULL,
              PRIMARY KEY(item_id,revision)
            );
            CREATE TABLE IF NOT EXISTS approvals (
              id TEXT PRIMARY KEY,item_id TEXT NOT NULL REFERENCES items(id),revision INTEGER NOT NULL,
              fingerprint TEXT NOT NULL,channels TEXT NOT NULL,reviewer TEXT NOT NULL,
              status TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(item_id,revision)
            );
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,approval_id TEXT NOT NULL REFERENCES approvals(id),item_id TEXT NOT NULL REFERENCES items(id),
              revision INTEGER NOT NULL,channel TEXT NOT NULL,status TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,error TEXT,external_id TEXT,url TEXT,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(approval_id,channel)
            );
            CREATE TABLE IF NOT EXISTS attempts (
              id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),status TEXT NOT NULL,
              detail TEXT NOT NULL,created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS posts (
              id TEXT PRIMARY KEY,job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),channel TEXT NOT NULL,
              title TEXT NOT NULL,body TEXT NOT NULL,slug TEXT NOT NULL UNIQUE,url TEXT NOT NULL,created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity (
              id TEXT PRIMARY KEY,item_id TEXT,action TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sandbox_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS jobs_state ON jobs(status,created_at);
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'destination' not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN destination TEXT NOT NULL DEFAULT ''")


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def fingerprint(content, channels):
    import json
    return hashlib.sha256(json.dumps({'content': content, 'channels': sorted(channels)},
                                     sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require_session(request: Request):
    import time
    token = request.cookies.get('dispatch_session', '')
    with request.app.state.db.connection() as db:
        row = db.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?',
                         (token_hash(token), time.time())).fetchone()
    if not row:
        raise HTTPException(401, 'Sign in to continue.')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), row['csrf']):
        raise HTTPException(403, 'Your session changed. Refresh before continuing.')
    return request.app.state.settings.email
