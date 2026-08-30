# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64

from bugbot import utils
from bugbot.rules.not_landed import NEEDINFO_TRACKING_PREFIX, NotLanded


def _rule(monkeypatch):
    monkeypatch.setattr(utils, "get_login_info", lambda: {"phab_api_key": "test-key"})
    return NotLanded()


def test_new_needinfo_tracks_exact_revision_ids(monkeypatch):
    rule = _rule(monkeypatch)
    rule.needinfo_revision_ids = {"123": {124, 123}}

    assert rule.get_db_extra()["123"] == f"{NEEDINFO_TRACKING_PREFIX}123,124"


def test_unlanded_attachment_records_revision_id(monkeypatch):
    rule = _rule(monkeypatch)
    monkeypatch.setattr(rule, "check_phab", lambda attachment, reviewers: True)
    result = {"reviewers_phid": set()}
    attachment = {
        "content_type": "text/x-phabricator-request",
        "creator": "author@example.com",
        "data": base64.b64encode(
            b"https://phabricator.services.mozilla.com/D123"
        ).decode(),
    }

    rule.handle_attachment(attachment, result)

    assert result["revision_ids"] == {123}
