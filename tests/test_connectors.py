import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.connections import check_ai
from backend.connectors import (PublicationUncertain, check_wordpress, configuration_error,
                                connection_report, destination, publish_external, text_html)
from backend.core import Settings
from backend.fixtures import SAMPLE
from backend.workflow import generate_one, publish_one


def wordpress_settings():
    return Settings(website_provider='wordpress', wordpress_url='https://example.org',
                    wordpress_user='editor', wordpress_password='private-password')


def linkedin_settings():
    return Settings(social_provider='linkedin', linkedin_token='private-token', linkedin_author='urn:li:organization:123')


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_wordpress_payload_is_escaped_and_success_is_recorded():
    def handler(request):
        assert request.url == 'https://example.org/wp-json/wp/v2/posts'
        assert request.headers['Authorization'].startswith('Basic ')
        payload = json.loads(request.content)
        assert payload == {'title': 'Workshop report', 'content': '<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>\n<p>48 participants.</p>',
                           'status': 'publish', 'slug': 'dispatch-job123'}
        return httpx.Response(201, json={'id': 42, 'status': 'publish', 'link': 'https://example.org/?p=42'})
    with mock_client(handler) as client:
        result = publish_external(wordpress_settings(), {'id': 'job123', 'channel': 'website', 'status': 'queued'},
                                  {'title': 'Workshop report', 'body': '<script>alert(1)</script>\n\n48 participants.'}, client)
    assert result == {'id': '42', 'url': 'https://example.org/?p=42'}


def test_wordpress_uncertain_request_reconciles_by_exact_slug_and_content():
    calls = []
    draft = {'title': 'Workshop report', 'body': '48 participants.'}
    def handler(request):
        calls.append(request.method)
        assert request.url.params['slug'] == 'dispatch-job123'
        return httpx.Response(200, json=[{'id': 42, 'slug': 'dispatch-job123', 'status': 'publish',
            'title': {'raw': draft['title']}, 'content': {'raw': text_html(draft['body'])}, 'link': 'https://example.org/report/'}])
    with mock_client(handler) as client:
        result = publish_external(wordpress_settings(), {'id': 'job123', 'channel': 'website', 'status': 'reconciling'}, draft, client)
    assert result['id'] == '42'
    assert calls == ['GET']


def test_wordpress_unconfirmed_outcome_never_creates_a_second_post():
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json=[])
    with mock_client(handler) as client, pytest.raises(PublicationUncertain, match='No second post'):
        publish_external(wordpress_settings(), {'id': 'job123', 'channel': 'website', 'status': 'reconciling'},
                         {'title': 'Report', 'body': 'Text'}, client)
    assert calls == ['GET']


def test_linkedin_posts_only_the_approved_text_and_returns_id():
    def handler(request):
        assert str(request.url) == 'https://api.linkedin.com/rest/posts'
        assert request.headers['LinkedIn-Version'] == '202610'
        assert request.headers['X-Restli-Protocol-Version'] == '2.0.0'
        payload = json.loads(request.content)
        assert payload['author'] == 'urn:li:organization:123'
        assert payload['commentary'] == 'Workshop report\n\n48 participants.'
        assert payload['lifecycleState'] == 'PUBLISHED'
        return httpx.Response(201, headers={'x-restli-id': 'urn:li:share:12345'})
    with mock_client(handler) as client:
        result = publish_external(linkedin_settings(), {'id': 'job123', 'channel': 'linkedin', 'status': 'queued'},
                                  {'title': 'Workshop report', 'body': '48 participants.'}, client)
    assert result['id'] == 'urn:li:share:12345'
    assert result['url'] == 'https://www.linkedin.com/feed/update/urn:li:share:12345/'


@pytest.mark.parametrize('status,headers,expected', [(401, {}, ValueError), (403, {}, ValueError),
    (429, {}, ValueError), (500, {}, PublicationUncertain), (201, {}, PublicationUncertain)])
def test_linkedin_errors_do_not_claim_success(status, headers, expected):
    with mock_client(lambda request: httpx.Response(status, headers=headers)) as client, pytest.raises(expected):
        publish_external(linkedin_settings(), {'id': 'job123', 'channel': 'linkedin', 'status': 'queued'},
                         {'title': 'Report', 'body': 'Text'}, client)


def test_linkedin_ambiguous_result_does_not_resend_or_contact_provider():
    def handler(request):
        pytest.fail('An uncertain LinkedIn write must never be repeated automatically')
    with mock_client(handler) as client, pytest.raises(PublicationUncertain, match='manual verification'):
        publish_external(linkedin_settings(), {'id': 'job123', 'channel': 'linkedin', 'status': 'reconciling'},
                         {'title': 'Report', 'body': 'Text'}, client)


def test_configuration_and_reports_never_expose_credentials():
    settings = wordpress_settings()
    settings.social_provider = 'linkedin'
    assert configuration_error(settings, 'linkedin')
    report = json.dumps(connection_report(settings))
    assert 'private-password' not in report
    assert 'needs_setup' in report
    settings.wordpress_url = 'http://example.org'
    assert 'HTTPS' in configuration_error(settings, 'website')


def test_read_only_checks_do_not_create_posts_or_return_provider_secrets():
    def handler(request):
        assert request.method == 'GET'
        if request.url.host == 'api.openai.com':
            return httpx.Response(200, json={'id': 'gpt-4.1-mini', 'secret': 'must-not-return'})
        return httpx.Response(200, json={'capabilities': {'publish_posts': True}, 'private': 'must-not-return'})
    with mock_client(handler) as client:
        ai = check_ai(Settings(api_key='private-api-key'), client)
        wp = check_wordpress(wordpress_settings(), client)
    assert ai['status'] == wp['status'] == 'verified'
    assert 'must-not-return' not in json.dumps([ai, wp])
    assert 'private-api-key' not in json.dumps(ai)


def test_unconfigured_external_destination_cannot_be_approved(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, worker=False, seed=False, social_provider='linkedin'))
    with TestClient(app) as client:
        auth = client.post('/api/auth/login', json={'email': 'demo@example.com', 'password': 'demo-password'}).json()
        client.headers['X-CSRF-Token'] = auth['csrf']
        item_id = client.post('/api/items', json=SAMPLE).json()['id']
        generate_one(app)
        item = client.get('/api/items/' + item_id).json()
        saved = client.put('/api/items/' + item_id, json={'revision': item['revision'], 'content': item['content'], 'channels': ['linkedin']}).json()
        response = client.post('/api/items/' + item_id + '/approve', json={'revision': saved['revision'], 'channels': ['linkedin']})
        assert response.status_code == 422
        assert client.get('/api/publications').json() == []


def test_destination_change_after_approval_cannot_redirect_job(tmp_path):
    settings = wordpress_settings()
    settings.data_dir, settings.worker, settings.seed = tmp_path, False, False
    app = create_app(settings)
    with TestClient(app) as client:
        auth = client.post('/api/auth/login', json={'email': settings.email, 'password': settings.password}).json()
        client.headers['X-CSRF-Token'] = auth['csrf']
        item_id = client.post('/api/items', json=SAMPLE).json()['id']
        generate_one(app)
        item = client.get('/api/items/' + item_id).json()
        saved = client.put('/api/items/' + item_id, json={'revision': item['revision'], 'content': item['content'], 'channels': ['website']}).json()
        stale = client.post('/api/items/' + item_id + '/approve', json={'revision': saved['revision'], 'channels': ['website'],
                            'destinations': {'website': {'provider': 'local'}}})
        assert stale.status_code == 409
        response = client.post('/api/items/' + item_id + '/approve', json={'revision': saved['revision'], 'channels': ['website'],
                               'destinations': {'website': destination(settings, 'website')}})
        assert response.status_code == 202
        settings.wordpress_url = 'https://different.example.org'
        publish_one(app)
        job = client.get('/api/publications').json()[0]
        assert job['status'] == 'failed'
        assert 'destination changed' in job['error']
        assert 'private-password' not in json.dumps(job)
