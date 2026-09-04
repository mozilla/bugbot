# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json

import pytest
import responses

from bugbot import slack

CHANNEL = "C0123456789"
TEST_API_URL = "https://slack.test/api/"
POST_MESSAGE_URL = f"{TEST_API_URL}chat.postMessage"


@pytest.fixture
def api(monkeypatch):
    """Point the transport at a test server and give it a token to use."""
    monkeypatch.setenv(slack.API_URL_VAR, TEST_API_URL)
    monkeypatch.setenv(slack.TOKEN_VAR, "xoxb-test")


@responses.activate
def test_posts_the_channel_text_and_token(api):
    responses.add(responses.POST, POST_MESSAGE_URL, json={"ok": True, "ts": "1.2"})

    assert slack.post_to_slack(CHANNEL, "a title") == "1.2"

    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer xoxb-test"
    payload = json.loads(request.body)
    assert payload["channel"] == CHANNEL
    assert payload["text"] == "a title"
    # Unfurls would repeat what a link-heavy message already says.
    assert payload["unfurl_links"] is False
    assert payload["unfurl_media"] is False
    # Posted under a readable name rather than the Slack app's own.
    assert payload["username"] == slack.USERNAME
    # Neither was passed, so neither should be sent.
    assert "blocks" not in payload
    assert "thread_ts" not in payload


@responses.activate
def test_posts_blocks_and_replies_in_thread(api):
    responses.add(responses.POST, POST_MESSAGE_URL, json={"ok": True, "ts": "3.4"})

    slack.post_to_slack(
        CHANNEL,
        "a title",
        blocks=[{"type": "divider"}],
        thread_ts="1.2",
    )

    payload = json.loads(responses.calls[0].request.body)
    assert payload["blocks"] == [{"type": "divider"}]
    assert payload["thread_ts"] == "1.2"


@responses.activate
def test_an_application_error_comes_back_as_http_200(api):
    # Slack reports a rejected payload with ok=false and a 200, so the status
    # alone would read as success.
    responses.add(
        responses.POST, POST_MESSAGE_URL, json={"ok": False, "error": "invalid_blocks"}
    )

    with pytest.raises(RuntimeError, match="invalid_blocks"):
        slack.post_to_slack(CHANNEL, "a title")


@responses.activate
def test_missing_scope_names_the_scope_it_wanted(api):
    responses.add(
        responses.POST,
        POST_MESSAGE_URL,
        json={
            "ok": False,
            "error": "missing_scope",
            "needed": "chat:write",
            "provided": "im:read",
        },
    )

    with pytest.raises(RuntimeError, match=r"missing_scope \(needed chat:write"):
        slack.post_to_slack(CHANNEL, "a title")


@responses.activate
def test_an_http_error_reports_the_body(api):
    responses.add(responses.POST, POST_MESSAGE_URL, body="nope", status=500)

    with pytest.raises(RuntimeError, match="HTTP 500: nope"):
        slack.post_to_slack(CHANNEL, "a title")


def test_the_environment_token_wins_over_the_configured_one(monkeypatch):
    monkeypatch.setenv(slack.TOKEN_VAR, "xoxb-env")
    monkeypatch.setattr(
        slack.utils, "get_login_info", lambda: {"slack_bot_token": "xoxb-cfg"}
    )

    assert slack.get_token() == "xoxb-env"

    monkeypatch.delenv(slack.TOKEN_VAR)
    assert slack.get_token() == "xoxb-cfg"


def test_a_missing_token_stops_the_run(monkeypatch):
    monkeypatch.delenv(slack.TOKEN_VAR, raising=False)
    monkeypatch.setattr(slack.utils, "get_login_info", lambda: {})

    with pytest.raises(RuntimeError, match="chat:write"):
        slack.get_token()


def test_a_missing_config_file_is_a_missing_token_not_a_crash(monkeypatch):
    def no_file():
        raise FileNotFoundError("configs/config.json")

    monkeypatch.delenv(slack.TOKEN_VAR, raising=False)
    monkeypatch.setattr(slack.utils, "get_login_info", no_file)

    with pytest.raises(RuntimeError, match="chat:write"):
        slack.get_token()


def test_the_username_is_spelled_correctly():
    # It is on every message anyone reads, so a typo here is very visible.
    assert slack.USERNAME == "Firefox Release Management Bot"
