# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class CopyDuplicateInfo(BzCleaner):
    def __init__(self):
        super(CopyDuplicateInfo, self).__init__()
        self.autofix_data = {}

    def description(self):
        return 'Bugs which are DUPLICATE and some info haven\'t been moved'

    def has_product_component(self):
        return True

    def set_autofix(self, bugs, dups, signatures, pcs):
        for bugid, missed_sgns in signatures.items():
            sgns = dups[bugid]['signature']
            sgns = utils.add_signatures(sgns, missed_sgns)
            self.autofix_data[bugid] = {'cf_crash_signature': sgns}

        for bugid, pc in pcs.items():
            if bugid in self.autofix_data:
                self.autofix_data[bugid].update(pc)
            else:
                self.autofix_data[bugid] = pc

    def get_fixed_bugs(self, bugs, dups, signatures, pcs):
        res = {}
        for bugid in signatures.keys():
            res[bugid] = info = dups[bugid]
            info['update_signature'] = 'Yes'

        for bugid in pcs.keys():
            if bugid in res:
                res[bugid]['update_pc'] = 'Yes'
            else:
                res[bugid] = info = bugs[bugid]
                info['update_pc'] = 'Yes'

        for info in res.values():
            if 'update_pc' not in info:
                info['update_pc'] = 'No'
            if 'update_signature' not in info:
                info['update_signature'] = 'No'

        return res

    def columns(self):
        return ['id', 'summary', 'update_signature', 'update_pc']

    def sort_columns(self):
        return lambda p: (
            0 if p[2] == 'Yes' else 1,
            0 if p[3] == 'Yes' else 1,
            -int(p[0]),
        )

    def get_autofix_change(self):
        return self.autofix_data

    def handle_bug(self, bug, data):
        bugid = str(bug['id'])
        data[bugid] = {
            'id': bugid,
            'summary': self.get_summary(bug),
            'signature': bug.get('cf_crash_signature', ''),
            'dupe': str(bug['dupe_of']),
            'product': bug['product'],
            'component': bug['component'],
            'version': bug['version'],
        }
        return bug

    def get_dups(self, bugs):
        def handler(bug, data):
            self.handle_bug(bug, data)

        bugids = [info['dupe'] for info in bugs.values()]
        data = {}

        Bugzilla(
            bugids=bugids,
            include_fields=[
                'cf_crash_signature',
                'dupe_of',
                'product',
                'component',
                'id',
                'summary',
                'groups',
                'version',
            ],
            bughandler=handler,
            bugdata=data,
        ).get_data().wait()

        return data

    def compare(self, bugs, dups):
        # each bug in bugs is the dup of one in dups
        # so the characteristics of this bug should be in the dup
        signatures = {}
        pcs = {}
        for bugid, info in bugs.items():
            dupid = info['dupe']
            if dupid not in dups:
                # the bug is unaccessible (sec bug for example)
                continue

            dup = dups[dupid]
            bs = utils.get_signatures(info['signature'])
            ds = utils.get_signatures(dup['signature'])
            if not bs.issubset(ds):
                signatures[dupid] = bs - ds

            pc = {}
            for x in ['product', 'component']:
                if info[x] != dup[x]:
                    pc[x] = dup[x]
            if pc:
                # when we change the product, we change the version too
                # to avoid incompatible version in the new product
                if 'product' in pc and info['version'] != dup['version']:
                    pc['version'] = dup['version']
                pcs[bugid] = pc

        # Don't move product/component for now
        # return signatures, pcs
        return signatures, {}

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        fields = ['cf_crash_signature', 'dupe_of', 'version']
        params = {
            'include_fields': fields,
            'resolution': 'DUPLICATE',
            'f1': 'resolution',
            'o1': 'changedafter',
            'v1': start_date,
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(CopyDuplicateInfo, self).get_bugs(date=date, bug_ids=bug_ids)
        dups = self.get_dups(bugs)
        signatures, pcs = self.compare(bugs, dups)

        self.set_autofix(bugs, dups, signatures, pcs)
        bugs = self.get_fixed_bugs(bugs, dups, signatures, pcs)

        return bugs


if __name__ == '__main__':
    CopyDuplicateInfo().run()
