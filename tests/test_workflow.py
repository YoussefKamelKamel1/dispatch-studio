import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core import Settings
from backend.fixtures import SAMPLE
from backend.workflow import generate_one, publish_one


def connect_publisher(app, client):
    def publisher(job, payload):
        headers = {'Authorization': 'Bearer ' + app.state.sandbox_token, 'Idempotency-Key': job['id']}
        if job['status'] == 'reconciling':
            found = client.get('/sandbox/api/posts/by-job/' + job['id'], headers=headers)
            if found.status_code == 200:
                return found.json()
            if found.status_code != 404:
                raise httpx.ReadTimeout('Reconciliation failed')
        response = client.post('/sandbox/api/' + job['channel'] + '/posts', json=payload, headers=headers)
        if response.status_code >= 400:
            raise ValueError(f'Sandbox returned HTTP {response.status_code}. Retry this destination.')
        return response.json()
    app.state.publisher = publisher
    return publisher


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(data_dir=tmp_path, seed=False, worker=False, base_url='http://testserver')
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'email': settings.email, 'password': settings.password})
        assert login.status_code == 200
        client.headers['X-CSRF-Token'] = login.json()['csrf']
        connect_publisher(app, client)
        yield client, app


def new_draft(client, app):
    response = client.post('/api/items', json=SAMPLE)
    assert response.status_code == 202, response.text
    assert generate_one(app)
    return client.get('/api/items/' + response.json()['id']).json()


def save_channels(client, item, channels=('website', 'linkedin')):
    response = client.put('/api/items/' + item['id'], json={
        'revision': item['revision'], 'content': item['content'], 'channels': list(channels)})
    assert response.status_code == 200, response.text
    return response.json()


def approve(client, item):
    response = client.post('/api/items/' + item['id'] + '/approve', json={
        'revision': item['revision'], 'channels': item['channels']})
    assert response.status_code == 202, response.text
    return response.json()


def test_generation_saves_three_drafts_and_never_publishes(workspace):
    client, app = workspace
    item = new_draft(client, app)
    assert set(item['content']) == {'website', 'linkedin', 'newsletter'}
    assert item['revision'] == 1
    assert item['channels'] == []
    assert item['status'] == 'draft'
    assert 'demo' in item['provider']
    assert item['jobs'] == []
    assert not publish_one(app)
    assert 'preliminary' in item['content']['website']['body']


def test_approval_requires_authorization_csrf_and_selected_saved_destinations(workspace):
    client, app = workspace
    item = new_draft(client, app)
    url = '/api/items/' + item['id'] + '/approve'
    assert TestClient(app).post(url, json={'revision': 1, 'channels': ['website']}).status_code == 401
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post(url, json={'revision': 1, 'channels': ['website']}).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    assert client.post(url, json={'revision': 1, 'channels': []}).status_code == 422
    assert client.post(url, json={'revision': 1, 'channels': ['website']}).status_code == 409
    assert client.post('/sandbox/api/website/posts', json={'job_id': 'forged'}).status_code == 401
    headers = {'Authorization': 'Bearer ' + app.state.sandbox_token, 'Idempotency-Key': 'forged'}
    assert client.post('/sandbox/api/website/posts', json={'job_id': 'forged'}, headers=headers).status_code == 403


def test_approval_triggers_real_http_receivers_and_readable_publications(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app))
    result = approve(client, item)
    assert result['item']['status'] == 'publishing'
    assert publish_one(app)
    assert publish_one(app)
    current = client.get('/api/items/' + item['id']).json()
    assert current['status'] == 'published'
    assert len(current['jobs']) == 2
    assert all(job['status'] == 'succeeded' and job['url'] for job in current['jobs'])
    for job in current['jobs']:
        page = client.get(job['url'])
        assert page.status_code == 200
        assert item['title'] in page.text
        assert 'Demonstration publication' in page.text
    log = client.get('/api/export/publications')
    assert log.status_code == 200
    assert 'succeeded' in log.text and 'Revision' in log.text


def test_repeat_approval_and_receiver_replays_do_not_duplicate(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app))
    first, second = approve(client, item), approve(client, item)
    assert first['approval_id'] == second['approval_id']
    assert second['already_approved'] is True
    publish_one(app)
    publish_one(app)
    jobs = client.get('/api/items/' + item['id']).json()['jobs']
    headers = {'Authorization': 'Bearer ' + app.state.sandbox_token, 'Idempotency-Key': jobs[0]['id']}
    replay = client.post('/sandbox/api/' + jobs[0]['channel'] + '/posts', json={'job_id': jobs[0]['id']}, headers=headers)
    assert replay.status_code == 201
    assert replay.json()['replayed'] is True
    with app.state.db.connection() as db:
        assert db.execute('SELECT count(*) FROM posts').fetchone()[0] == 2


def test_selected_destinations_only(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app), ['website'])
    approve(client, item)
    publish_one(app)
    assert not publish_one(app)
    current = client.get('/api/items/' + item['id']).json()
    assert [j['channel'] for j in current['jobs']] == ['website']


def test_edits_revoke_approval_cancel_unsent_jobs_and_block_stale_approval(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app))
    approve(client, item)
    edited = copy.deepcopy(item['content'])
    edited['website']['body'] += '\n\nA reviewer clarified the source.'
    saved = client.put('/api/items/' + item['id'], json={'revision': item['revision'], 'content': edited, 'channels': item['channels']})
    assert saved.status_code == 200
    assert saved.json()['revision'] == item['revision'] + 1
    assert all(job['status'] == 'cancelled' for job in saved.json()['jobs'])
    assert not publish_one(app)
    stale = client.post('/api/items/' + item['id'] + '/approve', json={'revision': item['revision'], 'channels': item['channels']})
    assert stale.status_code == 409
    approve(client, saved.json())
    publish_one(app)
    publish_one(app)
    with app.state.db.connection() as db:
        assert db.execute('SELECT body FROM posts WHERE channel=?', ('website',)).fetchone()[0] == edited['website']['body']


def test_channel_change_also_requires_new_approval(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app), ['website'])
    approve(client, item)
    changed = save_channels(client, item, ['linkedin'])
    assert changed['revision'] > item['revision']
    assert all(job['status'] == 'cancelled' for job in changed['jobs'])
    assert not publish_one(app)
    approve(client, changed)
    publish_one(app)
    with app.state.db.connection() as db:
        assert [r[0] for r in db.execute('SELECT channel FROM posts')] == ['linkedin']


def test_editing_is_locked_while_a_request_is_in_flight(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app))
    approve(client, item)
    real = app.state.publisher
    def observe_lock(job, payload):
        content = copy.deepcopy(item['content'])
        content['website']['body'] += ' Attempted concurrent edit.'
        response = client.put('/api/items/' + item['id'], json={'revision': item['revision'], 'content': content, 'channels': item['channels']})
        assert response.status_code == 409
        rejected = client.post('/api/items/' + item['id'] + '/reject', json={'revision': item['revision'], 'reason': 'Concurrent rejection'})
        assert rejected.status_code == 409
        return real(job, payload)
    app.state.publisher = observe_lock
    publish_one(app)
    jobs = client.get('/api/items/' + item['id']).json()['jobs']
    assert sum(job['status'] == 'succeeded' for job in jobs) == 1


def test_rejection_cancels_jobs_and_records_reason(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app))
    approve(client, item)
    result = client.post('/api/items/' + item['id'] + '/reject', json={'revision': item['revision'], 'reason': 'Please clarify the preliminary finding.'})
    assert result.status_code == 200
    assert not publish_one(app)
    assert any('Please clarify' in a['detail'] for a in client.get('/api/activity').json())
    current = client.get('/api/items/' + item['id']).json()
    assert current['status'] == 'rejected'
    assert client.post('/api/items/' + item['id'] + '/approve', json={'revision': current['revision'], 'channels': current['channels']}).status_code == 409


def test_partial_failure_and_targeted_retry_preserve_success(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app))
    client.post('/api/sandbox/fail-next', json={'channel': 'linkedin'})
    approve(client, item)
    publish_one(app)
    publish_one(app)
    current = client.get('/api/items/' + item['id']).json()
    assert current['status'] == 'partial'
    success = next(j for j in current['jobs'] if j['channel'] == 'website')
    failed = next(j for j in current['jobs'] if j['channel'] == 'linkedin')
    assert success['status'] == 'succeeded' and failed['status'] == 'failed'
    assert client.post('/api/jobs/' + success['id'] + '/retry').status_code == 409
    assert client.post('/api/jobs/' + failed['id'] + '/retry').status_code == 202
    publish_one(app)
    current = client.get('/api/items/' + item['id']).json()
    assert current['status'] == 'published'
    assert next(j for j in current['jobs'] if j['channel'] == 'website')['attempts'] == 1
    assert next(j for j in current['jobs'] if j['channel'] == 'linkedin')['attempts'] == 2
    with app.state.db.connection() as db:
        assert db.execute('SELECT count(*) FROM posts').fetchone()[0] == 2


def test_lost_response_is_reconciled_without_reposting(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app), ['website'])
    approve(client, item)
    real = app.state.publisher
    def lose_response(job, payload):
        real(job, payload)
        raise httpx.ReadTimeout('Response lost after receiver persisted the post')
    app.state.publisher = lose_response
    publish_one(app)
    current = client.get('/api/items/' + item['id']).json()
    job = current['jobs'][0]
    assert job['status'] == 'uncertain'
    app.state.publisher = real
    assert client.post('/api/jobs/' + job['id'] + '/retry').json()['status'] == 'reconciling'
    publish_one(app)
    assert client.get('/api/items/' + item['id']).json()['status'] == 'published'
    with app.state.db.connection() as db:
        assert db.execute('SELECT count(*) FROM posts').fetchone()[0] == 1


def test_old_failed_job_cannot_retry_after_an_edit(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app), ['linkedin'])
    client.post('/api/sandbox/fail-next', json={'channel': 'linkedin'})
    approve(client, item)
    publish_one(app)
    current = client.get('/api/items/' + item['id']).json()
    edited = copy.deepcopy(current['content'])
    edited['linkedin']['body'] += ' Clarified.'
    client.put('/api/items/' + item['id'], json={'revision': current['revision'], 'content': edited, 'channels': current['channels']})
    assert client.post('/api/jobs/' + current['jobs'][0]['id'] + '/retry').status_code == 409


def test_published_html_escapes_untrusted_source(workspace):
    client, app = workspace
    item = save_channels(client, new_draft(client, app), ['website'])
    item['content']['website']['body'] += '\n\n<script>alert("test")</script>'
    response = client.put('/api/items/' + item['id'], json={'revision': item['revision'], 'content': item['content'], 'channels': item['channels']})
    approve(client, response.json())
    publish_one(app)
    current = client.get('/api/items/' + item['id']).json()
    page = client.get(current['jobs'][0]['url'])
    assert '<script>' not in page.text
    assert '&lt;script&gt;' in page.text
    assert "default-src 'none'" in page.headers['content-security-policy']


def test_generation_failure_can_retry_without_losing_source(workspace):
    client, app = workspace
    def fail(item):
        raise ValueError('Provider unavailable; retry later.')
    app.state.generator = fail
    created = client.post('/api/items', json=SAMPLE).json()
    generate_one(app)
    item = client.get('/api/items/' + created['id']).json()
    assert item['status'] == 'generation_failed'
    assert item['source'] == SAMPLE['source']
    app.state.generator = None
    assert client.post('/api/items/' + item['id'] + '/retry-generation').status_code == 200
    generate_one(app)
    assert client.get('/api/items/' + item['id']).json()['status'] == 'draft'


def test_history_and_exports_retain_previous_versions(workspace):
    client, app = workspace
    item = new_draft(client, app)
    save_channels(client, item)
    history = client.get('/api/items/' + item['id'] + '/history').json()
    assert [row['revision'] for row in history] == [2, 1]
    assert history[1]['channels'] == []
    export = client.get('/api/items/' + item['id'] + '/export')
    assert all(name in export.text for name in ('LINKEDIN', 'WEBSITE', 'NEWSLETTER'))


def test_interrupted_publication_survives_restart_as_uncertain(tmp_path):
    settings = Settings(data_dir=tmp_path, worker=False, seed=False)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post('/api/auth/login', json={'email': settings.email, 'password': settings.password})
        client.headers['X-CSRF-Token'] = response.json()['csrf']
        item = save_channels(client, new_draft(client, app), ['website'])
        approved = approve(client, item)
        job = approved['item']['jobs'][0]
        with app.state.db.connection() as db:
            db.execute("UPDATE jobs SET status='publishing' WHERE id=?", (job['id'],))
    recovered = create_app(settings)
    with TestClient(recovered):
        with recovered.state.db.connection() as db:
            assert db.execute('SELECT status FROM jobs WHERE id=?', (job['id'],)).fetchone()[0] == 'uncertain'
