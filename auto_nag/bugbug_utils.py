# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import time
from itertools import islice

import requests

BUGBUG_HTTP_SERVER = os.environ.get(
    "BUGBUG_HTTP_SERVER", "https://bugbug.herokuapp.com/"
)


def chunks(it, size):
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())


def classification_http_request(url, bug_ids):
    response = requests.post(url, headers={"X-Api-Key": "Test"}, json={"bugs": bug_ids})

    response.raise_for_status()

    return response


def get_bug_ids_classification(
    model, bug_ids, retry_count=100, retry_sleep=1, batch_size=1000
):
    if len(bug_ids) > 0:
        url = f"{BUGBUG_HTTP_SERVER}/{model}/predict/batch"

        # Copy the bug ids to avoid mutating it
        bug_ids = set(map(int, bug_ids))

        json_response = {}

        for _ in range(retry_count):

            # Do the call in chunks
            for chunk in list(chunks(bug_ids, batch_size)):
                # The send the current chunk
                response = classification_http_request(url, chunk)
                response.raise_for_status()

                # Check which bug ids are ready
                for bug_id, bug_data in response.json()["bugs"].items():
                    if not bug_data.get("ready", True):
                        continue

                    # The bug is ready, add it to the json_response and pop it
                    # up from the current batch
                    # The http service returns strings for backward compatibility reasons
                    bug_ids.remove(int(bug_id))
                    json_response[bug_id] = bug_data

            if len(bug_ids) == 0:
                break
            else:
                time.sleep(retry_sleep)

        else:
            total_sleep = retry_count * retry_sleep
            msg = f"Couldn't get {len(bug_ids)} bug classification in {total_sleep} seconds, aborting"
            raise Exception(msg)
    else:
        json_response = {}

    return json_response
