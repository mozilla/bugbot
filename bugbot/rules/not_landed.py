# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import random
import re

from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla, BugzillaUser
from libmozdata.phabricator import (
    PhabricatorAPI,
    PhabricatorBzNotFoundException,
    PhabricatorRevisionNotFoundException,
)

from bugbot import utils
from bugbot.bzcleaner import BzCleaner

PHAB_URL_PAT = re.compile(r"https://phabricator\.services\.mozilla\.com/D([0-9]+)")


class NotLanded(BzCleaner):
    def __init__(self):
        super(NotLanded, self).__init__()
        self.nweeks = utils.get_config(self.name(), "number_of_weeks", 2)
        self.nyears = utils.get_config(self.name(), "number_of_years", 2)
        self.phab = PhabricatorAPI(utils.get_login_info()["phab_api_key"])
        self.extra_ni = {}

    def description(self):
        return "Open bugs with no activity for {} weeks and a r+ patch which hasn't landed".format(
            self.nweeks
        )

    def has_assignee(self):
        return True

    def get_extra_for_template(self):
        return {"nweeks": self.nweeks}

    def get_extra_for_needinfo_template(self):
        self.extra_ni.update(self.get_extra_for_template())
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "assignee"]

    def handle_bug(self, bug, data):
        if self.has_bot_set_ni(bug):
            return None

        bugid = str(bug["id"])
        assignee = bug.get("assigned_to", "")
        if utils.is_no_assignee(assignee):
            assignee = ""
            nickname = ""
        else:
            nickname = bug["assigned_to_detail"]["nick"]

        data[bugid] = {
            "assigned_to": assignee,
            "nickname": nickname,
            "deps": set(bug["depends_on"]),
        }

        return bug

    def filter_bugs(self, bugs):
        # We must remove bugs which have open dependencies (except meta bugs)
        # because devs may wait for those bugs to be fixed before their patch
        # can land.

        all_deps = set(dep for info in bugs.values() for dep in info["deps"])

        def bug_handler(bug, data):
            if (
                bug["status"] in {"RESOLVED", "VERIFIED", "CLOSED"}
                or "meta" in bug["keywords"]
            ):
                data.add(bug["id"])

        useless = set()
        Bugzilla(
            bugids=list(all_deps),
            include_fields=["id", "keywords", "status"],
            bughandler=bug_handler,
            bugdata=useless,
        ).get_data().wait()

        for bugid, info in bugs.items():
            # finally deps will contain open bugs which are not meta
            info["deps"] -= useless

        # keep bugs with no deps
        bugs = {bugid: info for bugid, info in bugs.items() if not info["deps"]}

        return bugs

    def check_phab(self, attachment, reviewers_phid):
        """Check if the patch in Phabricator has been r+"""
        if attachment["is_obsolete"] == 1:
            return None

        phab_url = base64.b64decode(attachment["data"]).decode("utf-8")

        # extract the revision
        rev = PHAB_URL_PAT.search(phab_url).group(1)
        try:
            data = self.phab.load_revision(
                rev_id=int(rev), queryKey="all", attachments={"reviewers": 1}
            )
        except PhabricatorRevisionNotFoundException:
            return None

        # this is a timestamp
        last_modified = data["fields"]["dateModified"]
        last_modified = lmdutils.get_date_from_timestamp(last_modified)
        if (self.date - last_modified).days <= self.nweeks * 7:
            # Do not do anything if recent changes in the bug
            return False

        reviewers = data["attachments"]["reviewers"]["reviewers"]

        if not reviewers:
            return False

        for reviewer in reviewers:
            if reviewer["status"] != "accepted":
                return False
            reviewers_phid.add(reviewer["reviewerPHID"])

        value = data["fields"]["status"].get("value", "")
        if value == "changes-planned":
            # even if the patch is r+ and not published, some changes may be required
            # so with the value 'changes-planned', the dev can say it's still a wip
            return False

        if value != "published":
            return True

        return False

    def handle_attachment(self, attachment, res):
        ct = attachment["content_type"]
        c = None
        if ct == "text/x-phabricator-request":
            if "phab" not in res or res["phab"]:
                c = self.check_phab(attachment, res["reviewers_phid"])
                if c is not None:
                    res["phab"] = c

        if c is not None:
            attacher = attachment["creator"]
            if "author" in res:
                if attacher in res["author"]:
                    res["author"][attacher] += 1
                else:
                    res["author"][attacher] = 1
            else:
                res["author"] = {attacher: 1}

            if "count" in res:
                res["count"] += 1
            else:
                res["count"] = 1

    def get_patch_data(self, bugs):
        """Get patch information in bugs"""
        patterns = Bugzilla.get_landing_patterns(channels=["nightly", "autoland"])

        def comment_handler(bug, bugid, data):
            # if a comment contains a backout: don't nag
            for comment in bug["comments"]:
                comment = comment["text"].lower()
                if any(pat[0].match(comment) for pat in patterns) and (
                    "backed out" in comment or "backout" in comment
                ):
                    data[bugid]["backout"] = True

        def attachment_id_handler(attachments, bugid, data):
            for a in attachments:
                if (
                    a["content_type"] == "text/x-phabricator-request"
                    and a["is_obsolete"] == 0
                ):
                    data.append(a["id"])

        def attachment_handler(attachments, data):
            for attachment in attachments:
                bugid = str(attachment["bug_id"])
                if bugid in data:
                    data[bugid].append(attachment)
                else:
                    data[bugid] = [attachment]

        def has_blocking_dependencies(attachment):
            rev = PHAB_URL_PAT.search(
                base64.b64decode(attachment["data"]).decode("utf-8")
            ).group(1)
            try:
                revision_data = self.phab.load_revision(rev_id=int(rev))
            except PhabricatorRevisionNotFoundException:
                return None

            stack_graph = revision_data["fields"]["stackGraph"]
            current_revision_phid = revision_data["phid"]
            dependencies = stack_graph[current_revision_phid]

            for dep_phid in dependencies:
                dep_revision_data = self.phab.load_revision(rev_phid=dep_phid)
                dep_status = dep_revision_data["fields"]["status"]["value"]
                if dep_status != "published":
                    return True

            return False

        bugids = list(bugs.keys())
        data = {
            bugid: {
                "backout": False,
                "author": None,
                "count": 0,
                "has_blocking_dependencies": False,
            }
            for bugid in bugids
        }

        # Get the ids of the attachments of interest
        # to avoid to download images, videos, ...
        attachment_ids = []
        Bugzilla(
            bugids=bugids,
            attachmenthandler=attachment_id_handler,
            attachmentdata=attachment_ids,
            attachment_include_fields=["is_obsolete", "content_type", "id"],
        ).get_data().wait()

        # Once we've the ids we can get the data
        attachments_by_bug = {}
        Bugzilla(
            attachmentids=attachment_ids,
            attachmenthandler=attachment_handler,
            attachmentdata=attachments_by_bug,
            attachment_include_fields=[
                "bug_id",
                "data",
                "is_obsolete",
                "content_type",
                "id",
                "creator",
            ],
        ).get_data().wait()

        for bugid, attachments in attachments_by_bug.items():
            res = {"reviewers_phid": set()}
            for attachment in attachments:
                self.handle_attachment(attachment, res)

            if "phab" in res:
                if res["phab"]:
                    data[bugid][
                        "has_blocking_dependencies"
                    ] = has_blocking_dependencies(attachment)
                    data[bugid]["reviewers_phid"] = res["reviewers_phid"]
                    data[bugid]["author"] = res["author"]
                    data[bugid]["count"] = res["count"]

        data = {bugid: v for bugid, v in data.items() if v["author"]}

        if not data:
            return data

        Bugzilla(
            bugids=list(data.keys()),
            commenthandler=comment_handler,
            commentdata=data,
            comment_include_fields=["text"],
        ).get_data().wait()

        data = {
            bugid: v
            for bugid, v in data.items()
            if not v["backout"] and not v["has_blocking_dependencies"]
        }

        return data

    def get_bz_users(self, phids):
        if not phids:
            return {}

        try:
            data = self.phab.load_bz_account(user_phids=list(phids))
            users = {x["phid"]: x["id"] for x in data}
        except PhabricatorBzNotFoundException:
            return {}

        def handler(user, data):
            data[str(user["id"])] = user

        data = {}
        BugzillaUser(
            user_names=list(users.values()),
            include_fields=["id", "name", "nick"],
            user_handler=handler,
            user_data=data,
        ).wait()

        return {phid: data[id] for phid, id in users.items()}

    def get_bz_params(self, date):
        self.date = lmdutils.get_date_ymd(date)
        fields = ["flags", "depends_on"]
        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "attachment.ispatch",
            "n2": 1,
            "f2": "attachments.isobsolete",
            "f3": "attachments.mimetype",
            "o3": "anywordssubstr",
            "v3": "text/x-phabricator-request",
            "f4": "creation_ts",
            "o4": "greaterthan",
            "v4": f"-{self.nyears}y",
            "f5": "days_elapsed",
            "o5": "greaterthaneq",
            "v5": self.nweeks * 7,
            "n6": 1,
            "f6": "longdesc",
            "o6": "casesubstring",
            "v6": "which didn't land and no activity in this bug for",
            "f7": "status_whiteboard",
            "o7": "notsubstring",
            "v7": "[reminder-test ",
        }

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(NotLanded, self).get_bugs(date=date, bug_ids=bug_ids)
        bugs = self.filter_bugs(bugs)
        bugs_patch = self.get_patch_data(bugs)
        res = {}

        reviewers_phid = set()
        bug_assignee_map = {}
        for bugid, data in bugs_patch.items():
            reviewers_phid |= data["reviewers_phid"]
            assignee = bugs[bugid]["assigned_to"]
            if not assignee:
                assignee = max(data["author"], key=data["author"].get)
                bug_assignee_map[bugid] = assignee

        bz_reviewers = self.get_bz_users(reviewers_phid)
        all_reviewers = set(bz_reviewers.keys())

        for bugid, data in bugs_patch.items():
            res[bugid] = d = bugs[bugid]
            self.extra_ni[bugid] = data["count"]
            assignee = d["assigned_to"]

            if not assignee:
                user_details = bz_reviewers[assignee]
                assignee = user_details["id"]
                nickname = user_details["nick"]

            if not assignee:
                continue

            self.add_auto_ni(bugid, {"mail": assignee, "nickname": nickname})

            common = all_reviewers["name"] & data["reviewers_phid"]
            if common:
                reviewer = random.choice(list(common))
                self.add_auto_ni(
                    bugid, {"mail": bz_reviewers[reviewer], "nickname": None}
                )

        return res


if __name__ == "__main__":
    NotLanded().run()
