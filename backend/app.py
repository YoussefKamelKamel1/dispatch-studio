from __future__ import annotations

import csv
import hmac
import html
import io
import json
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .ai import ChannelDraft
from .core import ROOT, Database, Settings, fingerprint, now, require_session, token_hash, uid
from .fixtures import SAMPLE, seed
from .workflow import CHANNELS, event, generate_one, publish_one
from .connectors import check_wordpress, configuration_error, connection_report, destination, destination_json
from .connections import ai_connection, check_ai


class Login(BaseModel):
    email: str
    password: str


class NewItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str
    title: str = Field(min_length=3, max_length=200)
    source: str = Field(min_length=30, max_length=30000)
    update_type: Literal['Project update', 'Research findings', 'Event announcement', 'Project description'] = 'Project update'
    audience: str = Field(default='Research partners and organizational stakeholders', max_length=1000)
    cta: str = Field(default='', max_length=1000)


class Content(BaseModel):
    model_config = ConfigDict(extra='forbid')
    linkedin: ChannelDraft
    newsletter: ChannelDraft
    website: ChannelDraft


class Edit(BaseModel):
    revision: int
    content: Content
    channels: list[Literal['website', 'linkedin']]


class Approval(BaseModel):
    revision: int
    channels: list[Literal['website', 'linkedin']] = Field(min_length=1)
    destinations: dict | None = None


class Rejection(BaseModel):
    revision: int
    reason: str = Field(min_length=3, max_length=1000)


class Ready(BaseModel):
    revision: int


class PublishRequest(BaseModel):
    job_id: str


class SandboxFailure(BaseModel):
    channel: Literal['website', 'linkedin'] = 'linkedin'


def read_item(db, item_id):
    row = db.execute('SELECT i.*,p.name AS project_name,p.color AS project_color FROM items i JOIN projects p ON p.id=i.project_id WHERE i.id=?', (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Content item not found.')
    item = dict(row)
    rev = db.execute('SELECT * FROM revisions WHERE item_id=? AND revision=?', (item_id, item['revision'])).fetchone()
    item['content'] = json.loads(rev['content']) if rev else None
    item['channels'] = json.loads(rev['channels']) if rev else []
    item['warnings'] = json.loads(item['warnings'])
    item['jobs'] = [dict(row) for row in db.execute('SELECT * FROM jobs WHERE item_id=? ORDER BY created_at DESC', (item_id,))]
    item['approvals'] = [dict(row) for row in db.execute('SELECT id,revision,channels,reviewer,status,created_at FROM approvals WHERE item_id=? ORDER BY created_at DESC', (item_id,))]
    return item


def check_revision(item, expected):
    if item['revision'] != expected:
        raise HTTPException(409, 'A newer revision exists. Reload and review it before continuing.')


def check_not_publishing(db, item_id):
    if db.execute("SELECT id FROM jobs WHERE item_id=? AND status='publishing'", (item_id,)).fetchone():
        raise HTTPException(409, 'A publication request is in flight. Wait for its outcome before editing or rejecting.')


def revoke(db, item_id):
    db.execute("UPDATE approvals SET status='revoked' WHERE item_id=? AND status='active'", (item_id,))
    db.execute("UPDATE jobs SET status='cancelled',error='Approval revoked by a later edit or rejection.',updated_at=? WHERE item_id=? AND status IN ('queued','reconciling','failed','uncertain')", (now(), item_id))


def published_page(title, body, stamp, social=False):
    esc = html.escape
    paragraphs = ''.join('<p>' + esc(p).replace('\n', '<br>') + '</p>' for p in re.split(r'\n\s*\n', body) if p.strip())
    label = 'LINKEDIN PUBLISHING SANDBOX' if social else 'DISPATCH / RESEARCH & IDEAS'
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>''' + esc(title) + ''' · Dispatch</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f6f3ed;color:#292f2c;font-family:Arial,sans-serif}header{padding:28px 7%;border-bottom:1px solid #deddd5;display:flex;justify-content:space-between;align-items:center}header a{font-family:Georgia,serif;font-size:25px;color:#303c32;text-decoration:none}header span{font-size:10px;letter-spacing:2px;color:#8b8174}main{max-width:800px;margin:65px auto;padding:0 28px 70px}.eyebrow{font-size:10px;letter-spacing:2px;color:#ab654c;font-weight:bold}h1{font-family:Georgia,serif;font-weight:400;font-size:clamp(34px,5vw,55px);line-height:1.15;letter-spacing:-1.7px;margin:24px 0}.meta{font-size:12px;color:#9a9286;padding-bottom:25px;border-bottom:1px solid #deddd5;margin-bottom:32px}article p{font-family:Georgia,serif;font-size:20px;line-height:1.9;color:#50534a;margin:25px 0}footer{font-size:11px;color:#918779;border-top:1px solid #deddd5;padding-top:25px;margin-top:50px;line-height:1.8}.banner{background:#ede4d7;border-bottom:1px solid #ded2c0;text-align:center;padding:12px;font-size:11px;color:#8b7053}a{color:#9b5b46}.social{max-width:620px;background:white;border:1px solid #deddd5;border-radius:10px;padding:35px;margin-top:40px}.social article p{font-family:Arial,sans-serif;font-size:16px;line-height:1.8}.social h1{font-family:Arial,sans-serif;font-size:27px;letter-spacing:-.6px}
    </style></head><body><div class="banner">Demonstration publication · Sample content · ''' + ('This is a local simulation, not a post on LinkedIn.' if social else 'Published to the local test CMS after human approval.') + '''</div><header><a href="/">Dispatch<span style="color:#ac6953">.</span></a><span>DISPATCH / PUBLICATIONS</span></header><main class="''' + ('social' if social else '') + '''"><span class="eyebrow">''' + label + '</span><h1>' + esc(title) + '</h1><div class="meta">Published ' + esc(stamp[:10]) + ' · Dispatch research team</div><article>' + paragraphs + '</article><footer>This page was created by the approval-triggered publishing workflow.<br><a href="/">Return to the editorial workspace ↗</a></footer></main></body></html>'


def create_app(settings=None, generator=None, publisher=None):
    settings = settings or Settings.environment()
    database = Database(settings.data_dir / 'dispatch.sqlite3')
    database.initialize()
    seed(database, settings)
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(app):
        with database.connection() as db:
            db.execute("UPDATE items SET status='queued_generation' WHERE status='generating'")
            db.execute("UPDATE jobs SET status='uncertain',error='Application restarted during publication. Check outcome before retrying.' WHERE status='publishing'")
            for row in db.execute("SELECT DISTINCT item_id FROM jobs WHERE status='uncertain'").fetchall():
                from .workflow import item_status
                item_status(db, row['item_id'])
        def run():
            while not stop.is_set():
                try:
                    worked = publish_one(app)
                    worked = generate_one(app) or worked
                    if not worked:
                        stop.wait(0.4)
                except Exception:
                    stop.wait(1)
        worker = threading.Thread(target=run, name='dispatch-worker', daemon=True)
        if settings.worker:
            worker.start()
        yield
        stop.set()
        if settings.worker:
            worker.join(timeout=3)

    app = FastAPI(title='Dispatch — Content & Publishing Agent', lifespan=lifespan)
    app.state.db, app.state.settings = database, settings
    app.state.generator, app.state.publisher = generator, publisher
    app.state.sandbox_token = settings.sandbox_token or secrets.token_urlsafe(32)
    app.state.login_attempts = {}
    app.state.connection_checks = {}

    @app.middleware('http')
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.url.path.startswith(('/api/', '/sandbox/api/')):
            response.headers['Cache-Control'] = 'no-store'
        if request.url.path.startswith(('/news/', '/sandbox/linkedin/')):
            response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'product': 'Dispatch', 'ai_mode': settings.mode, 'model': settings.model,
                'workspace': 'demo' if settings.data_dir.name == 'demo-workspace' else 'standard',
                'publishing_mode': 'local_sandbox' if settings.website_provider == 'local' and settings.social_provider == 'sandbox' else 'configured'}

    @app.post('/api/auth/login')
    def login(body: Login, response: Response, request: Request):
        key = request.client.host if request.client else 'local'
        attempts = app.state.login_attempts.setdefault(key, [])
        attempts[:] = [at for at in attempts if time.time() - at < 60]
        if len(attempts) >= 10:
            raise HTTPException(429, 'Too many sign-in attempts. Wait one minute.')
        attempts.append(time.time())
        if not (hmac.compare_digest(body.email.encode(), settings.email.encode())
                and hmac.compare_digest(body.password.encode(), settings.password.encode())):
            raise HTTPException(401, 'The email or password is incorrect.')
        attempts.clear()
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with database.connection() as db:
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)', (token_hash(token), csrf, time.time() + 28800))
        response.set_cookie('dispatch_session', token, httponly=True, samesite='strict', max_age=28800,
                            secure=request.url.scheme == 'https', path='/')
        return {'email': settings.email, 'name': settings.reviewer_name, 'csrf': csrf}

    @app.get('/api/auth/me')
    def me(request: Request, email=Depends(require_session)):
        with database.connection() as db:
            row = db.execute('SELECT csrf FROM sessions WHERE token_hash=?', (token_hash(request.cookies['dispatch_session']),)).fetchone()
        return {'email': email, 'name': settings.reviewer_name, 'csrf': row['csrf']}

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response, email=Depends(require_session)):
        with database.connection() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(request.cookies['dispatch_session']),))
        response.delete_cookie('dispatch_session', path='/')
        return {'ok': True}

    @app.get('/api/config')
    def config(email=Depends(require_session)):
        with database.connection() as db:
            projects = [dict(row) for row in db.execute('SELECT * FROM projects')]
            failures = {row['key']: row['value'] for row in db.execute('SELECT * FROM sandbox_settings')}
        return {'projects': projects, 'ai_mode': settings.mode, 'model': settings.model,
                'publishing_mode': 'local_sandbox' if settings.website_provider == 'local' and settings.social_provider == 'sandbox' else 'configured', 'sample': SAMPLE,
                'connections': connection_report(settings, app.state.connection_checks),
                'ai_connection': ai_connection(settings, app.state.connection_checks.get('ai')),
                'fail_next': {channel: failures.get('fail_' + channel) == '1' for channel in CHANNELS}}

    @app.get('/api/connections')
    def connections(email=Depends(require_session)):
        return {'ai': ai_connection(settings, app.state.connection_checks.get('ai')),
                'publishing': connection_report(settings, app.state.connection_checks)}

    @app.post('/api/connections/check')
    def check_connections(email=Depends(require_session)):
        app.state.connection_checks['ai'] = check_ai(settings)
        for channel in CHANNELS:
            error = configuration_error(settings, channel)
            spec = destination(settings, channel)
            check = {'status': 'needs_setup', 'detail': error} if error else {
                'status': 'local' if spec['provider'] in ('local', 'sandbox') else 'unverified',
                'detail': 'Built-in destination is available.' if spec['provider'] in ('local', 'sandbox') else
                          'Token and author are configured. LinkedIn write permission is verified only by an approved publication.'}
            if not error and spec['provider'] == 'wordpress':
                try:
                    check = check_wordpress(settings)
                except Exception:
                    check = {'status': 'failed', 'detail': 'WordPress could not be reached or returned an invalid response.'}
            app.state.connection_checks[channel] = check | {'checked_at': now()}
        return connections(email)

    @app.get('/api/items')
    def items(email=Depends(require_session)):
        with database.connection() as db:
            return [read_item(db, row['id']) for row in db.execute('SELECT id FROM items ORDER BY updated_at DESC').fetchall()]

    @app.get('/api/items/{item_id}')
    def item(item_id: str, email=Depends(require_session)):
        with database.connection() as db:
            return read_item(db, item_id)

    @app.post('/api/items', status_code=202)
    def create(body: NewItem, email=Depends(require_session)):
        if not body.title.strip() or len(body.source.strip()) < 30:
            raise HTTPException(422, 'Add a title and at least 30 characters of source material.')
        item_id, stamp = uid(), now()
        with database.connection() as db:
            if not db.execute('SELECT id FROM projects WHERE id=?', (body.project_id,)).fetchone():
                raise HTTPException(404, 'Project not found.')
            db.execute('''INSERT INTO items (id,project_id,title,source,update_type,audience,cta,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                       (item_id, body.project_id, body.title.strip(), body.source.strip(), body.update_type,
                        body.audience.strip(), body.cta.strip(), 'queued_generation', stamp, stamp))
            event(db, item_id, 'source_added', 'Source saved; three-channel generation queued.')
        return {'id': item_id, 'status': 'queued_generation'}

    @app.post('/api/items/{item_id}/retry-generation')
    def retry_generation(item_id: str, email=Depends(require_session)):
        with database.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            item = read_item(db, item_id)
            if item['status'] != 'generation_failed':
                raise HTTPException(409, 'Only failed generation can be retried.')
            db.execute("UPDATE items SET status='queued_generation',error=NULL,updated_at=? WHERE id=?", (now(), item_id))
        return {'status': 'queued_generation'}

    @app.put('/api/items/{item_id}')
    def edit(item_id: str, body: Edit, email=Depends(require_session)):
        content = body.content.model_dump()
        channels = sorted(set(body.channels))
        if any(not d['title'].strip() or not d['body'].strip() for d in content.values()):
            raise HTTPException(422, 'Every channel needs a title and body before saving.')
        if any(len(d['body']) > 30000 or len(d['title']) > 300 for d in content.values()):
            raise HTTPException(422, 'Keep titles under 300 characters and channel drafts under 30,000 characters.')
        with database.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            item = read_item(db, item_id)
            check_revision(item, body.revision)
            check_not_publishing(db, item_id)
            if not item['content']:
                raise HTTPException(409, 'Wait for generation to finish.')
            if content == item['content'] and channels == sorted(item['channels']) and item['status'] != 'rejected':
                return item
            revoke(db, item_id)
            revision = item['revision'] + 1
            db.execute('INSERT INTO revisions VALUES (?,?,?,?,?)', (item_id, revision, json.dumps(content), json.dumps(channels), now()))
            db.execute("UPDATE items SET revision=?,status='draft',updated_at=? WHERE id=?", (revision, now(), item_id))
            event(db, item_id, 'draft_saved', f'{email} saved revision {revision}. Any previous approval was revoked.')
            return read_item(db, item_id)

    @app.post('/api/items/{item_id}/ready')
    def ready(item_id: str, body: Ready, email=Depends(require_session)):
        with database.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            item = read_item(db, item_id)
            check_revision(item, body.revision)
            if item['status'] not in ('draft', 'ready'):
                raise HTTPException(409, 'Only a saved draft can be marked ready for review.')
            db.execute("UPDATE items SET status='ready',updated_at=? WHERE id=?", (now(), item_id))
            event(db, item_id, 'review_requested', f'Revision {body.revision} is ready for human review.')
        return {'status': 'ready'}

    @app.post('/api/items/{item_id}/approve', status_code=202)
    def approve(item_id: str, body: Approval, email=Depends(require_session)):
        channels = sorted(set(body.channels))
        with database.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            item = read_item(db, item_id)
            check_revision(item, body.revision)
            if not item['content']:
                raise HTTPException(409, 'Generate and review the content first.')
            if channels != sorted(item['channels']):
                raise HTTPException(409, 'Save the selected destinations before approving.')
            existing = db.execute('SELECT * FROM approvals WHERE item_id=? AND revision=?', (item_id, body.revision)).fetchone()
            if existing:
                if existing['status'] != 'active':
                    raise HTTPException(409, 'This approval was revoked. Save a new draft revision and review again.')
                return {'approval_id': existing['id'], 'item': item, 'already_approved': True}
            if item['status'] not in ('draft', 'ready'):
                raise HTTPException(409, 'Edit and save a new draft before approving this item.')
            for channel in channels:
                error = configuration_error(settings, channel)
                if error:
                    raise HTTPException(422, error)
                if body.destinations is not None and body.destinations.get(channel) != destination(settings, channel):
                    raise HTTPException(409, 'The destination changed. Refresh and review the connection before approving.')
                draft = item['content'][channel]
                if not draft['title'].strip() or not draft['body'].strip():
                    raise HTTPException(422, 'Selected destinations need nonempty approved content.')
            approval_id, stamp = uid(), now()
            db.execute('INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?)',
                       (approval_id, item_id, body.revision, fingerprint(item['content'], channels),
                        json.dumps(channels), email, 'active', stamp))
            for channel in channels:
                db.execute('''INSERT INTO jobs (id,approval_id,item_id,revision,channel,status,created_at,updated_at,destination)
                    VALUES (?,?,?,?,?,'queued',?,?,?)''', (uid(), approval_id, item_id, body.revision, channel, stamp, stamp,
                                                        destination_json(settings, channel)))
            db.execute("UPDATE items SET status='publishing',updated_at=? WHERE id=?", (stamp, item_id))
            event(db, item_id, 'approved', f'{email} approved revision {body.revision} for {", ".join(channels)}.')
            return {'approval_id': approval_id, 'item': read_item(db, item_id), 'already_approved': False}

    @app.post('/api/items/{item_id}/reject')
    def reject(item_id: str, body: Rejection, email=Depends(require_session)):
        if len(body.reason.strip()) < 3:
            raise HTTPException(422, 'Add a short rejection reason.')
        with database.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            item = read_item(db, item_id)
            check_revision(item, body.revision)
            check_not_publishing(db, item_id)
            if not item['content']:
                raise HTTPException(409, 'Wait for generation before reviewing.')
            revoke(db, item_id)
            # A rejection starts a new unpublished revision; old published snapshots remain immutable.
            revision = item['revision'] + 1
            db.execute('INSERT INTO revisions VALUES (?,?,?,?,?)', (item_id, revision, json.dumps(item['content']), json.dumps(item['channels']), now()))
            db.execute("UPDATE items SET revision=?,status='rejected',updated_at=? WHERE id=?", (revision, now(), item_id))
            event(db, item_id, 'rejected', f'{email}: {body.reason.strip()}')
        return {'status': 'rejected'}

    @app.post('/api/jobs/{job_id}/retry', status_code=202)
    def retry_job(job_id: str, email=Depends(require_session)):
        with database.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not job:
                raise HTTPException(404, 'Publication job not found.')
            approval = db.execute('SELECT * FROM approvals WHERE id=?', (job['approval_id'],)).fetchone()
            item = read_item(db, job['item_id'])
            if approval['status'] != 'active' or item['revision'] != job['revision']:
                raise HTTPException(409, 'Approval is no longer current. Review and approve the latest revision.')
            if job['status'] not in ('failed', 'uncertain'):
                raise HTTPException(409, 'Only failed or uncertain destinations can be retried.')
            state = 'reconciling' if job['status'] == 'uncertain' else 'queued'
            db.execute('UPDATE jobs SET status=?,error=NULL,updated_at=? WHERE id=?', (state, now(), job_id))
            db.execute("UPDATE items SET status='publishing',updated_at=? WHERE id=?", (now(), job['item_id']))
            event(db, job['item_id'], 'retry_requested', f"{email} requested {'outcome reconciliation' if state == 'reconciling' else 'retry'} for {job['channel']}.")
        return {'status': state}

    @app.get('/api/items/{item_id}/history')
    def history(item_id: str, email=Depends(require_session)):
        with database.connection() as db:
            read_item(db, item_id)
            return [dict(row) | {'content': json.loads(row['content']), 'channels': json.loads(row['channels'])}
                    for row in db.execute('SELECT * FROM revisions WHERE item_id=? ORDER BY revision DESC', (item_id,))]

    @app.get('/api/activity')
    def activity(email=Depends(require_session)):
        with database.connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM activity ORDER BY created_at DESC LIMIT 200')]

    @app.get('/api/publications')
    def publications(email=Depends(require_session)):
        with database.connection() as db:
            return [dict(row) for row in db.execute('''SELECT j.*,i.title,p.name AS project_name,a.reviewer,
                a.created_at AS approved_at FROM jobs j JOIN items i ON i.id=j.item_id JOIN projects p ON p.id=i.project_id
                JOIN approvals a ON a.id=j.approval_id ORDER BY j.updated_at DESC''')]

    @app.get('/api/export/publications')
    def export_publications(email=Depends(require_session)):
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['Title', 'Revision', 'Channel', 'Status', 'Approved by', 'Approved at (UTC)', 'Updated at (UTC)', 'URL', 'Attempts', 'Error'])
        for row in publications(email):
            values = [row['title'], row['revision'], row['channel'], row['status'], row['reviewer'],
                      row['approved_at'], row['updated_at'], row['url'], row['attempts'], row['error']]
            writer.writerow([("'" + str(v)) if str(v or '').startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in values])
        return Response('\ufeff' + output.getvalue(), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="dispatch-publication-log.csv"'})

    @app.get('/api/items/{item_id}/export')
    def export_content(item_id: str, email=Depends(require_session)):
        with database.connection() as db:
            item = read_item(db, item_id)
        if not item['content']:
            raise HTTPException(409, 'Draft generation has not completed.')
        text = f"{item['title']}\nRevision {item['revision']} · {item['provider']}\n\n"
        text += '\n\n'.join(f"{channel.upper()}\n{draft['title']}\n\n{draft['body']}" for channel, draft in item['content'].items())
        return Response(text, media_type='text/plain', headers={'Content-Disposition': 'attachment; filename="dispatch-channel-drafts.txt"'})

    @app.post('/api/sandbox/fail-next')
    def fail_next(body: SandboxFailure, email=Depends(require_session)):
        with database.connection() as db:
            db.execute('INSERT OR REPLACE INTO sandbox_settings VALUES (?,?)', ('fail_' + body.channel, '1'))
            event(db, None, 'sandbox_failure_armed', f'Next {body.channel} sandbox request will fail once, before a post is created.')
        return {'channel': body.channel, 'fail_next': True}

    def internal(request):
        if not hmac.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + app.state.sandbox_token):
            raise HTTPException(401, 'Publishing API authorization required.')

    @app.get('/sandbox/api/posts/by-job/{job_id}')
    def by_job(job_id: str, request: Request):
        internal(request)
        with database.connection() as db:
            post = db.execute('SELECT id,url FROM posts WHERE job_id=?', (job_id,)).fetchone()
        if not post:
            raise HTTPException(404, 'No publication exists for this job.')
        return dict(post)

    @app.post('/sandbox/api/{channel}/posts', status_code=201)
    def receive(channel: str, body: PublishRequest, request: Request):
        internal(request)
        if channel not in CHANNELS:
            raise HTTPException(404, 'Destination not found.')
        if request.headers.get('Idempotency-Key') != body.job_id:
            raise HTTPException(422, 'A matching idempotency key is required.')
        fail = False
        with database.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            post = db.execute('SELECT id,url,channel FROM posts WHERE job_id=?', (body.job_id,)).fetchone()
            if post:
                if post['channel'] != channel:
                    raise HTTPException(409, 'Job destination does not match.')
                return {'id': post['id'], 'url': post['url'], 'replayed': True}
            job = db.execute('SELECT * FROM jobs WHERE id=?', (body.job_id,)).fetchone()
            if not job or job['status'] != 'publishing' or job['channel'] != channel:
                raise HTTPException(403, 'A currently approved publishing job is required.')
            approval = db.execute('SELECT * FROM approvals WHERE id=?', (job['approval_id'],)).fetchone()
            item = read_item(db, job['item_id'])
            channels = json.loads(approval['channels'])
            if approval['status'] != 'active' or item['revision'] != job['revision'] or channel not in channels or fingerprint(item['content'], channels) != approval['fingerprint']:
                raise HTTPException(403, 'The approval is not valid for this exact content snapshot.')
            failure = db.execute('SELECT value FROM sandbox_settings WHERE key=?', ('fail_' + channel,)).fetchone()
            if failure and failure['value'] == '1':
                db.execute('UPDATE sandbox_settings SET value=? WHERE key=?', ('0', 'fail_' + channel))
                fail = True
            else:
                post_id = uid()
                draft = item['content'][channel]
                slug = re.sub(r'[^a-z0-9]+', '-', draft['title'].lower()).strip('-')[:80] + '-' + post_id[:6]
                path = '/news/' + slug if channel == 'website' else '/sandbox/linkedin/' + post_id
                url = settings.base_url + path
                db.execute('INSERT INTO posts VALUES (?,?,?,?,?,?,?,?)',
                           (post_id, body.job_id, channel, draft['title'], draft['body'], slug, url, now()))
        if fail:
            raise HTTPException(503, 'Deliberate one-time sandbox failure. No post was created.')
        return {'id': post_id, 'url': url, 'replayed': False}

    @app.get('/news/{slug}', response_class=HTMLResponse)
    def article(slug: str):
        with database.connection() as db:
            post = db.execute("SELECT * FROM posts WHERE slug=? AND channel='website'", (slug,)).fetchone()
        if not post:
            raise HTTPException(404, 'Published article not found.')
        return published_page(post['title'], post['body'], post['created_at'])

    @app.get('/sandbox/linkedin/{post_id}', response_class=HTMLResponse)
    def social_post(post_id: str):
        with database.connection() as db:
            post = db.execute("SELECT * FROM posts WHERE id=? AND channel='linkedin'", (post_id,)).fetchone()
        if not post:
            raise HTTPException(404, 'Sandbox post not found.')
        return published_page(post['title'], post['body'], post['created_at'], social=True)

    dist = ROOT / 'frontend' / 'dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    return app


app = create_app()
