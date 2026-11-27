# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import time
from typing import Iterable

import requests

BUGBUG_HTTP_SERVER = os.environ.get("BUGBUG_HTTP_SERVER", "https://bugbug.moz.tools/")


# The (connect, read) timeouts of the classification requests, in seconds. The
# service answers right away, with {"ready": False} for the items it is still
# classifying, so a request taking longer means it is unavailable.
REQUEST_TIMEOUT = (10, 30)

# The maximum number of bugs the service accepts in a single request for the
# classification of their commits.
MAX_BUGS_PER_COMMITS_REQUEST = 20


def get_batch_classification(
    url: str,
    kind: str,
    items: Iterable,
    retry_count: int,
    retry_sleep: int,
    max_per_request: int | None = None,
) -> dict[str, dict]:
    """Poll a batch classification endpoint until all the items are classified.

    Args:
        url: The URL of the endpoint.
        kind: The kind of items, which is also the key of the items in the
            request and in the answer, e.g. "bugs".
        items: The items to classify.
        retry_count: The number of times to retry the request.
        retry_sleep: The number of seconds to sleep between retries.
        max_per_request: The maximum number of items per request, if any.

    Returns:
        A dictionary with the items (as strings, like the service returns them)
        as keys and their classification as values.

    Raises:
        requests.RequestException: The service is unavailable, e.g. it didn't
            answer within REQUEST_TIMEOUT.
        Exception: Some items were still not classified after the retries.
    """
    pending = list(dict.fromkeys(items))
    results: dict[str, dict] = {}
    if not pending:
        return results

    step = max_per_request or len(pending)
    for _ in range(retry_count):
        for i in range(0, len(pending), step):
            response = requests.post(
                url,
                headers={"X-Api-Key": "autonag"},
                json={kind: pending[i : i + step]},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            for item, data in response.json()[kind].items():
                if data.get("ready", True):
                    results[item] = data

        pending = [item for item in pending if str(item) not in results]
        if not pending:
            return results

        time.sleep(retry_sleep)

    total_sleep = retry_count * retry_sleep
    raise Exception(
        f"Couldn't get the classification of {len(pending)} {kind} in {total_sleep} seconds, aborting"
    )


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
        The http service returns the bug ids as strings for backward
        compatibility reasons.
    """
    return get_batch_classification(
        f"{BUGBUG_HTTP_SERVER}/{model}/predict/batch",
        "bugs",
        map(int, bugs),
        retry_count,
        retry_sleep,
    )


def get_bugs_commits_classification(
    model: str, bugs: Iterable, retry_count: int = 21, retry_sleep: int = 10
) -> dict[str, dict]:
    """Get the classification of the autoland commits of a list of bugs.

    The service finds the commits of each bug (the ones whose description refers
    to it), and classifies them with a commit model.

    Args:
        model: The commit model to use for the classification, e.g. "regressor".
        bugs: The ids of the bugs whose commits to classify, if a dictionary is
            passed, the keys will be used as bug ids.
        retry_count: The number of times to retry the request.
        retry_sleep: The number of seconds to sleep between retries.

    Returns:
        A dictionary with the bug ids (as strings) as keys and, as values, the
        classification of each of their commits by hash under "commits", and
        the highest `risk_band` of the ones which were scored and not backed out
        (or None). The classification of a commit is {"available": False} when
        the service couldn't find it, otherwise its `risk_band` and its
        `ignored_reason` (e.g. "backout", "backedout"), if it doesn't count.

    Raises:
        requests.RequestException: The service is unavailable, e.g. it didn't
            answer within REQUEST_TIMEOUT.
        Exception: Some bugs were still not classified after the retries.
    """
    return get_batch_classification(
        f"{BUGBUG_HTTP_SERVER.rstrip('/')}/{model}/predict/bugs/autoland",
        "bugs",
        map(int, bugs),
        retry_count,
        retry_sleep,
        MAX_BUGS_PER_COMMITS_REQUEST,
    )
