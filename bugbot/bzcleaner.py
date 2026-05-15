# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# mypy: disallow-untyped-defs

import argparse
import logging
import os
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, cast

from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader, Template
from libmozdata import config
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla

from bugbot import db, logger, logger_extra, mail, utils
from bugbot.cache import Cache
from bugbot.nag_me import Nag

BzParams = dict[str, str | int | list[str] | list[int]]
EmailData = list[Any | tuple[Any, ...] | dict[Any, Any]]
Bug = Mapping[str, Any]


class TooManyChangesError(Exception):
    """Exception raised when the rule is trying to apply too many changes"""

    def __init__(
        self, bugs: dict[str, Bug], changes: dict[str, Any], max_changes: int
    ) -> None:
        message = f"The rule has been aborted because it was attempting to apply changes on {len(changes)} bugs. Max is {max_changes}."
        super().__init__(message)
        self.bugs = bugs
        self.changes = changes


class SilentBugzilla(Bugzilla):
    """Same as Bugzilla but using an account that does not trigger bugmail"""

    TOKEN = config.get("Bugzilla", "nomail-token", "")


class BzCleaner(object):
    """
    Attributes:
        no_bugmail: If `True`, a token for an account that does not trigger
            bugmail will be used when performing `PUT` actions on Bugzilla.
        normal_changes_max: The maximum number of changes that could be made in
            a normal situation. If exceeded, the rule will fail.
    """

    no_bugmail: bool = False
    normal_changes_max: int = 50

    def __init__(self) -> None:
        super(BzCleaner, self).__init__()
        self._set_rule_name()
        self.apply_autofix: bool = True
        self.has_autofix: bool = False
        self.autofix_changes: dict[str, Any] = {}
        self.quota_actions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.no_manager: set[str] = set()
        self.auto_needinfo: dict[str, dict[str, Any]] = {}
        self.extra_ni: dict[str, Any] = {}
        self.has_flags: bool = False
        self.cache = Cache(self.name(), self.max_days_in_cache())
        self.test_mode = utils.get_config("common", "test", False)
        self.versions: Any = None

    def _set_rule_name(self) -> None:
        module = sys.modules[self.__class__.__module__]
        module_file = module.__file__
        assert module_file is not None
        base = os.path.dirname(__file__)
        rules = os.path.join(base, "rules")
        self.__rule_path__: str = os.path.relpath(module_file, rules)
        name = os.path.basename(module_file)
        name = os.path.splitext(name)[0]
        self.__rule_name__: str = name

    def init_versions(self) -> bool:
        self.versions = utils.get_checked_versions()
        return bool(self.versions)

    def max_days_in_cache(self) -> int:
        """Get the max number of days the data must be kept in cache"""
        return self.get_config("max_days_in_cache", -1)

    def description(self) -> str:
        """Get the description for the help"""
        return ""

    def name(self) -> str:
        """Get the rule name"""
        return self.__rule_name__

    def get_rule_path(self) -> str:
        """Get the rule path"""
        return self.__rule_path__

    def needinfo_template_name(self) -> str:
        """Get the txt template filename"""
        return self.name() + "_needinfo.txt"

    def template(self) -> str:
        """Get the html template filename"""
        return self.name() + ".html"

    def subject(self) -> str:
        """Get the partial email subject"""
        return self.description()

    def get_email_subject(self, date: str | None) -> str:
        """Get the email subject with a date or not"""
        af = "[autofix]" if self.has_autofix else ""
        if date:
            return "[bugbot]{} {} for the {}".format(af, self.subject(), date)
        return "[bugbot]{} {}".format(af, self.subject())

    def ignore_date(self) -> bool:
        """Should we ignore the date ?"""
        return False

    def must_run(self, date: datetime) -> bool:
        """Check if the rule must run for this date"""
        days = self.get_config("must_run", None)
        if not days:
            return True
        weekday = date.weekday()
        week = utils.get_weekdays()
        for day in days:
            if week[day] == weekday:
                return True
        return False

    def has_enough_data(self) -> bool:
        """Check if the rule has enough data to run"""
        if self.versions is None:
            # init_versions() has never been called
            return True
        return bool(self.versions)

    def filter_no_nag_keyword(self) -> bool:
        """If True, then remove the bugs with [no-nag] in whiteboard from the bug list"""
        return True

    def add_no_manager(self, bugid: str | int) -> None:
        self.no_manager.add(str(bugid))

    def has_assignee(self) -> bool:
        return False

    def has_needinfo(self) -> bool:
        return False

    def get_mail_to_auto_ni(self, bug: Bug) -> dict[str, Any] | None:
        return None

    def all_include_fields(self) -> bool:
        return False

    def get_max_ni(self) -> int:
        return -1

    def get_max_actions(self) -> int:
        return -1

    def exclude_no_action_bugs(self) -> bool:
        """
        If `True`, then remove bugs that have no actions from the email (e.g.,
        needinfo got ignored due to exceeding the limit). This is applied only
        when using the `add_prioritized_action()` method.

        Returning `False` could be useful if we want to list all actions the rule
        would do if it had no limits.
        """
        return True

    def ignore_meta(self) -> bool:
        return False

    def columns(self) -> list[str]:
        """The fields to get for the columns in email report"""
        return ["id", "summary"]

    def sort_columns(self) -> str | None:
        """Returns the key to sort columns"""
        return None

    def get_dates(self, date_str: str) -> tuple[datetime, datetime]:
        """Get the dates for the bugzilla query (changedafter and changedbefore fields)"""
        date = lmdutils.get_date_ymd(date_str)
        if date is None:
            raise ValueError(f"Invalid date string {date_str}")
        lookup = self.get_config("days_lookup", 7)
        start_date = date - relativedelta(days=lookup)
        end_date = date + relativedelta(days=1)

        return start_date, end_date

    def get_extra_for_template(self) -> Mapping[str, Any]:
        """Get extra data to put in the template"""
        return {}

    def get_extra_for_needinfo_template(self) -> Mapping[str, Any]:
        """Get extra data to put in the needinfo template"""
        return {}

    def get_config(self, entry: str, default: Any = None) -> Any:
        return utils.get_config(self.name(), entry, default=default)

    def get_bz_params(self, date: str) -> BzParams:
        """Get the Bugzilla parameters for the search query"""
        return {}

    def get_data(self) -> dict[str, Any]:
        """Get the data structure to use in the bughandler"""
        return {}

    def get_summary(self, bug: Bug) -> str:
        return "..." if bug["groups"] else bug["summary"]

    def get_cc_emails(self, data: EmailData) -> list[str]:
        return []

    def has_default_products(self) -> bool:
        return True

    def has_product_component(self) -> bool:
        return False

    def has_access_to_sec_bugs(self) -> bool:
        return self.get_config("sec", True)

    def handle_bug(self, bug: Bug, data: dict[str, Any]) -> Bug | None:
        """Implement this function to get all the bugs from the query"""
        return bug

    def get_db_extra(self) -> Mapping[str, Any]:
        """Get extra information required for db insertion"""
        return {
            bugid: ni_mail
            for ni_mail, v in self.auto_needinfo.items()
            for bugid in v["bugids"]
        }

    def get_auto_ni_skiplist(self) -> set[str]:
        """Return a set of email addresses that should never be needinfoed"""
        return set(self.get_config("needinfo_skiplist", default=[]))

    def add_auto_ni(self, bugid: str | int, data: dict[str, Any] | None) -> bool:
        if not data:
            return False

        ni_mail = data["mail"]
        if ni_mail in self.get_auto_ni_skiplist() or utils.is_no_assignee(ni_mail):
            return False
        if ni_mail in self.auto_needinfo:
            max_ni = self.get_max_ni()
            info = self.auto_needinfo[ni_mail]
            if max_ni > 0 and len(info["bugids"]) >= max_ni:
                return False
            info["bugids"].append(str(bugid))
        else:
            self.auto_needinfo[ni_mail] = {
                "nickname": data["nickname"],
                "bugids": [str(bugid)],
            }
        return True

    def add_prioritized_action(
        self,
        bug: Bug,
        quota_name: str,
        needinfo: dict[str, Any] | None = None,
        autofix: dict[str, Any] | None = None,
    ) -> None:
        """
        - `quota_name` is the key used to apply the limits, e.g., triage owner, team, or component
        """
        assert needinfo or autofix

        # Avoid having more than one ni from our bot
        if needinfo and self.has_bot_set_ni(bug):
            needinfo = autofix = None

        action = {
            "bug": bug,
            "needinfo": needinfo,
            "autofix": autofix,
        }

        self.quota_actions[quota_name].append(action)

    def get_bug_sort_key(self, bug: Bug) -> str | None:
        return None

    def _populate_prioritized_actions(self, bugs: dict[str, Bug]) -> dict[str, Any]:
        max_actions = self.get_max_actions()
        max_ni = self.get_max_ni()
        exclude_no_action_bugs = (
            len(self.quota_actions) > 0 and self.exclude_no_action_bugs()
        )
        bugs_with_action = set()

        for actions in self.quota_actions.values():
            if len(actions) > max_ni or len(actions) > max_actions:
                actions.sort(
                    key=lambda action: (
                        not action["needinfo"],
                        self.get_bug_sort_key(action["bug"]),
                    )
                )

            ni_count = 0
            actions_count = 0
            for action in actions:
                bugid = str(action["bug"]["id"])
                if max_actions > 0 and actions_count >= max_actions:
                    break

                if action["needinfo"]:
                    if max_ni > 0 and ni_count >= max_ni:
                        continue

                    ok = self.add_auto_ni(bugid, action["needinfo"])
                    if not ok:
                        # If we can't needinfo, we do not add the autofix
                        continue

                    if "extra" in action["needinfo"]:
                        self.extra_ni[bugid] = action["needinfo"]["extra"]

                    bugs_with_action.add(bugid)
                    ni_count += 1

                if action["autofix"]:
                    assert bugid not in self.autofix_changes
                    self.autofix_changes[bugid] = action["autofix"]
                    bugs_with_action.add(bugid)

                if action["autofix"] or action["needinfo"]:
                    actions_count += 1

        if exclude_no_action_bugs:
            bugs = {id: bug for id, bug in bugs.items() if id in bugs_with_action}

        return bugs

    def bughandler(self, bug: Bug, data: dict[str, Any]) -> None:
        """bug handler for the Bugzilla query"""
        if bug["id"] in self.cache:
            return

        if self.handle_bug(bug, data) is None:
            return

        bugid = str(bug["id"])
        res: dict[str, Any] = {"id": bugid}

        auto_ni = self.get_mail_to_auto_ni(bug)
        self.add_auto_ni(bugid, auto_ni)

        res["summary"] = self.get_summary(bug)

        if self.has_assignee():
            res["assignee"] = utils.get_name_from_user_detail(bug["assigned_to_detail"])

        if self.has_needinfo():
            s = set()
            for flag in utils.get_needinfo(bug):
                s.add(flag["requestee"])
            res["needinfos"] = sorted(s)

        if self.has_product_component():
            for k in ["product", "component"]:
                res[k] = bug[k]

        if isinstance(self, Nag):
            bug = self.set_people_to_nag(bug, res)
            if not bug:
                return

        if bugid in data:
            data[bugid].update(res)
        else:
            data[bugid] = res

    def get_products(self) -> list[str]:
        return list(
            (
                set(self.get_config("products"))
                | set(self.get_config("additional_products", []))
            )
            - set(self.get_config("exclude_products", []))
        )

    def amend_bzparams(self, params: dict[str, Any], bug_ids: list[int]) -> None:
        """Amend the Bugzilla params"""
        if not self.all_include_fields():
            if "include_fields" in params:
                fields = params["include_fields"]
                if isinstance(fields, list):
                    if "id" not in fields:
                        fields.append("id")
                elif isinstance(fields, str):
                    if fields != "id":
                        params["include_fields"] = [fields, "id"]
                else:
                    params["include_fields"] = [fields, "id"]
            else:
                params["include_fields"] = ["id"]

            params["include_fields"] += ["summary", "groups"]

            if self.has_assignee() and "assigned_to" not in params["include_fields"]:
                params["include_fields"].append("assigned_to")

            if self.has_product_component():
                if "product" not in params["include_fields"]:
                    params["include_fields"].append("product")
                if "component" not in params["include_fields"]:
                    params["include_fields"].append("component")

            if self.has_needinfo() and "flags" not in params["include_fields"]:
                params["include_fields"].append("flags")

        if bug_ids:
            params["bug_id"] = bug_ids

        if self.filter_no_nag_keyword():
            n = utils.get_last_field_num(params)
            params.update(
                {
                    "f" + n: "status_whiteboard",
                    "o" + n: "notsubstring",
                    "v" + n: "[no-nag]",
                }
            )

        if self.ignore_meta():
            n = utils.get_last_field_num(params)
            params.update({"f" + n: "keywords", "o" + n: "nowords", "v" + n: "meta"})

        if self.has_default_products():
            params["product"] = self.get_products()

        if not self.has_access_to_sec_bugs():
            n = utils.get_last_field_num(params)
            params.update({"f" + n: "bug_group", "o" + n: "isempty"})

        self.has_flags = "flags" in params.get("include_fields", [])

    def get_bugs(
        self,
        date: str = "today",
        bug_ids: list[int] = [],
        chunk_size: int | None = None,
    ) -> dict[str, Any]:
        """Get the bugs"""
        bugs = self.get_data()
        params = self.get_bz_params(date)
        self.amend_bzparams(params, bug_ids)
        self.query_url = utils.get_bz_search_url(params)

        if isinstance(self, Nag):
            self.query_params: dict = params

        old_CHUNK_SIZE = Bugzilla.BUGZILLA_CHUNK_SIZE
        try:
            if chunk_size:
                Bugzilla.BUGZILLA_CHUNK_SIZE = chunk_size

            Bugzilla(
                params,
                bughandler=self.bughandler,
                bugdata=bugs,
                timeout=self.get_config("bz_query_timeout"),
            ).get_data().wait()
        finally:
            Bugzilla.BUGZILLA_CHUNK_SIZE = old_CHUNK_SIZE

        self.get_comments(bugs)

        return bugs

    def commenthandler(self, bug: Bug, bugid: str | int, data: dict[str, Any]) -> None:
        return

    def _commenthandler(self, bug: Bug, bugid: str | int, data: dict[str, Any]) -> None:
        comments = bug["comments"]
        bugid = str(bugid)
        if self.has_last_comment_time():
            if comments:
                data[bugid]["last_comment"] = utils.get_human_lag(comments[-1]["time"])
            else:
                data[bugid]["last_comment"] = ""

        self.commenthandler(bug, bugid, data)

    def get_comments(self, bugs: dict[str, Any]) -> dict[str, Any]:
        """Get the bugs comments"""
        if self.has_last_comment_time():
            bugids = self.get_list_bugs(bugs)
            Bugzilla(
                bugids=bugids, commenthandler=self._commenthandler, commentdata=bugs
            ).get_data().wait()
        return bugs

    def has_last_comment_time(self) -> bool:
        return False

    def get_list_bugs(self, bugs: dict[str, Any]) -> list[str]:
        return [x["id"] for x in bugs.values()]

    def get_documentation(self) -> str:
        return "For more information, please visit [BugBot documentation](https://wiki.mozilla.org/BugBot#{}).".format(
            self.get_rule_path().replace("/", ".2F")
        )

    def has_bot_set_ni(self, bug: Bug) -> bool:
        if not self.has_flags:
            raise Exception
        return utils.has_bot_set_ni(bug)

    def set_needinfo(self) -> Mapping[str, Mapping[str, Any]]:
        if not self.auto_needinfo:
            return {}

        template = self.get_needinfo_template()
        res: dict[str, dict[str, Any]] = {}

        doc = self.get_documentation()

        for ni_mail, info in self.auto_needinfo.items():
            nick = info["nickname"]
            for bugid in info["bugids"]:
                data: dict[str, Any] = {
                    "comment": {"body": ""},
                    "flags": [
                        {
                            "name": "needinfo",
                            "requestee": ni_mail,
                            "status": "?",
                            "new": "true",
                        }
                    ],
                }

                comment = None
                if nick:
                    comment = template.render(
                        nickname=nick,
                        extra=self.get_extra_for_needinfo_template(),
                        plural=utils.plural,
                        bugid=bugid,
                        documentation=doc,
                    )
                    comment = comment.strip() + "\n"
                    data["comment"]["body"] = comment

                if bugid not in res:
                    res[bugid] = data
                else:
                    res[bugid]["flags"] += data["flags"]
                    if comment:
                        res[bugid]["comment"]["body"] = comment

        return res

    def get_needinfo_template(self) -> Template:
        """Get a template to render needinfo comment body"""

        template_name = self.needinfo_template_name()
        assert bool(template_name)
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template(template_name)

        return template

    def has_individual_autofix(self, changes: dict[Any, Any]) -> bool:
        # check if we have a dictionary with bug numbers as keys
        # return True if all the keys are bug number
        # (which means that each bug has its own autofix)
        return bool(changes) and all(
            isinstance(bugid, int) or bugid.isdigit() for bugid in changes
        )

    def get_autofix_change(self) -> dict[str, Any]:
        """Get the change to do to autofix the bugs"""
        return self.autofix_changes

    def autofix(self, bugs: dict[str, Bug]) -> dict[str, Bug]:
        """Autofix the bugs according to what is returned by get_autofix_change"""
        ni_changes = self.set_needinfo()
        change = self.get_autofix_change()

        if not ni_changes and not change:
            return bugs

        self.has_autofix = True
        new_changes: dict[str, Any] = {}
        bugids: Iterable[str]
        if not self.has_individual_autofix(change):
            bugids = self.get_list_bugs(bugs)
            for bugid in bugids:
                mrg = utils.merge_bz_changes(change, ni_changes.get(bugid, {}))
                if mrg:
                    new_changes[bugid] = mrg
        else:
            change = {str(k): v for k, v in change.items()}
            bugids = set(change.keys()) | set(ni_changes.keys())
            for bugid in bugids:
                mrg = utils.merge_bz_changes(
                    change.get(bugid, {}), ni_changes.get(bugid, {})
                )
                if mrg:
                    new_changes[bugid] = mrg

        if not self.apply_autofix:
            self.autofix_changes = new_changes
            return bugs

        extra = self.get_db_extra()

        if self.is_limited and len(new_changes) > self.normal_changes_max:
            raise TooManyChangesError(bugs, new_changes, self.normal_changes_max)

        self.apply_changes_on_bugzilla(
            self.name(),
            new_changes,
            self.no_bugmail,
            self.dryrun or self.test_mode,
            extra,
        )

        return bugs

    @staticmethod
    def apply_changes_on_bugzilla(
        rule_name: str,
        new_changes: Mapping[str, dict],
        no_bugmail: bool = False,
        is_dryrun: bool = True,
        db_extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Apply changes on Bugzilla

        Args:
            rule_name: the name of the rule that is performing the changes.
            new_changes: the changes that will be performed. The dictionary key
                should be the bug ID.
            no_bugmail: If True, an account that doesn't trigger bugmail will be
                used to apply the changes.
            is_dryrun: If True, no changes will be applied. Instead, the
                proposed changes will be logged.
            db_extra: extra data to be passed to the DB. The dictionary key
                should be the bug ID.
        """
        if is_dryrun:
            for bugid, ch in new_changes.items():
                logger.info("The bugs: %s\n will be autofixed with:\n%s", bugid, ch)
            return None

        if db_extra is None:
            db_extra = {}

        max_retries = utils.get_config("common", "bugzilla_max_retries", 3)
        bugzilla_cls = SilentBugzilla if no_bugmail else Bugzilla

        for bugid, ch in new_changes.items():
            added = False
            for _ in range(max_retries):
                failures = bugzilla_cls([str(bugid)]).put(ch)
                if failures:
                    time.sleep(1)
                else:
                    added = True
                    db.BugChange.add(rule_name, bugid, extra=db_extra.get(bugid, ""))
                    break
            if not added:
                logger.error(
                    "%s: Cannot put data for bug %s (change => %s): %s",
                    rule_name,
                    bugid,
                    ch,
                    failures,
                )

    def terminate(self) -> None:
        """Called when everything is done"""
        return

    def organize(self, bugs: dict[str, Bug]) -> list[tuple[Any, ...]]:
        return utils.organize(bugs, self.columns(), key=self.sort_columns())

    def add_to_cache(self, bugs: dict[str, Bug]) -> None:
        """Add the bug keys to cache"""
        if isinstance(bugs, dict):
            self.cache.add(bugs.keys())
        else:
            self.cache.add(bugs)

    def get_email_data(self, date: str) -> EmailData:
        bugs = self.get_bugs(date=date)
        bugs = self._populate_prioritized_actions(bugs)
        bugs = self.autofix(bugs)
        self.add_to_cache(bugs)
        if not bugs:
            return cast(EmailData, [])

        return self.organize(bugs)

    def get_email(
        self, date: str, data: EmailData, preamble: str = ""
    ) -> tuple[str, str]:
        """Get title and body for the email"""
        assert data, "No data to send"

        extra = self.get_extra_for_template()
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template(self.template())
        message = template.render(
            date=date,
            data=data,
            extra=extra,
            str=str,
            enumerate=enumerate,
            plural=utils.plural,
            no_manager=self.no_manager,
            table_attrs=self.get_config("table_attrs"),
        )
        common = env.get_template("common.html")
        body = common.render(
            preamble=preamble,
            message=message,
            query_url=utils.shorten_long_bz_url(self.query_url),
        )
        return self.get_email_subject(date), body

    def _send_alert_about_too_many_changes(self, err: TooManyChangesError) -> None:
        """Send an alert email when there are too many changes to apply"""

        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template("aborted_preamble.html")
        preamble = template.render(
            changes=err.changes.items(),
            changes_size=len(err.changes),
            normal_changes_max=self.normal_changes_max,
            rule_name=self.name(),
            https_proxy=os.environ.get("https_proxy"),
            enumerate=enumerate,
            table_attrs=self.get_config("table_attrs"),
        )

        login_info = utils.get_login_info()
        receivers = utils.get_config("common", "receivers")
        date = lmdutils.get_date("today")
        data = self.organize(err.bugs)
        title, body = self.get_email(date, data, preamble)
        title = f"Aborted: {title}"

        mail.send(
            login_info["ldap_username"],
            receivers,
            title,
            body,
            html=True,
            login=login_info,
            dryrun=self.dryrun,
        )

    def send_email(self, date: str = "today") -> None:
        """Send the email"""
        if date:
            date = lmdutils.get_date(date)
            d = lmdutils.get_date_ymd(date)
            if isinstance(self, Nag):
                self.nag_date: datetime = d

            if not self.must_run(d):
                return

        if not self.has_enough_data():
            logger.info("The rule {} hasn't enough data to run".format(self.name()))
            return

        login_info = utils.get_login_info()
        email_data = self.get_email_data(date)
        if email_data:
            title, body = self.get_email(date, email_data)
            receivers = utils.get_receivers(self.name())
            cc_list = self.get_cc_emails(email_data)

            status = "Success"
            try:
                mail.send(
                    login_info["ldap_username"],
                    receivers,
                    title,
                    body,
                    Cc=cc_list,
                    html=True,
                    login=login_info,
                    dryrun=self.dryrun,
                )
            except Exception:
                logger.exception("Rule {}".format(self.name()))
                status = "Failure"

            db.Email.add(self.name(), receivers, "global", status)
            if isinstance(self, Nag):
                self.send_mails(title, dryrun=self.dryrun)
        else:
            name = self.name().upper()
            if date:
                logger.info("{}: No data for {}".format(name, date))
            else:
                logger.info("{}: No data".format(name))
            logger.info("Query: {}".format(self.query_url))

    def add_custom_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def parse_custom_arguments(self, args: argparse.Namespace) -> None:
        pass

    def get_args_parser(self) -> argparse.ArgumentParser:
        """Get the arguments from the command line"""
        parser = argparse.ArgumentParser(description=self.description())
        parser.add_argument(
            "--production",
            dest="dryrun",
            action="store_false",
            help="If the flag is not passed, just do the query, and print emails to console without emailing anyone",
        )

        parser.add_argument(
            "--no-limit",
            dest="is_limited",
            action="store_false",
            default=True,
            help=f"If the flag is not passed, the rule will be limited to touch a maximum of {self.normal_changes_max} bugs",
        )

        if not self.ignore_date():
            parser.add_argument(
                "-D",
                "--date",
                dest="date",
                action="store",
                default="today",
                help="Date for the query",
            )

        self.add_custom_arguments(parser)

        return parser

    def run(self) -> None:
        """Run the rule"""
        logger_extra["bugbot_rule"] = self.name()
        logger.info("Run rule %s", self.get_rule_path())

        args = self.get_args_parser().parse_args()
        self.parse_custom_arguments(args)
        date = "" if self.ignore_date() else args.date
        self.dryrun = args.dryrun
        self.is_limited = args.is_limited
        self.cache.set_dry_run(self.dryrun)

        if self.dryrun:
            logger.setLevel(logging.DEBUG)

        try:
            self.send_email(date=date)
            self.terminate()
            logger.info("Rule {} has finished.".format(self.get_rule_path()))
        except TooManyChangesError as err:
            self._send_alert_about_too_many_changes(err)
            logger.exception("Rule %s", self.name())
        except Exception:
            logger.exception("Rule {}".format(self.name()))
