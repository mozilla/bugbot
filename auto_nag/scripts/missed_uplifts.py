# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class MissedUplifts(BzCleaner):
    def __init__(self):
        super(MissedUplifts, self).__init__()
        self.versions = utils.get_checked_versions()
        if not self.versions:
            return

        self.beta = self.versions['beta']
        self.release = self.versions['release']
        self.esr = self.versions['esr']
        self.esr_str = 'esr' + str(self.esr)

        self.pending_release = utils.get_report_bugs('release', op='?')
        self.pending_beta = utils.get_report_bugs('beta', op='?')
        self.pending_esr = utils.get_report_bugs(self.esr_str, op='?')

        self.accepted_release = utils.get_report_bugs('release', op='+')
        self.accepted_beta = utils.get_report_bugs('beta', op='+')
        self.accepted_esr = utils.get_report_bugs(self.esr_str, op='+')

        self.status_central = utils.get_flag(
            self.versions['central'], 'status', 'central'
        )
        self.status_beta = utils.get_flag(self.beta, 'status', 'beta')
        self.status_release = utils.get_flag(self.release, 'status', 'release')
        self.status_esr = utils.get_flag(self.esr, 'status', 'esr')

    def description(self):
        return 'Bugs fixed in nightly but still affect other supported channels'

    def name(self):
        return 'missed-uplifts'

    def template(self):
        return 'missed_uplifts.html'

    def subject(self):
        return self.description()

    def must_run(self, date):
        weekday = date.weekday()
        return weekday <= 4

    def has_enough_data(self):
        return bool(self.versions)

    def columns(self):
        return ['id', 'priority', 'severity', 'affected', 'approvals', 'summary']

    def sort_columns(self):
        return lambda p: (tuple(int(x) for x in reversed(p[3])), -int(p[0]))

    def handle_bug(self, bug, data):
        bugid = str(bug['id'])
        beta = bug[self.status_beta]
        release = bug[self.status_release]
        esr = bug[self.status_esr]
        affected = []
        if beta == 'affected':
            affected.append(self.beta)
        if release == 'affected':
            affected.append(self.release)
        if esr == 'affected':
            affected.append(self.esr)

        approvals = []
        if bugid in self.pending_beta:
            approvals.append('beta?')
        if bugid in self.accepted_beta:
            approvals.append('beta+')

        if bugid in self.pending_release:
            approvals.append('release?')
        if bugid in self.accepted_release:
            approvals.append('release+')

        if bugid in self.pending_release:
            approvals.append('release?')
        if bugid in self.accepted_release:
            approvals.append('release+')

        if bugid in self.pending_esr:
            approvals.append(self.esr_str + '?')
        if bugid in self.accepted_esr:
            approvals.append(self.esr_str + '+')

        data[bugid] = {
            'affected': affected,
            'approvals': ', '.join(approvals),
            'priority': bug['priority'],
            'severity': bug['severity'],
        }

        return bug

    def get_bz_params(self, date):
        fields = [
            self.status_beta,
            self.status_release,
            self.status_esr,
            'priority',
            'severity',
        ]
        params = {
            'include_fields': fields,
            'resolution': ['---', 'FIXED'],
            'f1': self.status_central,
            'o1': 'anyexact',
            'v1': ','.join(['fixed', 'verified']),
            'j2': 'OR',
            'f2': 'OP',
            # affected in beta
            'f3': self.status_beta,
            'o3': 'anyexact',
            'v3': 'affected',
            # affected in release
            'f4': self.status_release,
            'o4': 'anyexact',
            'v4': 'affected',
            'f5': 'CP',
        }

        return params


if __name__ == '__main__':
    MissedUplifts().run()
