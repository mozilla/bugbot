# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import re

import requests
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla, BugzillaUser

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner

PHAB_URL_PAT = re.compile(r"https://phabricator\.services\.mozilla\.com/D([0-9]+)")
PHAB_API = "https://phabricator.services.mozilla.com/api/differential.revision.search"


class NotLanded(BzCleaner):
    def __init__(self):
        super(NotLanded, self).__init__()
        self.nweeks = utils.get_config(self.name(), "number_of_weeks", 2)
        self.nyears = utils.get_config(self.name(), "number_of_years", 2)
        self.phab_token = utils.get_login_info()["phab_api_key"]
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

    def check_phab(self, attachment):
        """Check if the patch in Phabricator has been r+
        """
        if attachment["is_obsolete"] == 1:
            return None

        phab_url = base64.b64decode(attachment["data"]).decode("utf-8")

        # extract the revision
        rev = PHAB_URL_PAT.search(phab_url).group(1)
        r = requests.post(
            PHAB_API,
            data={
                "api.token": self.phab_token,
                "queryKey": "all",
                "constraints[ids][0]": rev,
                "attachments[reviewers]": 1,
            },
        )
        r.raise_for_status()
        data = r.json()["result"]["data"][0]

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
                c = self.check_phab(attachment)
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
        """Get patch information in bugs
        """
        nightly_pat = Bugzilla.get_landing_patterns(channels=["nightly"])[0][0]

        def comment_handler(bug, bugid, data):
            # if a comment contains a backout: don't nag
            for comment in bug["comments"]:
                comment = comment["text"].lower()
                if nightly_pat.match(comment) and (
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

        bugids = list(bugs.keys())
        data = {
            bugid: {"backout": False, "author": None, "count": 0} for bugid in bugids
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
            res = {}
            for attachment in attachments:
                self.handle_attachment(attachment, res)

            if "phab" in res:
                if res["phab"]:
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

        data = {bugid: v for bugid, v in data.items() if not v["backout"]}

        return data

    def get_nicks(self, nicknames):
        def handler(user, data):
            data[user["name"]] = user["nick"]

        users = set(nicknames.values())
        data = {}
        if users:
            BugzillaUser(
                user_names=list(users),
                include_fields=["name", "nick"],
                user_handler=handler,
                user_data=data,
            ).wait()

        for bugid, name in nicknames.items():
            nicknames[bugid] = (name, data[name])

        return nicknames

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
        }

        return params

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(NotLanded, self).get_bugs(date=date, bug_ids=bug_ids)
        bugs = self.filter_bugs(bugs)
        bugs_patch = self.get_patch_data(bugs)
        res = {}
        nicknames = {}
        for bugid, data in bugs_patch.items():
            res[bugid] = d = bugs[bugid]
            self.extra_ni[bugid] = data["count"]
            assignee = d["assigned_to"]
            nickname = d["nickname"]
            if not assignee:
                assignee = max(data["author"], key=data["author"].get)
                nicknames[bugid] = assignee
            else:
                self.add_auto_ni(bugid, {"mail": assignee, "nickname": nickname})

        nicknames = self.get_nicks(nicknames)
        for bugid, (name, nick) in nicknames.items():
            self.add_auto_ni(bugid, {"mail": name, "nickname": nick})

        return res


if __name__ == "__main__":
    NotLanded().run()
