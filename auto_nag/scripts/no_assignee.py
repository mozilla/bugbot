# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import functools
from libmozdata import hgmozilla
from libmozdata.bugzilla import Bugzilla, BugzillaUser
from libmozdata.connection import Query
import re
from auto_nag.bzcleaner import BzCleaner


HG_MAIL = re.compile(r'^([^<]*)<([^>]+)>$')


class NoAssignee(BzCleaner):
    def __init__(self):
        super(NoAssignee, self).__init__()
        self.hgdata = {}

    def description(self):
        return 'Get bugs with no assignees and a patch which landed in m-c'

    def name(self):
        return 'no-assignee'

    def template(self):
        return 'no_assignee_email.html'

    def subject(self):
        return 'Bugs with no assignees'

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        reporters = self.get_config('reporter_exception', default=[])
        reporters = ','.join(reporters)
        regexp = r'http[s]?://hg\.mozilla\.org/(releases/)?mozilla-[^/]+/rev/[0-9a-f]+'
        params = {
            'resolution': 'FIXED',
            'bug_status': ['RESOLVED', 'VERIFIED'],
            'keywords': 'meta',
            'keywords_type': 'nowords',
            'f1': 'assigned_to',
            'o1': 'equals',
            'v1': 'nobody@mozilla.org',
            'f2': 'longdesc',
            'o2': 'regexp',
            'v2': regexp,
            'f3': 'resolution',
            'o3': 'changedafter',
            'v3': start_date,
            'f4': 'resolution',
            'o4': 'changedbefore',
            'v4': end_date,
        }
        if reporters:
            params.update({'f5': 'reporter', 'o5': 'nowordssubstr', 'v5': reporters})

        return params

    def is_patch(self, attachment):
        """Check if the attachment is a patch or not.
        """
        if attachment['is_obsolete'] == 1:
            return False
        if attachment['is_patch'] == 1:
            return True
        if attachment['content_type'] in [
            'text/x-phabricator-request',
            'text/x-review-board-request',
        ]:
            return True

        return False

    def get_revisions(self, bugids):
        """Get the revisions from the hg.m.o urls in the bug comments"""
        nightly_pats = Bugzilla.get_landing_patterns(channels=['nightly'])

        def comment_handler(bug, bugid, data):
            r = Bugzilla.get_landing_comments(bug['comments'], [], nightly_pats)
            data[bugid]['revisions'] = [i['revision'] for i in r]

        def attachment_handler(attachments, bugid, data):
            for attachment in attachments:
                if self.is_patch(attachment):
                    data[bugid]['creators'].add(attachment['creator'])

        revisions = {
            str(bugid): {'revisions': [], 'creators': set()} for bugid in bugids
        }
        Bugzilla(
            bugids=bugids,
            commenthandler=comment_handler,
            commentdata=revisions,
            comment_include_fields=['text'],
            attachmenthandler=attachment_handler,
            attachmentdata=revisions,
        ).get_data().wait()

        return revisions

    def get_user_info(self, bzdata):
        """Get the user info from Bugzilla to have his real name.
        """

        def handler(user, data):
            data[user['name']] = user['real_name']

        users = set()
        for info in bzdata.values():
            users |= info['creators']

        data = {}

        if users:
            BugzillaUser(
                user_names=list(users), user_handler=handler, user_data=data
            ).wait()

        return data

    def clean_name(self, name):
        """Get the different parts of the name with letters only
        """
        res = ''
        for c in name:
            res += c if c.isalpha() else ' '
        res = res.split(' ')
        res = filter(None, res)
        res = map(lambda s: s.lower(), res)
        res = set(res)

        if len(res) >= 2:
            return res

        return set()

    def find_assignee(self, creators, patchers, bz_info):
        """Find a potential assignee.
           If an email is common between patchers (people who made patches on bugzilla)
           and hg creators then return this email.
           If "Foo Bar [:foobar]" made a patch and his hg name is "Bar Foo" return the
           corresponding Bugzilla email.
        """
        if not creators:
            return None

        patchers_mail = set(mail for _, mail in patchers)
        common = creators & patchers_mail
        if len(common) == 1:
            # there is a common email between Bz patchers & Hg email
            return list(common)[0]

        if len(common) == 0:
            # here we try to find at least 2 common elements
            # in the creator real name and in the hg author name
            patchers_name = [self.clean_name(name) for name, _ in patchers]
            for creator in creators:
                if creator not in bz_info:
                    continue
                real_name = self.clean_name(bz_info[creator])
                for name in patchers_name:
                    if len(name & real_name) >= 2:
                        return creator

        return None

    def set_autofixable(self, bzdata, user_info):
        """Set the bugs where an easy assignee can be set.
        """
        for bugid, info in bzdata.items():
            creators = info['creators']
            if bugid not in self.hgdata:
                continue
            patchers = self.hgdata[bugid]
            self.hgdata[bugid] = self.find_assignee(creators, patchers, user_info)

    def filter_from_hg(self, bzdata, user_info):
        """Get the bugs where an associated revision contains
        the bug id in the description"""

        def handler_rev(bugid, json, data):
            if bugid in json['desc']:
                user = json['user']
                if bugid not in data:
                    data[bugid] = set()
                m = HG_MAIL.match(user)
                if m:
                    hgname = m.group(1).strip()
                    hgmail = m.group(2).strip()
                    data[bugid].add((hgname, hgmail))

        url = hgmozilla.Revision.get_url('nightly')
        queries = []
        for bugid, info in bzdata.items():
            hdler = functools.partial(handler_rev, bugid)
            for rev in info['revisions']:
                queries.append(Query(url, {'node': rev}, hdler, self.hgdata))

        if queries:
            hgmozilla.Revision(queries=queries).wait()

        self.set_autofixable(bzdata, user_info)

        return self.hgdata

    def autofix(self, bugs, dryrun):
        for bugid, email in self.hgdata.items():
            if email:
                if dryrun:
                    print('Auto assign {}: {}'.format(bugid, email))
                else:
                    Bugzilla([bugid]).put({'assigned_to': email})
        return self.hgdata

    def get_bugs(self, date='today', bug_ids=[]):
        bugids = super(NoAssignee, self).get_bugs(date=date, bug_ids=bug_ids)
        bzdata = self.get_revisions(bugids)
        user_info = self.get_user_info(bzdata)

        bugids = self.filter_from_hg(bzdata, user_info)

        return bugids


if __name__ == '__main__':
    NoAssignee().run()
