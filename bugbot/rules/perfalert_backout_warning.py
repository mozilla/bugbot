# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import collections

import numpy
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.user_activity import UserActivity, UserStatus

# The number of business days the author is given to acknowledge a performance
# regression, starting from the day the performance sheriff needinfos them. A
# backout may be requested at the end of the last day.
ACKNOWLEDGEMENT_DEADLINE = 3

# A sentence that is part of the needinfo comment. It is used to avoid warning
# about the same bug twice.
COMMENT_MARKER = "a backout of your patch may be requested"


class PerfAlertBackoutWarning(BzCleaner):
    def __init__(self, ndays: int = ACKNOWLEDGEMENT_DEADLINE - 1):
        super().__init__()
        # The number of business days that must have passed since the sheriff
        # needinfoed the author, i.e., we warn one business day before the
        # acknowledgement deadline expires.
        self.ndays = ndays
        self.extra_ni = {"deadline": ACKNOWLEDGEMENT_DEADLINE}
        self.private_regressor_ids: set[str] = set()

    def description(self):
        return "PerfAlert regressions with no author response one business day before a backout is requested"

    def handle_bug(self, bug, data):
        if len(bug["regressed_by"]) != 1:
            # either we don't have access to the regressor,
            # or there's more than one, either way leave things alone
            return

        data[str(bug["id"])] = {
            "creator": bug["creator"],
            "regressor_id": bug["regressed_by"][0],
            "needinfo_flags": list(utils.get_needinfo(bug)),
        }

        return bug

    def get_bz_params(self, date):
        fields = [
            "id",
            "creator",
            "regressed_by",
            "flags",
        ]

        # Find all open bugs that have perf-alert and regression in their
        # keywords, and that have a needinfo pending.
        params = {
            "include_fields": fields,
            "f1": "regressed_by",
            "o1": "isnotempty",
            "f2": "keywords",
            "o2": "allwords",
            "v2": ["regression", "perf-alert"],
            "f3": "keywords",
            "o3": "nowords",
            "v3": "backlog-deferred",
            "f4": "flagtypes.name",
            "o4": "equals",
            "v4": "needinfo?",
            # Exclude the bugs that we already warned about.
            "n5": 1,
            "f5": "longdesc",
            "o5": "casesubstring",
            "v5": COMMENT_MARKER,
            "status": ["UNCONFIRMED", "NEW", "REOPENED"],
            "resolution": ["---"],
        }

        return params

    def retrieve_regressors(self, bugs):
        regressor_to_bugs = collections.defaultdict(list)
        for bug in bugs.values():
            regressor_to_bugs[bug["regressor_id"]].append(bug)

        def bug_handler(regressor_bug):
            if regressor_bug.get("groups"):
                regressor_bug_id = str(regressor_bug["id"])
                self.private_regressor_ids.add(regressor_bug_id)

            for bug in regressor_to_bugs[regressor_bug["id"]]:
                bug["regressor_author_email"] = regressor_bug["assigned_to"]
                bug["regressor_author_nickname"] = regressor_bug["assigned_to_detail"][
                    "nick"
                ]

        Bugzilla(
            bugids={bug["regressor_id"] for bug in bugs.values()},
            bughandler=bug_handler,
            include_fields=["id", "assigned_to", "groups"],
        ).get_data().wait()

    @staticmethod
    def get_needinfo_date(needinfo_flags, author_email):
        """Get the date of the first needinfo pending on the regressor author.

        Needinfo requests made by the bot are ignored: only a request coming
        from a performance sheriff starts the acknowledgement countdown, and
        this also prevents our own warning from restarting it.

        Args:
            needinfo_flags: the pending needinfo flags of the bug.
            author_email: the email of the regressor author.

        Returns:
            The date of the oldest matching needinfo, or `None` if the author
            has no needinfo pending.
        """
        bot_emails = set(utils.get_config("common", "bot_bz_mail"))
        dates = [
            lmdutils.get_date_ymd(flag["creation_date"]).date()
            for flag in needinfo_flags
            if flag.get("requestee") == author_email
            and flag["setter"] not in bot_emails
        ]

        return min(dates) if dates else None

    def filter_bugs(self, bugs):
        # TODO: Attempt to needinfo the triage owner instead of ignoring the bugs
        # Exclude bugs whose regressor author is nobody.
        for bug in list(bugs.values()):
            if utils.is_no_assignee(bug.get("regressor_author_email", "")):
                logger.warning(
                    "Bug {}, regressor of bug {}, doesn't have an author".format(
                        bug["regressor_id"], bug["id"]
                    )
                )
                del bugs[bug["id"]]

        # Exclude bugs where the deadline the sheriff gave to the author does
        # not expire at the end of the next business day.
        today = lmdutils.get_date("today")
        for bug_id, bug in list(bugs.items()):
            needinfo_date = self.get_needinfo_date(
                bug["needinfo_flags"], bug["regressor_author_email"]
            )
            if (
                needinfo_date is None
                or numpy.busday_count(needinfo_date, today) != self.ndays
            ):
                del bugs[bug_id]

        # Exclude bugs where the author already responded: bugs where the author
        # has engaged are handled by the inactive regression rule.
        bugs = {
            bug_id: bug
            for bug_id, bug in bugs.items()
            if bug["creator"] != bug["regressor_author_email"]
        }

        def comment_handler(bug, bug_id):
            bug_id = str(bug_id)
            if any(
                comment["creator"] == bugs[bug_id]["regressor_author_email"]
                for comment in bug["comments"]
            ):
                del bugs[bug_id]

        if bugs:
            Bugzilla(
                bugids=self.get_list_bugs(bugs),
                commenthandler=comment_handler,
                comment_include_fields=["creator"],
            ).get_data().wait()

        # Exclude bugs where the regressor author is inactive or blocked needinfo.
        # TODO: We can drop this when https://github.com/mozilla/bugbot/issues/1465 is implemented.
        if bugs:
            users_info = UserActivity(
                include_fields=["groups", "requests"]
            ).check_users(
                set(bug["regressor_author_email"] for bug in bugs.values()),
                keep_active=True,
                fetch_employee_info=True,
            )

            for bug_id, bug in list(bugs.items()):
                user_info = users_info[bug["regressor_author_email"]]
                if (
                    user_info["status"] != UserStatus.ACTIVE
                    or user_info["requests"]["needinfo"]["blocked"]
                ):
                    del bugs[bug_id]

        return bugs

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def get_extra_for_template(self):
        return self.extra_ni

    def set_autofix(self, bugs):
        for bugid, info in bugs.items():
            self.extra_ni[bugid] = {"regressor_id": str(info["regressor_id"])}
            self.add_auto_ni(
                bugid,
                {
                    "mail": info["regressor_author_email"],
                    "nickname": info["regressor_author_nickname"],
                },
            )

    def get_bugs(self, *args, **kwargs):
        bugs = super().get_bugs(*args, **kwargs)
        self.retrieve_regressors(bugs)
        bugs = self.filter_bugs(bugs)
        self.set_autofix(bugs)
        return bugs

    def set_needinfo(self):
        res = super().set_needinfo()
        for bug_id, needinfo_action in res.items():
            needinfo_action["comment"]["is_private"] = (
                bug_id in self.private_regressor_ids
            )

        return res


if __name__ == "__main__":
    PerfAlertBackoutWarning().run()
