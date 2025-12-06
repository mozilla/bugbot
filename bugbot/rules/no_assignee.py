# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import functools
import re

from Levenshtein import jaro_winkler
from libmozdata import hgmozilla
from libmozdata.bugzilla import Bugzilla, BugzillaUser
from libmozdata.connection import Query

from bugbot import utils
from bugbot.bzcleaner import BzCleaner

HG_MAIL = re.compile(r"^([^<]*)<([^>]+)>$")
ALNUM = re.compile(r"[\W_]+", re.UNICODE)


class NoAssignee(BzCleaner):
    def __init__(self):
        super(NoAssignee, self).__init__()
        self.hgdata = {}
        self.autofix_assignee = {}

    def description(self):
        return "Bugs with no assignees and a patch which landed in m-c"

    def columns(self):
        return ["id", "summary", "email"]

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)
        reporters = self.get_config("reporter_exception", default=[])
        reporters = ",".join(reporters)
        regexp = r"http[s]?://hg\.mozilla\.org/(releases/)?mozilla-[^/]+/rev/[0-9a-f]+"
        bot = utils.get_config("common", "bot_bz_mail")[0]
        params = {
            "resolution": "FIXED",
            "bug_status": ["RESOLVED", "VERIFIED"],
            "keywords": "meta",
            "keywords_type": "nowords",
            "f1": "longdesc",
            "o1": "regexp",
            "v1": regexp,
            "f2": "resolution",
            "o2": "changedafter",
            "v2": start_date,
            "f3": "resolution",
            "o3": "changedbefore",
            "v3": end_date,
            "n4": 1,
            "f4": "assigned_to",
            "o4": "changedby",
            "v4": bot,
        }

        if reporters:
            params.update({"f5": "reporter", "o5": "nowordssubstr", "v5": reporters})

        utils.get_empty_assignees(params)

        return params

    def is_patch(self, attachment):
        """Check if the attachment is a patch or not."""
        if attachment["is_obsolete"] == 1:
            return False
        if attachment["is_patch"] == 1:
            return True
        if attachment["content_type"] in [
            "text/x-phabricator-request",
            "text/x-review-board-request",
        ]:
            return True

        return False

    def get_revisions(self, bugs):
        """Get the revisions from the hg.m.o urls in the bug comments"""
        nightly_pats = Bugzilla.get_landing_patterns(channels=["nightly"])

        def comment_handler(bug, bugid, data):
            commenters = data[bugid]["commenters"]
            for comment in bug["comments"]:
                commenter = comment["author"]
                if commenter in commenters:
                    commenters[commenter] += 1
                else:
                    commenters[commenter] = 1

            r = Bugzilla.get_landing_comments(bug["comments"], [], nightly_pats)
            data[bugid]["revisions"] = [i["revision"] for i in r]

        def attachment_handler(attachments, bugid, data):
            for attachment in attachments:
                if self.is_patch(attachment):
                    data[bugid]["creators"].add(attachment["creator"])

        bugids = list(bugs.keys())
        revisions = {
            bugid: {"revisions": [], "creators": set(), "commenters": {}}
            for bugid in bugids
        }
        Bugzilla(
            bugids=bugids,
            commenthandler=comment_handler,
            commentdata=revisions,
            comment_include_fields=["text", "author"],
            attachmenthandler=attachment_handler,
            attachment_include_fields=[
                "creator",
                "is_obsolete",
                "is_patch",
                "content_type",
            ],
            attachmentdata=revisions,
        ).get_data().wait()

        return revisions

    def get_user_info(self, bzdata):
        """Get the user info from Bugzilla to have his real name."""

        def handler(user, data):
            data[user["name"]] = user["real_name"]

        users = set()
        for info in bzdata.values():
            users |= info["creators"]
            users |= set(info["commenters"].keys())

        data = {}

        if users:
            BugzillaUser(
                user_names=list(users),
                user_handler=handler,
                user_data=data,
                include_fields=["name", "real_name"],
            ).wait()

        return data

    def clean_name(self, name):
        """Get the different parts of the name with letters only"""
        res = ""
        for c in name:
            res += c if c.isalpha() else " "
        res = res.split(" ")
        res = filter(None, res)
        res = map(lambda s: s.lower(), res)
        res = set(res)

        if len(res) >= 2:
            return res

        return set()

    def clean_mail(self, mail):
        return ALNUM.sub("", mail)

    def mk_possible_mails(self, names):
        # Foo Bar will probably choose fbar@ or barf@ or foob@...
        # Generate the different possibilities
        res = set()
        if len(names) != 2:
            return res

        names = list(names)
        first = names[0]
        second = names[1]

        for i in range(1, len(first)):
            res.add(first[:i] + second)
            res.add(second + first[:i])

        for i in range(1, len(second)):
            res.add(second[:i] + first)
            res.add(first + second[:i])

        return res

    def find_assignee(self, bz_patchers, hg_patchers, bz_commenters, bz_info):
        """Find a potential assignee.
        If an email is common between patchers (people who made patches on bugzilla)
        and hg patchers then return this email.
        If "Foo Bar [:foobar]" made a patch and his hg name is "Bar Foo" return the
        corresponding Bugzilla email.
        """

        if not bz_patchers:
            # we've no patch in the bug
            # so try to find an assignee in the commenters
            bz_patchers = set(bz_commenters.keys())

        potential = set()
        hg_patchers_mail = set(mail for _, mail in hg_patchers)
        common = bz_patchers & hg_patchers_mail
        if len(common) == 1:
            # there is a common email between Bz patchers & Hg email
            return list(common)[0]

        # here we try to find at least 2 common elements
        # in the creator real name and in the hg author name
        hg_patchers_name = [self.clean_name(name) for name, _ in hg_patchers]
        for bz_patcher in bz_patchers:
            if bz_patcher not in bz_info:
                continue
            real_name = self.clean_name(bz_info[bz_patcher])
            for name in hg_patchers_name:
                if len(name & real_name) >= 2:
                    potential.add(bz_patcher)

        # try to find similarities between email and name
        for name in hg_patchers_name:
            possible_mail_parts = self.mk_possible_mails(name)
            for bz_patcher in bz_patchers:
                _bz_patcher = self.clean_mail(bz_patcher)
                for part in possible_mail_parts:
                    if len(part) >= 5 and part in _bz_patcher:
                        potential.add(bz_patcher)

        # try to find similarities between email in using Jaro-Winkler metric
        for b in bz_patchers:
            _b = self.clean_mail(b)
            for h in hg_patchers_mail:
                _h = self.clean_mail(h)
                d = 1 - jaro_winkler(_b, _h)
                if d <= 0.2:
                    potential.add(b)

        if potential:
            potential = list(potential)
            if len(potential) == 1:
                return potential[0]
            return max(
                ((p, bz_commenters.get(p, 0)) for p in potential), key=lambda x: x[1]
            )[0]

        return None

    def set_autofixable(self, bzdata, user_info):
        """Set the bugs where an easy assignee can be set."""
        for bugid, info in bzdata.items():
            if bugid not in self.hgdata:
                continue
            creators = info["creators"]
            commenters = info["commenters"]
            patchers = self.hgdata[bugid]
            self.hgdata[bugid] = self.find_assignee(
                creators, patchers, commenters, user_info
            )

    def filter_from_hg(self, bzdata, user_info):
        """Get the bugs where an associated revision contains
        the bug id in the description"""

        def handler_rev(bugid, json, data):
            if bugid in json["desc"] and not utils.is_backout(json):
                user = json["user"]
                if bugid not in data:
                    data[bugid] = set()
                m = HG_MAIL.match(user)
                if m:
                    hgname = m.group(1).strip()
                    hgmail = m.group(2).strip()
                    data[bugid].add((hgname, hgmail))

        url = hgmozilla.Revision.get_url("nightly")
        queries = []
        for bugid, info in bzdata.items():
            hdler = functools.partial(handler_rev, bugid)
            for rev in info["revisions"]:
                queries.append(Query(url, {"node": rev}, hdler, self.hgdata))

        if queries:
            hgmozilla.Revision(queries=queries).wait()

        self.set_autofixable(bzdata, user_info)

        return self.hgdata

    def get_autofix_change(self):
        return self.autofix_assignee

    def get_db_extra(self):
        return {
            bugid: v["assigned_to"] for bugid, v in self.get_autofix_change().items()
        }

    def get_bugs(self, date="today", bug_ids=[]):
        bugs = super(NoAssignee, self).get_bugs(date=date, bug_ids=bug_ids)
        bzdata = self.get_revisions(bugs)
        user_info = self.get_user_info(bzdata)

        _bugs = self.filter_from_hg(bzdata, user_info)
        res = {}
        for bugid, email in _bugs.items():
            if email:
                res[bugid] = {
                    "id": bugid,
                    "email": email,
                    "summary": bugs[bugid]["summary"],
                }
                self.autofix_assignee[bugid] = {"assigned_to": email}

        return res


if __name__ == "__main__":
    NoAssignee().run()
