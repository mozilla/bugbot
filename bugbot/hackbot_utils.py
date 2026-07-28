# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os

import requests

from bugbot import utils

DEFAULT_API_URL = "https://hackbot-api.moz.tools"

TIMEOUT = 60


def api_url() -> str:
    """The hackbot API base URL.

    hackbot runs the LLM agents (see mozilla/bugbug's services/hackbot-api). We
    only ever start a run from here: the agent applies its own findings to
    Bugzilla and reports the result to Slack itself, so nothing comes back to us.

    Defaults to the production deployment so the cron host needs no extra
    environment, the way ``BUGBUG_HTTP_SERVER`` does. Override
    ``HACKBOT_API_URL`` to point at another deployment — that is the name
    hackbot's other clients already use (the pulse listener's setting and the
    console's deploy env), so there is one name to remember across all three.

    Read per call rather than at import so the override is settable by anything
    that configures the environment after this module loads.
    """
    return os.environ.get("HACKBOT_API_URL", DEFAULT_API_URL)


def trigger_agent_run(agent: str, inputs: dict) -> str:
    """Start a hackbot agent run.

    Args:
        agent: The agent to run, e.g. `frontend-triage`.
        inputs: The agent's per-run inputs, e.g. `{"bug_id": 1234567}`.

    Returns:
        The id of the created run.
    """
    base_url = api_url()
    if not base_url:
        raise ValueError("HACKBOT_API_URL is not set")

    response = requests.post(
        f"{base_url.rstrip('/')}/agents/{agent}/runs",
        headers={"X-API-Key": utils.get_login_info()["hackbot_api_key"]},
        json=inputs,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    return response.json()["run_id"]
