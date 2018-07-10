# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import functools
from libmozdata import hgmozilla
from libmozdata.bugzilla import Bugzilla
from libmozdata.connection import Query
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class NoAssignee(BzCleaner):

    def __init__(self):
        super(NoAssignee, self).__init__()

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
        reporters = utils.get_config('no_assignee', 'reporter_exception', [])
        reporters = ','.join(reporters)
        regexp = 'http[s]?://hg\.mozilla\.org/(releases/)?mozilla-[^/]+/rev/[0-9a-f]+'  # NOQA
        params = {'resolution': 'FIXED',
                  'bug_status': ['RESOLVED', 'VERIFIED'],
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
                  'v4': end_date}
        if reporters:
            params.update({'f5': 'reporter',
                           'o5': 'nowordssubstr',
                           'v5': reporters})

        return params

    def get_revisions(self, bugids):
        """Get the revisions from the hg.m.o urls in the bug comments"""
        nightly_pats = Bugzilla.get_landing_patterns(channels=['nightly'])

        def comment_handler(bug, bugid, data):
            r = Bugzilla.get_landing_comments(
                bug['comments'], [], nightly_pats)
            data[bugid] = [i['revision'] for i in r]

        revisions = {}
        Bugzilla(bugids=bugids,
                 commenthandler=comment_handler,
                 commentdata=revisions,
                 comment_include_fields=['text']).get_data().wait()

        return revisions

    def filter_from_hg(self, revisions):
        """Get the bugs where an associated revision contains
        the bug id in the description"""

        def handler_rev(bugid, json, data):
            if bugid in json['desc']:
                data.add(int(bugid))

        url = hgmozilla.Revision.get_url('nightly')
        data = set()
        queries = []
        for bugid, rev in revisions.items():
            queries.append(Query(url, {'node': rev},
                                 functools.partial(handler_rev,
                                                   bugid), data))

        if queries:
            hgmozilla.Revision(queries=queries).wait()

        return list(sorted(data))

    def get_bugs(self, date='today', bug_ids=[]):
        bugids = super(NoAssignee, self).get_bugs(date=date, bug_ids=bug_ids)
        revisions = self.get_revisions(bugids)
        bugids = self.filter_from_hg(revisions)

        return bugids


if __name__ == '__main__':
    NoAssignee().run()
