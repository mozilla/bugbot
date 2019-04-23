# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
from libmozdata.connection import Query
from libmozdata import hgmozilla
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils
from auto_nag.nag_me import Nag


class Unlanded(BzCleaner, Nag):
    def __init__(self, channel):
        super(Unlanded, self).__init__()
        self.channel = channel
        self.bug_ids = []
        self.versions = utils.get_checked_versions()
        self.channel_pat = Bugzilla.get_landing_patterns(channels=[channel])

    def description(self):
        return 'Bugs with unlanded {} uplifts'.format(self.channel)

    def name(self):
        return 'unlanded_' + self.channel

    def template(self):
        return 'unlanded.html'

    def get_config(self, entry, default=None):
        return utils.get_config('unlanded', entry, default=default)

    def nag_template(self):
        return self.template()

    def has_last_comment_time(self):
        return True

    def has_default_products(self):
        return False

    def has_assignee(self):
        return True

    def columns(self):
        return ['id', 'summary', 'assignee', 'landed', 'last_comment']

    def sort_columns(self):
        return lambda p: (0 if p[3] == 'No' else 1, -int(p[0]))

    def has_enough_data(self):
        if not self.versions:
            return False

        self.version = self.versions[self.channel]
        if self.channel == 'esr':
            self.bug_ids = utils.get_report_bugs(self.channel + self.version)
        else:
            self.bug_ids = utils.get_report_bugs(self.channel)

        return bool(self.bug_ids)

    def get_hg(self, bugs):
        url = hgmozilla.Revision.get_url(self.channel)
        queries = []
        not_landed = set()

        def handler_rev(json, data):
            info = utils.get_info_from_hg(json)
            if info['bugid'] == data['bugid'] and not info['backedout']:
                data['ok'] = True

        for info in bugs.values():
            for rev, i in info.get('land', {}).items():
                queries.append(Query(url, {'node': rev}, handler_rev, i))

        if queries:
            hgmozilla.Revision(queries=queries).wait()

        for bugid, info in bugs.items():
            if all(not i['ok'] for i in info.get('land', {}).values()):
                not_landed.add(bugid)

        return not_landed

    def get_not_landed(self, bugs):
        not_landed = set()

        def comment_handler(bug, bugid, data):
            r = Bugzilla.get_landing_comments(bug['comments'], [], self.channel_pat)
            if not r:
                not_landed.add(bugid)
                return

            data[bugid]['land'] = {
                i['revision']: {'ok': False, 'bugid': bugid} for i in r
            }

        bugids = list(bugs.keys())
        Bugzilla(
            bugids=bugids,
            commenthandler=comment_handler,
            commentdata=bugs,
            comment_include_fields=['text'],
        ).get_data().wait()

        not_landed |= self.get_hg(bugs)

        for bugid, info in bugs.items():
            if 'land' in info:
                del info['land']
            info['landed'] = 'No' if bugid in not_landed else 'Yes'

        return bugs

    def set_people_to_nag(self, bug, buginfo):
        priority = self.get_priority(bug)
        if not self.filter_bug(priority):
            return None

        assignee = bug['assigned_to']
        buginfo['to'] = assignee
        if not self.add(assignee, buginfo):
            self.add_no_manager(buginfo['id'])
        return bug

    def get_bz_params(self, date):
        status = utils.get_flag(self.version, 'status', self.channel)
        self.tracking = utils.get_flag(self.version, 'tracking', self.channel)
        fields = [self.tracking]
        params = {
            'include_fields': fields,
            'bug_id': ','.join(self.bug_ids),
            'f1': status,
            'o1': 'nowordssubstr',
            'v1': ','.join(['unaffected', 'fixed', 'verified', 'wontfix', 'disabled']),
            'f2': self.tracking,
            'o2': 'anywordssubstr',
            'v2': ','.join(['+', 'blocking']),
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(Unlanded, self).get_bugs(date=date, bug_ids=bug_ids)
        self.get_not_landed(bugs)

        return bugs


if __name__ == '__main__':
    Unlanded('beta').run()
    Unlanded('release').run()
    Unlanded('esr').run()
