# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
from dateutil.relativedelta import relativedelta
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla
import re
import requests
from auto_nag.bzcleaner import BzCleaner
from auto_nag import utils


PHAB_URL_PAT = re.compile(r'https://phabricator\.services\.mozilla\.com/D([0-9]+)')
PHAB_API = 'https://phabricator.services.mozilla.com/api/differential.revision.search'


class NotLanded(BzCleaner):
    def __init__(self):
        super(NotLanded, self).__init__()
        self.nweeks = utils.get_config(self.name(), 'number_of_weeks', 2)
        self.nyears = utils.get_config(self.name(), 'number_of_years', 2)
        self.phab_token = utils.get_login_info()['phab_api_key']

    def description(self):
        return 'Get open bugs with no ativity and with a r+ patch which hasn\'t landed'

    def name(self):
        return 'not-landed'

    def template(self):
        return 'not-landed.html'

    def subject(self):
        return 'Open bugs with no activity for {} weeks and a r+ patch which hasn\'t landed'.format(
            self.nweeks
        )

    def has_assignee(self):
        return True

    def get_extra_for_template(self):
        return {'nweeks': self.nweeks}

    def columns(self):
        return ['id', 'summary', 'assignee']

    def check_phab(self, attachment):
        """Check if the patch in Phabricator has been r+
        """
        if attachment['is_obsolete'] == 1:
            return None

        phab_url = base64.b64decode(attachment['data']).decode('utf-8')

        # extract the revision
        rev = PHAB_URL_PAT.search(phab_url).group(1)
        r = requests.post(
            PHAB_API,
            data={
                'api.token': self.phab_token,
                'queryKey': 'all',
                'constraints[ids][0]': rev,
                'attachments[reviewers]': 1,
            },
        )
        r.raise_for_status()
        data = r.json()['result']['data'][0]
        status = data['fields']['status']
        reviewers = data['attachments']['reviewers']['reviewers']
        if not reviewers:
            return False

        for reviewer in reviewers:
            if reviewer['status'] != 'accepted':
                return False

        if status.get('value', '') != 'published':
            return True

        return False

    def check_splinter(self, attachment):
        """Check if the patch in Splinter has been r+
        """
        if attachment['is_patch'] == 0 or attachment['is_obsolete'] == 1:
            return None

        flags = attachment['flags']
        # no flags == no review
        if not flags:
            return False

        # no flag called review == no review
        if all(flag['name'] != 'review' for flag in flags):
            return False

        # check the attachment flags
        for flag in flags:
            if flag['name'] == 'review' and flag['status'] != '+':
                return False
        return True

    def handle_attachment(self, attachment, res):
        ct = attachment['content_type']
        if ct == 'text/plain':
            if 'splinter' not in res or res['splinter']:
                c = self.check_splinter(attachment)
                if c is not None:
                    res['splinter'] = c
        elif ct == 'text/x-phabricator-request':
            if 'phab' not in res or res['phab']:
                c = self.check_phab(attachment)
                if c is not None:
                    res['phab'] = c

    def get_patch_data(self, bugs):
        """Get patch information in bugs
        """
        nightly_pats = Bugzilla.get_landing_patterns(channels=['nightly'])

        def comment_handler(bug, bugid, data):
            r = Bugzilla.get_landing_comments(bug['comments'], [], nightly_pats)
            landed = bool(r)
            if not landed:
                for comment in bug['comments']:
                    comment = comment['text'].lower()
                    if 'backed out' in comment or 'backout' in comment:
                        landed = True
                        break

            data[bugid]['landed'] = landed

        def attachment_handler(attachments, bugid, data):
            res = {}
            for attachment in attachments:
                self.handle_attachment(attachment, res)

            if 'phab' in res:
                if res['phab']:
                    data[bugid]['patch'] = 'phab'
            elif 'splinter' in res and res['splinter']:
                data[bugid]['patch'] = 'splinter'

        bugids = list(bugs.keys())
        data = {bugid: {'landed': False, 'patch': None} for bugid in bugids}
        Bugzilla(
            bugids=bugids, attachmenthandler=attachment_handler, attachmentdata=data
        ).get_data().wait()

        data = {bugid: v for bugid, v in data.items() if v['patch'] is not None}
        splinter_bugs = [bugid for bugid, v in data.items() if v['patch'] == 'splinter']

        Bugzilla(
            bugids=splinter_bugs,
            commenthandler=comment_handler,
            commentdata=data,
            comment_include_fields=['text'],
        ).get_data().wait()

        data = {
            bugid
            for bugid, v in data.items()
            if v['patch'] == 'phab' or not v['landed']
        }

        return data

    def get_bz_params(self, date):
        date = lmdutils.get_date_ymd(date)
        start_date = date - relativedelta(years=self.nyears)
        params = {
            'resolution': '---',
            'f1': 'attachment.ispatch',
            'n2': 1,
            'f2': 'attachments.isobsolete',
            'f3': 'attachments.mimetype',
            'o3': 'anywordssubstr',
            'v3': 'text/x-phabricator-request,text/plain',
            'f4': 'creation_ts',
            'o4': 'greaterthan',
            'v4': start_date,
            'f5': 'days_elapsed',
            'o5': 'greaterthaneq',
            'v5': self.nweeks * 7,
        }

        return params

    def get_bugs(self, date='today', bug_ids=[]):
        bugs = super(NotLanded, self).get_bugs(date=date, bug_ids=bug_ids)
        bugs_patch = self.get_patch_data(bugs)
        bugs = {bugid: bugs[bugid] for bugid in bugs_patch}

        return bugs


if __name__ == '__main__':
    NotLanded().run()
