# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import time

import requests

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
