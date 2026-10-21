# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import utils


def test_get_signatures():
    s = " [@ abc]\n[@ def ]\r\n [@ ghi  ]  \r\n[@ jkl]   "
    s = utils.get_signatures(s)
    assert s == {"abc", "def", "ghi", "jkl"}


def test_add_signatures():
    old = "[@ x]\n[@ y]"
    new = " [@ abc]\n[@ def ]\r\n [@ ghi  ]  \r\n[@ jkl]   "
    new = utils.get_signatures(new)

    sgns = utils.add_signatures(old, new)
    assert sgns == "[@ x]\n[@ y]\n[@ abc]\n[@ def]\n[@ ghi]\n[@ jkl]"

    sgns = utils.add_signatures("", new)
    assert sgns == "[@ abc]\n[@ def]\n[@ ghi]\n[@ jkl]"


def test_get_phab_revision_ids():
    def attachment(file_name, content_type="text/x-phabricator-request", **kwargs):
        return {
            "file_name": file_name,
            "content_type": content_type,
            "is_obsolete": 0,
            **kwargs,
        }

    bug = {
        "attachments": [
            attachment("phabricator-D123-url.txt"),
            attachment("phabricator-D456-url.txt", is_obsolete=1),
            attachment("phabricator-D789-url.txt"),
            attachment("phabricator-D42-url.txt", content_type="text/plain"),
            attachment("pr-1-url.txt", content_type="text/x-github-pull-request"),
            attachment("unexpected-name.txt"),
        ]
    }
    assert utils.get_phab_revision_ids(bug) == [123, 789]
    assert utils.get_phab_revision_ids({"attachments": []}) == []
