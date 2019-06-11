# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import lzma
import os
import shutil
from urllib.error import HTTPError
from urllib.request import urlretrieve

import requests
from bugbug import bugzilla
from libmozdata.bugzilla import Bugzilla

from auto_nag import logger
from auto_nag.bzcleaner import BzCleaner


class BugbugScript(BzCleaner):
    def __init__(self):
        super().__init__()
        self.model = self.model_class.load(self.retrieve_model())
        self.to_cache = set()

    def retrieve_model(self):
        os.makedirs("models", exist_ok=True)

        file_name = f"{self.name()}model"  # noqa: E999
        file_path = os.path.join("models", file_name)

        model_url = f"https://index.taskcluster.net/v1/task/project.relman.bugbug.train_{self.name()}.latest/artifacts/public/{file_name}.xz"  # noqa
        r = requests.head(model_url, allow_redirects=True)
        new_etag = r.headers["ETag"]

        try:
            with open(f"{file_path}.etag", "r") as f:  # noqa
                old_etag = f.read()
        except IOError:
            old_etag = None

        if old_etag != new_etag:
            try:
                urlretrieve(model_url, f"{file_path}.xz")
            except HTTPError:
                logger.exception("Tool {}".format(self.name()))
                return file_path

            with lzma.open(f"{file_path}.xz", "rb") as input_f:  # noqa
                with open(file_path, "wb") as output_f:
                    shutil.copyfileobj(input_f, output_f)

            with open(f"{file_path}.etag", "w") as f:  # noqa
                f.write(new_etag)

        return file_path

    def get_data(self):
        return list()

    def amend_bzparams(self, params, bug_ids):
        super().amend_bzparams(params, bug_ids)
        params["include_fields"] = "id"

    def bughandler(self, bug, data):
        bugid = bug["id"]
        if bugid in self.cache:
            return
        data.append(bugid)

    def remove_using_history(self, bugs):
        return bugs

    def failure_callback(self, bugid):
        self.to_cache.remove(int(bugid))

    def terminate(self):
        self.add_to_cache(self.to_cache)

    def get_bugs(self, date="today", bug_ids=[]):
        # Retrieve bugs to analyze.
        old_CHUNK_SIZE = Bugzilla.BUGZILLA_CHUNK_SIZE
        try:
            Bugzilla.BUGZILLA_CHUNK_SIZE = 7000
            bug_ids = super().get_bugs(date=date, bug_ids=bug_ids)
        finally:
            Bugzilla.BUGZILLA_CHUNK_SIZE = old_CHUNK_SIZE

        bugs = bugzilla.get(bug_ids)
        bugs = list(bugs.values())

        # Add bugs that we are classifying now to the cache.
        # Normally it's called in bzcleaner::get_mails (with the results of get_bugs)
        # but since some bugs (we don't want to analyze again) are removed thanks
        # to their history, we must add_to_cache here.
        self.to_cache = {bug["id"] for bug in bugs}

        bugs = self.remove_using_history(bugs)

        # Analyze bugs (make a copy as bugbug could change some properties of the objects).
        if len(bug_ids) > 0:
            probs = self.model.classify(copy.deepcopy(bugs), True)
        else:
            probs = []

        return bugs, probs
