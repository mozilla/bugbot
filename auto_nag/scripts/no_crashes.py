# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dateutil.relativedelta import relativedelta
from libmozdata.socorro import SuperSearch
from libmozdata import utils as lmdutils
import sys

from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


class SocorroError(Exception):
    pass


class NoCrashes(BzCleaner):
    def __init__(self):
        super(NoCrashes, self).__init__()
        self.nweeks = utils.get_config(self.name(), 'number_of_weeks', 12)

    def description(self):
        return 'Get bugs with crash signatures which have no more crashes'

    def name(self):
        return 'nocrashes'

    def template(self):
        return 'no_crashes.html'

    def subject(self):
        return 'Bugs with no more crashes in the last {} weeks'.format(self.nweeks)

    def get_extra_for_template(self):
        return {'nweeks': self.nweeks}

    def get_data(self):
        return {'signatures': set(), 'ids': {}}

    def get_bz_params(self, date):
        date = lmdutils.get_date_ymd(date) - relativedelta(weeks=self.nweeks)
        reporters = self.get_config('reporter_exception', default=[])
        reporters = ','.join(reporters)
        keywords = self.get_config('keyword_exception', default=[])
        keywords = ','.join(keywords)
        fields = ['cf_crash_signature']
        params = {
            'include_fields': fields,
            'resolution': '---',
            'f1': 'cf_crash_signature',
            'o1': 'isnotempty',
            'f2': 'creation_ts',
            'o2': 'lessthan',
            'v2': date,
            'f3': 'days_elapsed',
            'o3': 'greaterthan',
            'v3': self.nweeks * 7,
        }

        if reporters:
            params.update({'f4': 'reporter', 'o4': 'nowordssubstr', 'v4': reporters})

        if keywords:
            params.update({'f5': 'keywords', 'o5': 'nowords', 'v5': keywords})

        return params

    def chunkify(self, signatures):
        """Make some chunks with signatures,
           the total length of each chunk must be <= 2048"""
        total = sum(len(s) for s in signatures)
        M = 2048
        n = total / M + 1
        res = [[M, []] for _ in range(n)]
        for s in signatures:
            L = len(s)
            added = False
            for i in res:
                if L < i[0]:
                    added = True
                    i[1].append(s)
                    i[0] -= L
                    break
            if not added:
                res.append([M - L, [s]])
        res = [x for _, x in res]
        return res, max(len(x) for x in res)

    def bughandler(self, bug, data):
        """bug handler for the Bugzilla query"""
        if 'cf_crash_signature' not in bug:
            return
        sgns = utils.get_signatures(bug['cf_crash_signature'])
        id = bug['id']
        data['ids'][id] = sgns
        signatures = data['signatures']
        for s in sgns:
            signatures.add(s)

    def get_stats(self, signatures, date):
        def handler(json, data):
            if json['errors']:
                raise SocorroError()
            del json['hits']
            for facet in json['facets'].get('signature', {}):
                data.remove(facet['term'])

        date = lmdutils.get_date_ymd(date) - relativedelta(weeks=self.nweeks)
        search_date = SuperSearch.get_search_date(date)
        chunks, size = self.chunkify(signatures)
        base = {
            'date': search_date,
            'signature': '',
            '_result_number': 0,
            '_facets': 'signature',
            '_facets_size': size,
        }

        searches = []
        for chunk in chunks:
            params = base.copy()
            params['signature'] = ['=' + x for x in chunk]
            searches.append(
                SuperSearch(params=params, handler=handler, handlerdata=signatures)
            )

        for s in searches:
            s.wait()

    def get_bugs_without_crashes(self, data):
        # data['ids'] contains bugid => set(...signatures...)
        # data['signatures'] is a set of signatures with no crashes
        res = []
        signatures = data['signatures']
        for bugid, bug_sgns in data['ids'].items():
            if bug_sgns < signatures:
                # all the signatures in the bug have no crashes
                res.append(bugid)
        return res

    def get_autofix_change(self):
        return {
            'comment': {
                'body': 'Closing because no crashes reported for {} weeks.'.format(
                    self.nweeks
                )
            },
            'status': 'RESOLVED',
            'resolution': 'WONTFIX',
        }

    def get_bugs(self, date='today', bug_ids=[]):
        data = super(NoCrashes, self).get_bugs(date=date, bug_ids=bug_ids)
        try:
            self.get_stats(data['signatures'], date)
        except SocorroError:
            print('An error occurred when getting data from Socorro. Execution ended.')
            sys.exit(1)

        bugids = self.get_bugs_without_crashes(data)

        return sorted(bugids)


if __name__ == '__main__':
    NoCrashes().run()
