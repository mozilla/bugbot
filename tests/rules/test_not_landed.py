# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
from datetime import datetime, timezone

from bugbot.rules import not_landed
from bugbot.rules.not_landed import NotLanded

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
OLD = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
AUTHOR = "author@example.com"


def _attachment(att_id, rev_id, is_obsolete=0):
    url = f"https://phabricator.services.mozilla.com/D{rev_id}"
    return {
        "id": att_id,
        "bug_id": 123,
        "content_type": "text/x-phabricator-request",
        "is_obsolete": is_obsolete,
        "creator": AUTHOR,
        "data": base64.b64encode(url.encode("utf-8")).decode("ascii"),
    }


def _revision(rev_id, status="accepted", parents=()):
    phid = f"PHID-DREV-{rev_id}"
    return {
        "phid": phid,
        "fields": {
            "dateModified": OLD,
            "status": {"value": status},
            "stackGraph": {phid: [f"PHID-DREV-{p}" for p in parents]},
        },
        "attachments": {
            "reviewers": {
                "reviewers": [
                    {"status": "accepted", "reviewerPHID": "PHID-USER-reviewer"}
                ]
            }
        },
    }


class FakePhab:
    def __init__(self, revisions):
        self.revisions = {rev["phid"]: rev for rev in revisions}

    def load_revision(self, rev_id=None, rev_phid=None, **kwargs):
        return self.revisions[rev_phid or f"PHID-DREV-{rev_id}"]


def _rule(revisions):
    rule = NotLanded.__new__(NotLanded)
    rule.nweeks = 1
    rule.date = NOW
    rule.phab = FakePhab(revisions)
    return rule


def _fake_bugzilla(attachments):
    class FakeBugzilla:
        @staticmethod
        def get_landing_patterns(channels):
            return []

        def __init__(self, bugids=None, attachmentids=None, **kwargs):
            self.bugids = bugids
            self.attachmentids = attachmentids
            self.kwargs = kwargs

        def get_data(self):
            handler = self.kwargs.get("attachmenthandler")
            data = self.kwargs.get("attachmentdata")
            if self.attachmentids is not None:
                handler([a for a in attachments if a["id"] in self.attachmentids], data)
            elif handler:
                for bugid in self.bugids:
                    handler(attachments, bugid, data)
            elif "commenthandler" in self.kwargs:
                for bugid in self.bugids:
                    self.kwargs["commenthandler"](
                        {"comments": []}, bugid, self.kwargs["commentdata"]
                    )
            return self

        def wait(self):
            pass

    return FakeBugzilla


def _patch_data(monkeypatch, attachments, revisions):
    monkeypatch.setattr(not_landed, "Bugzilla", _fake_bugzilla(attachments))
    return _rule(revisions).get_patch_data({"123": {}})


def test_landable_revision_is_nagged(monkeypatch):
    data = _patch_data(monkeypatch, [_attachment(10, 1)], [_revision(1)])
    assert list(data) == ["123"]


def test_blocked_stack_is_checked_on_every_landable_revision(monkeypatch):
    # D1 waits on the unlanded D3, but D2 is the last attachment: the stack
    # check used to look only at D2 and nag anyway.
    data = _patch_data(
        monkeypatch,
        [_attachment(10, 1), _attachment(11, 2)],
        [_revision(1, parents=[3]), _revision(2), _revision(3, status="needs-review")],
    )
    assert data == {}
