import copy
import lzma
import json
import os
import shutil
from urllib.request import urlretrieve
import requests
from bugbug import bugzilla
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla
from auto_nag.bzcleaner import BzCleaner


class BugbugScript(BzCleaner):
    def __init__(self):
        super().__init__()
        self.cache_path = os.path.join('models', f'{self.name()}_cache.json')  # noqa

    def retrieve_model(self):
        os.makedirs('models', exist_ok=True)

        file_name = f'{self.name()}model'  # noqa: E999
        file_path = os.path.join('models', file_name)

        model_url = f'https://index.taskcluster.net/v1/task/project.releng.services.project.testing.bugbug_train.latest/artifacts/public/{file_name}.xz'  # noqa
        r = requests.head(model_url, allow_redirects=True)
        new_etag = r.headers['ETag']

        try:
            with open(f'{file_path}.etag', 'r') as f:  # noqa
                old_etag = f.read()
        except IOError:
            old_etag = None

        if old_etag != new_etag:
            urlretrieve(model_url, f'{file_path}.xz')

            with lzma.open(f'{file_path}.xz', 'rb') as input_f:  # noqa
                with open(file_path, 'wb') as output_f:
                    shutil.copyfileobj(input_f, output_f)

            with open(f'{file_path}.etag', 'w') as f:  # noqa
                f.write(new_etag)

        return file_path

    def ignore_bug_summary(self):
        return False

    def get_data(self):
        return list()

    def amend_bzparams(self, params, bug_ids):
        super().amend_bzparams(params, bug_ids)
        params['include_fields'] = 'id'

    def bughandler(self, bug, data):
        data.append(bug['id'])

    def remove_using_history(self, bugs):
        return bugs

    def get_recent_bugs(self):
        try:
            with open(self.cache_path, 'r') as f:
                recent_bugs = json.load(f)
        except FileNotFoundError:
            recent_bugs = {}

        cleaned_recent_bugs = {}
        for bug_id, date in recent_bugs.items():
            delta = lmdutils.get_date_ymd('today') - lmdutils.get_date_ymd(date)
            if delta.days < 7:
                cleaned_recent_bugs[int(bug_id)] = date

        return cleaned_recent_bugs

    def add_recent_bugs(self, recent_bugs, bugs):
        for bug in bugs:
            recent_bugs[int(bug['id'])] = lmdutils.get_today()

        with open(self.cache_path, 'w') as f:
            json.dump(recent_bugs, f)

    def get_bugs(self, date='today', bug_ids=[]):
        # Retrieve bugs to analyze.
        old_CHUNK_SIZE = Bugzilla.BUGZILLA_CHUNK_SIZE
        try:
            Bugzilla.BUGZILLA_CHUNK_SIZE = 7000
            bug_ids = super().get_bugs(date=date, bug_ids=bug_ids)
        finally:
            Bugzilla.BUGZILLA_CHUNK_SIZE = old_CHUNK_SIZE

        # Ignore bugs that we didn't manage to classify recently.
        recent_bugs = self.get_recent_bugs()

        bug_ids = [bug_id for bug_id in bug_ids if bug_id not in recent_bugs]

        bugs = bugzilla._download(bug_ids)
        bugs = list(bugs.values())

        # Add bugs that we are classifying now to the cache.
        self.add_recent_bugs(recent_bugs, bugs)

        bugs = self.remove_using_history(bugs)

        # Analyze bugs (make a copy as bugbug could change some properties of the objects).
        if len(bug_ids) > 0:
            probs = self.model.classify(copy.deepcopy(bugs), True)
        else:
            probs = []

        return bugs, probs
