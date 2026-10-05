# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Post messages to Slack.

One bot for the whole of bugbot: the token and the name it appears under live
here, and a caller supplies only the message and where to send it.

`SLACK_API_URL`, `SLACK_ACCESS_TOKEN` and the error wording follow taskcluster's
notify service (services/notify). `SLACK_API_URL` points at a test server, which
is the only way to exercise this without a real token.
"""

import json
import os

import requests

from bugbot import utils

TIMEOUT_SECONDS = 15

DEFAULT_API_URL = "https://slack.com/api/"
API_URL_VAR = "SLACK_API_URL"
TOKEN_VAR = "SLACK_ACCESS_TOKEN"

# Read with `.get` rather than validated at load time the way `bz_api_key` is: a
# deployment that posts to no channel needs no token.
TOKEN_KEY = "slack_bot_token"

# The name every message is posted under, instead of whatever the Slack app
# happens to be called. Needs `chat:write.customize` on the token, and Slack
# rejects the message outright when that scope is missing.
USERNAME = "Firefox Release Management Bot"


def get_token() -> str:
    """The bot token to post with, `SLACK_ACCESS_TOKEN` winning over the config.

    A missing config file counts as a missing key, so a checkout with no
    credentials still imports. Raises rather than returning empty: these are cron
    jobs whose whole purpose is the message.
    """
    token = os.environ.get(TOKEN_VAR, "").strip()
    if token:
        return token

    try:
        token = utils.get_login_info().get(TOKEN_KEY, "")
    except OSError:
        token = ""

    if not token:
        raise RuntimeError(
            f"Posting to Slack needs a bot token with the chat:write scope "
            f"(chat:write.public to post without being invited), from {TOKEN_VAR} "
            f"or {TOKEN_KEY} in configs/config.json"
        )

    return token


def post_to_slack(
    channel: str,
    text: str,
    blocks: list[dict] | None = None,
    thread_ts: str | None = None,
) -> str:
    """Post a message to a Slack channel, and return its timestamp.

    `channel` is a channel ID, the last section of a channel's 'copy link' URL.
    `text` is the notification and the fallback for clients that can't render
    blocks. `thread_ts` takes the timestamp this returns for an earlier message.

    Not retried, unlike reads: a POST that times out may well have arrived, so
    retrying risks posting the message twice.
    """
    payload: dict = {
        "channel": channel,
        "text": text,
        "username": USERNAME,
        # These messages are built around their links, and an unfurl below one
        # repeats what the message already says.
        "unfurl_links": False,
        "unfurl_media": False,
    }
    if blocks is not None:
        payload["blocks"] = blocks
    if thread_ts is not None:
        payload["thread_ts"] = thread_ts

    api_url = (os.environ.get(API_URL_VAR) or DEFAULT_API_URL).rstrip("/")

    # Encoded here rather than passed as `json=` so the charset can be spelled
    # out: Slack answers a bare application/json with a missing_charset warning.
    response = requests.post(
        f"{api_url}/chat.postMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {get_token()}",
        },
        timeout=TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise RuntimeError(
            f"Slack returned HTTP {response.status_code}: {response.text.strip()}"
        )

    # chat.postMessage reports application errors as HTTP 200 with ok=false.
    result = response.json()
    if not result.get("ok"):
        reason = result.get("error", result)
        # On missing_scope Slack names the scope it wanted and the ones the token
        # carries. Without those two the error is very hard to act on.
        if result.get("needed"):
            reason += f" (needed {result['needed']}, token has {result['provided']})"
        raise RuntimeError(f"error posting slack message: {reason}")

    return result["ts"]
