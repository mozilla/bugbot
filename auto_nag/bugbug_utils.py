# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import time

import requests
from bugbug import bugzilla
from libmozdata.bugzilla import Bugzilla

from auto_nag.bzcleaner import BzCleaner

BUGBUG_HTTP_SERVER = os.environ.get(
    "BUGBUG_HTTP_SERVER", "https://bugbug.herokuapp.com/"
)


def get_bug_ids_classification(model, bug_ids, retry_count=100, retry_sleep=1):
    if len(bug_ids) > 0:
        url = f"{BUGBUG_HTTP_SERVER}/{model}/predict/batch"

        for _ in range(retry_count):
            response = requests.post(
                url, headers={"X-Api-Key": "Test"}, json={"bugs": bug_ids}
            )
            if response.status_code == 200:
                break
            elif response.status_code == 202:
                # All the results are not ready yet, try again in 1 second
                time.sleep(retry_sleep)
            else:
                response.raise_for_status()
        else:
            total_sleep = retry_count * retry_sleep
            msg = f"Couldn't get {len(bug_ids)} bug classification in {total_sleep} seconds, aborting"
            raise Exception(msg)

        json_response = response.json()["bugs"]
    else:
        json_response = {}

    return json_response


class BugbugScript(BzCleaner):
    def __init__(self):
        super().__init__()

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

    def get_bugs(self, model, date="today", bug_ids=[], retry_count=100, retry_sleep=1):
        # Retrieve bugs to analyze.
        old_CHUNK_SIZE = Bugzilla.BUGZILLA_CHUNK_SIZE
        try:
            Bugzilla.BUGZILLA_CHUNK_SIZE = 7000
            bug_ids = super().get_bugs(date=date, bug_ids=bug_ids)
        finally:
            Bugzilla.BUGZILLA_CHUNK_SIZE = old_CHUNK_SIZE

        # Some consumer of this API needs the actual bugs so download them
        # List of scripts using the bug data:
        # - component
        # - defectenhancementtask.py
        # - regression.py
        # - stepstoreproduce.py
        bugs = bugzilla.get(bug_ids)
        bugs = list(bugs.values())

        return get_bug_ids_classification(model, bug_ids, retry_count, retry_sleep)
