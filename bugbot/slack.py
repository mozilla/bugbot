# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Post messages to Slack.

One bot for the whole of bugbot. Everything about who is posting lives here --
the token it authenticates with and the name it appears under -- and a caller
supplies only the message and where to send it. Where a rule posts is that
rule's to say, kept wherever the rest of its configuration is -- in the rule, or
in a module it shares with the other rules it posts alongside -- so a second
rule posting somewhere else needs no change in here.

Messages go through chat.postMessage, which needs a bot token carrying
chat:write, and chat:write.public as well to post to a channel the bot has not
been invited to. One token serves every rule, so it is read from here rather
than passed in: it is a secret, and comes from `slack_bot_token` in
`configs/config.json` or from `SLACK_ACCESS_TOKEN`.

A channel is an ID rather than a name -- a "C…" string, the last section of a
channel's 'copy link' URL, or "D…" for a DM. Unlike the token it is not a
secret, so it belongs with a rule's configuration and not in config.json.

Messages are posted under `USERNAME` rather than whatever the Slack app happens
to be called, which needs `chat:write.customize` on the token as well.

`SLACK_API_URL`, `SLACK_ACCESS_TOKEN` and the error wording follow taskcluster's
notify service (services/notify), which solves the same problem. `SLACK_API_URL`
exists to point at a test server, which is the only way to exercise any of this
without a real token.
"""

import json
import os

import requests

from bugbot import utils

TIMEOUT_SECONDS = 15

DEFAULT_API_URL = "https://slack.com/api/"
API_URL_VAR = "SLACK_API_URL"
TOKEN_VAR = "SLACK_ACCESS_TOKEN"

# The key the bot token lives under in `configs/config.json`. Not required: a
# deployment that posts to no channel needs no token, so it is read with `.get`
# rather than validated at load time the way `bz_api_key` is.
TOKEN_KEY = "slack_bot_token"

# The name every message is posted under. Not overridable: there is one bot, so
# there is one name, and a rule choosing its own would only make bugbot look like
# several senders.
#
# A Slack app's own name is set in its app configuration, is shared by everything
# the token posts, and is generally not what a reader of one of these messages
# should see. This is what they see instead.
#
# Sending it needs `chat:write.customize` on the token on top of `chat:write`.
# Slack rejects the message outright when that scope is missing rather than
# ignoring the name, so this is not something that quietly stops working.
USERNAME = "Firefox Release Management Bot"


def get_token() -> str:
    """The bot token to post with.

    `SLACK_ACCESS_TOKEN` wins over `slack_bot_token` in `configs/config.json`. A
    missing config file counts as a missing key rather than an error, so a
    checkout with no credentials still imports.

    Raises rather than returning empty: these are cron jobs whose whole purpose is
    the message, so a missing token has to stop the run and be seen.
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

    `channel` is a channel ID; see the module docstring. Who the message comes
    from is not a caller's concern: the token and the display name are this
    module's, and every rule posts as the same bot.

    `text` is always sent: on a blocks message it is the notification and the
    fallback for clients that can't render blocks.

    `thread_ts` replies in thread, and takes the timestamp this returns for an
    earlier message.

    Link previews are always suppressed. These messages are notifications built
    around their links, and an unfurl below one repeats what the message already
    says at several times the height.

    Not retried, unlike reads: a POST that times out may well have arrived, so
    retrying risks posting the message twice. A failure here fails the run
    instead, which is visible in the error digest and harmless to repeat by hand.
    """
    payload: dict = {
        "channel": channel,
        "text": text,
        "username": USERNAME,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    if blocks is not None:
        payload["blocks"] = blocks
    if thread_ts is not None:
        payload["thread_ts"] = thread_ts

    api_url = (os.environ.get(API_URL_VAR) or DEFAULT_API_URL).rstrip("/")

    # The body is encoded here rather than passed as `json=` so the charset can be
    # spelled out: Slack answers a bare application/json with a missing_charset
    # warning.
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

    # chat.postMessage reports application errors as HTTP 200 with ok=false, so the
    # body is what has to be checked rather than the status.
    result = response.json()
    if not result.get("ok"):
        reason = result.get("error", result)
        # On missing_scope Slack names the scope it wanted and the ones the token
        # carries. Without those two the error is very hard to act on.
        if result.get("needed"):
            reason += f" (needed {result['needed']}, token has {result['provided']})"
        raise RuntimeError(f"error posting slack message: {reason}")

    return result["ts"]
