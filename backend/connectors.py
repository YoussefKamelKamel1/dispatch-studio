"""Publishing adapters. No external write occurs until a saved revision is approved."""
from __future__ import annotations

import html
import json
import re
from urllib.parse import quote, unquote, urlsplit

import httpx


class PublicationUncertain(httpx.ReadTimeout):
    """An intentionally safe, user-readable explanation with no credentials."""


def https_url(value):
    parsed = urlsplit(value)
    return bool(parsed.scheme == 'https' and parsed.hostname and not parsed.username
                and not parsed.password and not parsed.query and not parsed.fragment)


def public_result_url(value):
    parsed = urlsplit(value)
    return bool(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password)


def destination(settings, channel):
    if channel == 'website':
        provider = settings.website_provider
        target = settings.wordpress_url if provider == 'wordpress' else settings.base_url
        return {'provider': provider, 'target': target,
                'account': settings.wordpress_user if provider == 'wordpress' else ''}
    provider = settings.social_provider
    return {'provider': provider,
            'target': settings.linkedin_author if provider == 'linkedin' else settings.base_url,
            'version': settings.linkedin_version if provider == 'linkedin' else ''}


def destination_json(settings, channel):
    return json.dumps(destination(settings, channel), sort_keys=True)


def configuration_error(settings, channel):
    provider = destination(settings, channel)['provider']
    if channel == 'website':
        if provider == 'local':
            return None
        if provider != 'wordpress':
            return 'WEBSITE_PROVIDER must be local or wordpress.'
        if not https_url(settings.wordpress_url):
            return 'Set WORDPRESS_URL to the HTTPS site address, without /wp-json, a query, or embedded credentials.'
        if not settings.wordpress_user or not settings.wordpress_password.strip():
            return 'Add WORDPRESS_USERNAME and WORDPRESS_APPLICATION_PASSWORD to the server .env file.'
    else:
        if provider == 'sandbox':
            return None
        if provider != 'linkedin':
            return 'SOCIAL_PROVIDER must be sandbox or linkedin.'
        if not settings.linkedin_token:
            return 'Add LINKEDIN_ACCESS_TOKEN with permission to publish for the selected account.'
        if not re.fullmatch(r'urn:li:(person|organization):[A-Za-z0-9_-]+', settings.linkedin_author):
            return 'Set LINKEDIN_AUTHOR_URN to the authorized person or organization URN.'
        if not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])', settings.linkedin_version):
            return 'LINKEDIN_API_VERSION must use YYYYMM.'
    return None


def connection_report(settings, checks=None):
    checks = checks or {}
    result = []
    for channel in ('website', 'linkedin'):
        spec = destination(settings, channel)
        error = configuration_error(settings, channel)
        local = spec['provider'] in ('local', 'sandbox')
        result.append({'id': channel, **spec, 'configured': not error,
                       'status': 'needs_setup' if error else 'local' if local else 'configured',
                       'detail': error or ('Built-in destination. No external credentials required.' if local else
                                          'Credentials supplied. An approved publication is required to verify write access.'),
                       'check': checks.get(channel)})
    return result


def text_html(body):
    return '\n'.join('<p>' + html.escape(p).replace('\n', '<br>') + '</p>'
                     for p in re.split(r'\n\s*\n', body) if p.strip())


def response_ok(response, label):
    if response.status_code >= 500:
        raise PublicationUncertain(f'{label} returned a server error. Check the outcome before retrying.')
    if response.status_code >= 400:
        raise ValueError(f'{label} returned HTTP {response.status_code}. Check credentials, publishing permissions, and provider limits.')


def wordpress_publish(settings, job, draft, client):
    endpoint = settings.wordpress_url + '/wp-json/wp/v2/posts'
    auth = (settings.wordpress_user, settings.wordpress_password)
    slug = 'dispatch-' + job['id']
    if job['status'] == 'reconciling':
        response = client.get(endpoint, params={'slug': slug, 'context': 'edit', 'status': 'publish'}, auth=auth)
        response_ok(response, 'WordPress')
        matches = response.json()
        expected = text_html(draft['body'])
        for post in matches:
            if (post.get('slug') == slug and post.get('status') == 'publish'
                    and post.get('title', {}).get('raw') == draft['title']
                    and post.get('content', {}).get('raw', '').strip() == expected.strip()
                    and post.get('id') and public_result_url(post.get('link', ''))):
                return {'id': str(post['id']), 'url': post['link']}
        raise PublicationUncertain('WordPress could not confirm the earlier request. No second post was sent. Check the site manually.')
    response = client.post(endpoint, auth=auth, json={'title': draft['title'], 'content': text_html(draft['body']),
                                                   'status': 'publish', 'slug': slug})
    response_ok(response, 'WordPress')
    try:
        post = response.json()
        if post.get('status') != 'publish' or not post.get('id') or not public_result_url(post.get('link', '')):
            raise ValueError()
        return {'id': str(post['id']), 'url': post['link']}
    except (ValueError, KeyError, TypeError):
        raise PublicationUncertain('WordPress did not confirm a published post with a URL. Check the site before retrying.') from None


def linkedin_publish(settings, job, draft, client):
    # LinkedIn does not document an idempotent create endpoint. Never resend an ambiguous write.
    if job['status'] == 'reconciling':
        raise PublicationUncertain('LinkedIn outcome requires manual verification. No second post was sent; check the account feed.')
    commentary = draft['title'].strip() + '\n\n' + draft['body'].strip()
    if len(commentary) > 3000:
        raise ValueError('The LinkedIn title and body exceed 3,000 characters. Shorten the draft and approve a new revision.')
    headers = {'Authorization': 'Bearer ' + settings.linkedin_token,
               'LinkedIn-Version': settings.linkedin_version, 'X-Restli-Protocol-Version': '2.0.0'}
    response = client.post('https://api.linkedin.com/rest/posts', headers=headers,
        json={'author': settings.linkedin_author, 'commentary': commentary, 'visibility': 'PUBLIC',
              'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
              'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False})
    response_ok(response, 'LinkedIn')
    post_id = unquote(response.headers.get('x-restli-id', ''))
    if response.status_code != 201 or not re.fullmatch(r'urn:li:(share|ugcPost):\d+', post_id):
        raise PublicationUncertain('LinkedIn did not return a confirmed post ID. Check the account feed before any further action.')
    return {'id': post_id, 'url': 'https://www.linkedin.com/feed/update/' + quote(post_id, safe=':') + '/'}


def publish_external(settings, job, draft, client=None):
    error = configuration_error(settings, job['channel'])
    if error:
        raise ValueError(error)
    if client is None:
        with httpx.Client(timeout=30, follow_redirects=False) as owned:
            return publish_external(settings, job, draft, owned)
    if job['channel'] == 'website' and settings.website_provider == 'wordpress':
        return wordpress_publish(settings, job, draft, client)
    if job['channel'] == 'linkedin' and settings.social_provider == 'linkedin':
        return linkedin_publish(settings, job, draft, client)
    raise ValueError('No external adapter is configured for this destination.')


def check_wordpress(settings, client=None):
    if client is None:
        with httpx.Client(timeout=15, follow_redirects=False) as owned:
            return check_wordpress(settings, owned)
    response = client.get(settings.wordpress_url + '/wp-json/wp/v2/users/me', params={'context': 'edit'},
                          auth=(settings.wordpress_user, settings.wordpress_password))
    if response.status_code != 200:
        return {'status': 'failed', 'detail': f'WordPress authentication check returned HTTP {response.status_code}.'}
    user = response.json()
    if not user.get('capabilities', {}).get('publish_posts'):
        return {'status': 'failed', 'detail': 'This WordPress account does not report permission to publish posts.'}
    return {'status': 'verified', 'detail': 'Authenticated account has publish_posts permission. No post was created.'}
