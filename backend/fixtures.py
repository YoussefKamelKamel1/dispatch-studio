from __future__ import annotations

import json

from .ai import demo_generate
from .core import now, uid

PROJECTS = [('urban', 'Urban Futures', '#718474'), ('skills', 'Skills for Change', '#bd866c'),
            ('research', 'Open Research', '#8b88a4')]
SAMPLE = {
    'title': 'Urban Futures: October workshop findings',
    'project_id': 'urban', 'update_type': 'Research findings',
    'audience': 'Research partners, community organizations, and local policymakers',
    'cta': 'Review the draft findings at the November follow-up session.',
    'source': 'The fictional Urban Futures project completed its first round of community mapping workshops in October 2026. Across three workshops, 48 residents shared how they use public spaces and where they encounter barriers to access.\n\nParticipants identified a need for more shaded seating, accessible footpaths, and welcoming spaces for intergenerational activities. These are preliminary qualitative findings from the workshop participants, not a representative survey of the city.\n\nThe research team will now organize the anonymized workshop notes into themes and invite participants to review the draft findings. A follow-up session is planned for November 2026. No policy commitments or measured improvements have been established at this stage.'
}


def seed(database, settings):
    with database.connection() as db:
        for project in PROJECTS:
            db.execute('INSERT OR IGNORE INTO projects VALUES (?,?,?)', project)
        if db.execute('SELECT count(*) FROM items').fetchone()[0] or not settings.seed:
            return
        specs = [SAMPLE,
                 SAMPLE | {'title': 'Skills for Change: learning materials review', 'project_id': 'skills',
                           'update_type': 'Project update', 'cta': '',
                           'source': 'The fictional Skills for Change team has completed a co-design session with community facilitators. Participants reviewed a draft learning pathway focused on job-search confidence, interview preparation, and practical digital skills.\n\nThe next step is to revise the learning materials using the feedback. The pilot has not started, and no employment outcomes have been measured.'},
                 SAMPLE | {'title': 'Open Research: November methods exchange', 'project_id': 'research',
                           'update_type': 'Event announcement', 'cta': 'Contact the research team to express interest.',
                           'source': 'The fictional Open Research project is preparing an online methods exchange in November 2026. Researchers and community partners will discuss how to make qualitative research methods easier to understand and reuse.\n\nThe agenda is being developed. The final date, registration link, and speakers will be announced after confirmation.'}]
        for index, item in enumerate(specs):
            item_id, stamp = uid(), now()
            content, provider = demo_generate(item)
            checks = content.pop('checks')
            status = 'ready' if index == 0 else 'draft'
            db.execute('''INSERT INTO items (id,project_id,title,source,update_type,audience,cta,status,revision,provider,warnings,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (item_id, item['project_id'], item['title'], item['source'], item['update_type'], item['audience'],
                        item['cta'], status, 1, provider, json.dumps(checks), stamp, stamp))
            db.execute('INSERT INTO revisions VALUES (?,?,?,?,?)', (item_id, 1, json.dumps(content), '[]', stamp))
        db.execute('INSERT INTO activity VALUES (?,?,?,?,?)',
                   (uid(), None, 'workspace_created', 'Three fictional draft projects prepared. Nothing has been published.', now()))
