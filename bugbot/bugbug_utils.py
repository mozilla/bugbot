# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import time
from typing import Iterable

import requests

BUGBUG_HTTP_SERVER = os.environ.get("BUGBUG_HTTP_SERVER", "https://bugbug.moz.tools/")


def classification_http_request(url, bug_ids):
    response = requests.post(
        url, headers={"X-Api-Key": "autonag"}, json={"bugs": bug_ids}
    )

    response.raise_for_status()

    return response.json()


def get_bug_ids_classification(
    model: str, bugs: Iterable, retry_count: int = 21, retry_sleep: int = 10
):
    """Get the classification for a list of bug ids.

    Args:
        model: The model to use for the classification.
        bug_ids: The list of bug ids to classify, if a dictionary is passed, the
            keys will be used as bug ids.
        retry_count: The number of times to retry the request.
        retry_sleep: The number of seconds to sleep between retries.

    Returns:
        A dictionary with the bug ids as keys and the classification as values.
    """
    # Copy the bug ids to avoid mutating it
    bug_ids = set(map(int, bugs))
    if len(bug_ids) == 0:
        return {}

    url = f"{BUGBUG_HTTP_SERVER}/{model}/predict/batch"

    json_response = {}

    for _ in range(retry_count):
        response = classification_http_request(url, list(bug_ids))

        # Check which bug ids are ready
        for bug_id, bug_data in response["bugs"].items():
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
        msg = f"Couldn't get {len(bug_ids)} bug classifications in {total_sleep} seconds, aborting"
        raise Exception(msg)

    return json_response
