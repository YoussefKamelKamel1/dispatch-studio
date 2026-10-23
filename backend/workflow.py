from __future__ import annotations

import json

import httpx

from .ai import Drafts, demo_generate, live_generate
from .core import fingerprint, now, uid
from .connectors import PublicationUncertain, destination, publish_external

CHANNELS = ('website', 'linkedin')


def event(db, item_id, action, detail):
    db.execute('INSERT INTO activity VALUES (?,?,?,?,?)', (uid(), item_id, action, detail, now()))


def item_status(db, item_id):
    item = db.execute('SELECT revision FROM items WHERE id=?', (item_id,)).fetchone()
    jobs = db.execute('SELECT status FROM jobs WHERE item_id=? AND revision=?', (item_id, item['revision'])).fetchall()
    states = [job['status'] for job in jobs if job['status'] != 'cancelled']
    if not states:
        return
    if any(s in ('queued', 'publishing', 'reconciling') for s in states):
        status = 'publishing'
    elif all(s == 'succeeded' for s in states):
        status = 'published'
    elif any(s == 'succeeded' for s in states):
        status = 'partial'
    else:
        status = 'failed'
    db.execute('UPDATE items SET status=?,updated_at=? WHERE id=?', (status, now(), item_id))


def generate_one(app):
    database, settings = app.state.db, app.state.settings
    with database.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT * FROM items WHERE status='queued_generation' ORDER BY created_at LIMIT 1").fetchone()
        if not row:
            return False
        item = dict(row)
        db.execute("UPDATE items SET status='generating',error=NULL WHERE id=?", (item['id'],))
    try:
        if app.state.generator:
            content, provider = app.state.generator(item)
        elif settings.mode == 'live':
            content, provider = live_generate(item, settings)
        else:
            content, provider = demo_generate(item)
        content = Drafts.model_validate(content).model_dump()
        checks = content.pop('checks')
        if any(not draft['title'].strip() or not draft['body'].strip() for draft in content.values()):
            raise ValueError('A generated draft was empty. Retry generation before reviewing.')
        with database.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            revision = item['revision'] + 1
            db.execute('INSERT INTO revisions VALUES (?,?,?,?,?)', (item['id'], revision, json.dumps(content), '[]', now()))
            db.execute("UPDATE items SET status='draft',revision=?,provider=?,warnings=?,error=NULL,updated_at=? WHERE id=?",
                       (revision, provider, json.dumps(checks), now(), item['id']))
            event(db, item['id'], 'drafts_generated', f'Three channel drafts created with {provider}. Human approval is required.')
    except Exception as exc:
        detail = str(exc)[:600] if isinstance(exc, ValueError) else 'Generation failed. Check connectivity and configuration; then retry.'
        with database.connection() as db:
            db.execute("UPDATE items SET status='generation_failed',error=?,updated_at=? WHERE id=?", (detail, now(), item['id']))
            event(db, item['id'], 'generation_failed', detail)
    return True


def publish_one(app):
    database = app.state.db
    with database.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT * FROM jobs WHERE status IN ('queued','reconciling') ORDER BY created_at,channel DESC LIMIT 1").fetchone()
        if not row:
            return False
        job = dict(row)
        approval = db.execute('SELECT * FROM approvals WHERE id=?', (job['approval_id'],)).fetchone()
        item = db.execute('SELECT * FROM items WHERE id=?', (job['item_id'],)).fetchone()
        rev = db.execute('SELECT * FROM revisions WHERE item_id=? AND revision=?', (job['item_id'], job['revision'])).fetchone()
        if not approval or approval['status'] != 'active' or item['revision'] != job['revision'] or not rev:
            db.execute("UPDATE jobs SET status='cancelled',error='Approval is no longer valid.',updated_at=? WHERE id=?", (now(), job['id']))
            return True
        content = json.loads(rev['content'])
        channels = json.loads(approval['channels'])
        if fingerprint(content, channels) != approval['fingerprint'] or job['channel'] not in channels:
            db.execute("UPDATE jobs SET status='cancelled',error='Approved snapshot did not match.',updated_at=? WHERE id=?", (now(), job['id']))
            return True
        db.execute("UPDATE jobs SET status='publishing',attempts=attempts+1,updated_at=? WHERE id=?", (now(), job['id']))
        item_status(db, job['item_id'])
    try:
        payload = {'job_id': job['id']}
        if app.state.publisher:
            result = app.state.publisher(job, payload)
        elif job.get('destination') and json.loads(job['destination']) != destination(app.state.settings, job['channel']):
            raise ValueError('The publishing destination changed after approval. Restore that connection or save and approve a new revision.')
        elif (json.loads(job['destination']).get('provider') if job.get('destination') else 'local') in ('wordpress', 'linkedin'):
            result = publish_external(app.state.settings, job, content[job['channel']])
        else:
            headers = {'Authorization': 'Bearer ' + app.state.sandbox_token, 'Idempotency-Key': job['id']}
            with httpx.Client(timeout=20) as client:
                result = None
                if job['status'] == 'reconciling':
                    response = client.get(app.state.settings.base_url + '/sandbox/api/posts/by-job/' + job['id'], headers=headers)
                    if response.status_code == 200:
                        result = response.json()
                    elif response.status_code != 404:
                        raise httpx.ReadTimeout('Publication reconciliation was inconclusive.')
                if result is None:
                    response = client.post(app.state.settings.base_url + '/sandbox/api/' + job['channel'] + '/posts', json=payload, headers=headers)
                    if response.status_code >= 400:
                        raise ValueError(f"{job['channel'].title()} sandbox returned HTTP {response.status_code}. No successful result was confirmed; retry this destination.")
                    result = response.json()
        if not result.get('id') or not result.get('url'):
            raise httpx.ReadTimeout('The publisher response was incomplete; reconcile before retrying.')
        with database.connection() as db:
            db.execute("UPDATE jobs SET status='succeeded',external_id=?,url=?,error=NULL,updated_at=? WHERE id=?",
                       (result['id'], result['url'], now(), job['id']))
            db.execute('INSERT INTO attempts VALUES (?,?,?,?,?)', (uid(), job['id'], 'succeeded', 'Published result confirmed.', now()))
            event(db, job['item_id'], 'published', f"{job['channel'].title()} publication confirmed: {result['url']}")
            item_status(db, job['item_id'])
    except Exception as exc:
        uncertain = job['status'] == 'reconciling' or isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))
        status = 'uncertain' if uncertain else 'failed'
        detail = (str(exc) if isinstance(exc, PublicationUncertain) else
                  'The connection ended before publication could be confirmed. Check the outcome before retrying.' if uncertain
                  else str(exc)[:500] if isinstance(exc, ValueError) else 'Publishing failed. Review the connection and retry this destination.')
        with database.connection() as db:
            db.execute('UPDATE jobs SET status=?,error=?,updated_at=? WHERE id=?', (status, detail, now(), job['id']))
            db.execute('INSERT INTO attempts VALUES (?,?,?,?,?)', (uid(), job['id'], status, detail, now()))
            event(db, job['item_id'], 'publication_' + status, f"{job['channel'].title()}: {detail}")
            item_status(db, job['item_id'])
    return True
