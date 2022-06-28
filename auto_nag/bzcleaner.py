# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla

from auto_nag import db, logger, mail, utils
from auto_nag.cache import Cache
from auto_nag.nag_me import Nag


class BzCleaner(object):
    def __init__(self):
        super(BzCleaner, self).__init__()
        self._set_tool_name()
        self.has_autofix = False
        self.autofix_changes = {}
        self.quota_actions = defaultdict(list)
        self.no_manager = set()
        self.auto_needinfo = {}
        self.has_flags = False
        self.cache = Cache(self.name(), self.max_days_in_cache())
        self.test_mode = utils.get_config("common", "test", False)
        self.versions = None
        logger.info("Run tool {}".format(self.get_tool_path()))

    def _set_tool_name(self):
        module = sys.modules[self.__class__.__module__]
        base = os.path.dirname(__file__)
        scripts = os.path.join(base, "scripts")
        self.__tool_path__ = os.path.relpath(module.__file__, scripts)
        name = os.path.basename(module.__file__)
        name = os.path.splitext(name)[0]
        self.__tool_name__ = name

    def init_versions(self):
        self.versions = utils.get_checked_versions()
        return bool(self.versions)

    def max_days_in_cache(self):
        """Get the max number of days the data must be kept in cache"""
        return self.get_config("max_days_in_cache", -1)

    def preamble(self):
        return None

    def description(self):
        """Get the description for the help"""
        return ""

    def name(self):
        """Get the tool name"""
        return self.__tool_name__

    def get_tool_path(self):
        """Get the tool path"""
        return self.__tool_path__

    def needinfo_template(self):
        """Get the txt template filename"""
        return self.name() + "_needinfo.txt"

    def template(self):
        """Get the html template filename"""
        return self.name() + ".html"

    def subject(self):
        """Get the partial email subject"""
        return self.description()

    def get_email_subject(self, date):
        """Get the email subject with a date or not"""
        af = "[autofix]" if self.has_autofix else ""
        if date:
            return "[autonag]{} {} for the {}".format(af, self.subject(), date)
        return "[autonag]{} {}".format(af, self.subject())

    def ignore_date(self):
        """Should we ignore the date ?"""
        return False

    def must_run(self, date):
        """Check if the tool must run for this date"""
        days = self.get_config("must_run", None)
        if not days:
            return True
        weekday = date.weekday()
        week = utils.get_weekdays()
        for day in days:
            if week[day] == weekday:
                return True
        return False

    def has_enough_data(self):
        """Check if the tool has enough data to run"""
        if self.versions is None:
            # init_versions() has never been called
            return True
        return bool(self.versions)

    def filter_no_nag_keyword(self):
        """If True, then remove the bugs with [no-nag] in whiteboard from the bug list"""
        return True

    def add_no_manager(self, bugid):
        self.no_manager.add(str(bugid))

    def has_assignee(self):
        return False

    def has_needinfo(self):
        return False

    def get_mail_to_auto_ni(self, bug):
        return None

    def all_include_fields(self):
        return False

    def get_max_ni(self):
        return -1

    def get_max_actions(self):
        return -1

    def exclude_no_action_bugs(self):
        """
        If `True`, then remove bugs that have no actions from the email (e.g.,
        needinfo got ignored due to exceeding the limit). This is applied only
        when using the `add_prioritized_action()` method.

        Returning `False` could be useful if we want to list all actions the tool
        would do if it had no limits.
        """
        return True

    def ignore_meta(self):
        return False

    def columns(self):
        """The fields to get for the columns in email report"""
        return ["id", "summary"]

    def sort_columns(self):
        """Returns the key to sort columns"""
        return None

    def get_dates(self, date):
        """Get the dates for the bugzilla query (changedafter and changedbefore fields)"""
        date = lmdutils.get_date_ymd(date)
        lookup = self.get_config("days_lookup", 7)
        start_date = date - relativedelta(days=lookup)
        end_date = date + relativedelta(days=1)

        return start_date, end_date

    def get_extra_for_template(self):
        """Get extra data to put in the template"""
        return {}

    def get_extra_for_needinfo_template(self):
        """Get extra data to put in the needinfo template"""
        return {}

    def get_config(self, entry, default=None):
        return utils.get_config(self.name(), entry, default=default)

    def get_bz_params(self, date):
        """Get the Bugzilla parameters for the search query"""
        return {}

    def get_data(self):
        """Get the data structure to use in the bughandler"""
        return {}

    def get_summary(self, bug):
        return "..." if bug["groups"] else bug["summary"]

    def has_default_products(self):
        return True

    def has_product_component(self):
        return False

    def get_product_component(self):
        return self.prod_comp

    def get_max_years(self):
        return self.get_config("max-years", -1)

    def has_access_to_sec_bugs(self):
        return self.get_config("sec", True)

    def handle_bug(self, bug, data):
        """Implement this function to get all the bugs from the query"""
        return bug

    def get_db_extra(self):
        """Get extra information required for db insertion"""
        return {
            bugid: ni_mail
            for ni_mail, v in self.auto_needinfo.items()
            for bugid in v["bugids"]
        }

    def get_auto_ni_skiplist(self):
        """Return a set of email addresses that should never be needinfoed"""
        return set(self.get_config("needinfo_skiplist", default=[]))

    def add_auto_ni(self, bugid, data):
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
                "cc": data.get("cc", False),
            }
        return True

    def add_prioritized_action(self, bug, quota_name, needinfo=None, autofix=None):
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

    def get_bug_sort_key(self, bug):
        return None

    def _populate_prioritized_actions(self, bugs):
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

    def bughandler(self, bug, data):
        """bug handler for the Bugzilla query"""
        if bug["id"] in self.cache:
            return

        if self.handle_bug(bug, data) is None:
            return

        bugid = str(bug["id"])
        res = {"id": bugid}

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

    def get_products(self):
        return self.get_config("products") + self.get_config("additional_products", [])

    def amend_bzparams(self, params, bug_ids):
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

        # Limit the checkers to X years. Unlimited if max_years = -1
        max_years = self.get_max_years()
        if max_years > 0:
            n = utils.get_last_field_num(params)
            params.update(
                {
                    f"f{n}": "creation_ts",
                    f"o{n}": "greaterthan",
                    f"v{n}": f"-{max_years}y",
                }
            )

        if self.has_default_products():
            params["product"] = self.get_products()

        if not self.has_access_to_sec_bugs():
            n = utils.get_last_field_num(params)
            params.update({"f" + n: "bug_group", "o" + n: "isempty"})

        self.has_flags = "flags" in params.get("include_fields", [])

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
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

    def commenthandler(self, bug, bugid, data):
        return

    def _commenthandler(self, bug, bugid, data):
        comments = bug["comments"]
        bugid = str(bugid)
        if self.has_last_comment_time():
            if comments:
                data[bugid]["last_comment"] = utils.get_human_lag(comments[-1]["time"])
            else:
                data[bugid]["last_comment"] = ""

        self.commenthandler(bug, bugid, data)

    def get_comments(self, bugs):
        """Get the bugs comments"""
        if self.has_last_comment_time():
            bugids = self.get_list_bugs(bugs)
            Bugzilla(
                bugids=bugids, commenthandler=self._commenthandler, commentdata=bugs
            ).get_data().wait()
        return bugs

    def has_last_comment_time(self):
        return False

    def get_list_bugs(self, bugs):
        return [x["id"] for x in bugs.values()]

    def get_documentation(self):
        return "For more information, please visit [auto_nag documentation](https://wiki.mozilla.org/Release_Management/autonag#{}).".format(
            self.get_tool_path().replace("/", ".2F")
        )

    def has_bot_set_ni(self, bug):
        if not self.has_flags:
            raise Exception
        return utils.has_bot_set_ni(bug)

    def set_needinfo(self):
        if not self.auto_needinfo:
            return {}

        template_name = self.needinfo_template()
        assert bool(template_name)
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template(template_name)
        res = {}

        doc = self.get_documentation()

        for ni_mail, info in self.auto_needinfo.items():
            nick = info["nickname"]
            for bugid in info["bugids"]:
                data = {
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

    def has_individual_autofix(self, changes):
        # check if we have a dictionary with bug numbers as keys
        # return True if all the keys are bug number
        # (which means that each bug has its own autofix)
        return changes and all(
            isinstance(bugid, int) or bugid.isdigit() for bugid in changes
        )

    def get_autofix_change(self):
        """Get the change to do to autofix the bugs"""
        return self.autofix_changes

    def autofix(self, bugs):
        """Autofix the bugs according to what is returned by get_autofix_change"""
        ni_changes = self.set_needinfo()
        change = self.get_autofix_change()

        if not ni_changes and not change:
            return bugs

        self.has_autofix = True
        new_changes = {}
        if not self.has_individual_autofix(change):
            bugids = self.get_list_bugs(bugs)
            for bugid in bugids:
                new_changes[bugid] = utils.merge_bz_changes(
                    change, ni_changes.get(bugid, {})
                )
        else:
            change = {str(k): v for k, v in change.items()}
            bugids = set(change.keys()) | set(ni_changes.keys())
            for bugid in bugids:
                mrg = utils.merge_bz_changes(
                    change.get(bugid, {}), ni_changes.get(bugid, {})
                )
                if mrg:
                    new_changes[bugid] = mrg

        if self.dryrun or self.test_mode:
            for bugid, ch in new_changes.items():
                logger.info(
                    "The bugs: {}\n will be autofixed with:\n{}".format(bugid, ch)
                )
        else:
            extra = self.get_db_extra()
            max_retries = utils.get_config("common", "bugzilla_max_retries", 3)
            for bugid, ch in new_changes.items():
                added = False
                for _ in range(max_retries):
                    failures = Bugzilla([str(bugid)]).put(ch)
                    if failures:
                        time.sleep(1)
                    else:
                        added = True
                        db.BugChange.add(self.name(), bugid, extra=extra.get(bugid, ""))
                        break
                if not added:
                    self.failure_callback(bugid)
                    logger.error(
                        "{}: Cannot put data for bug {} (change => {}).".format(
                            self.name(), bugid, ch
                        )
                    )

        return bugs

    def failure_callback(self, bugid):
        """Called on Bugzilla.put failures"""
        return

    def terminate(self):
        """Called when everything is done"""
        return

    def organize(self, bugs):
        return utils.organize(bugs, self.columns(), key=self.sort_columns())

    def add_to_cache(self, bugs):
        """Add the bug keys to cache"""
        if isinstance(bugs, dict):
            self.cache.add(bugs.keys())
        else:
            self.cache.add(bugs)

    def get_email_data(self, date, bug_ids):
        bugs = self.get_bugs(date=date, bug_ids=bug_ids)
        bugs = self._populate_prioritized_actions(bugs)
        bugs = self.autofix(bugs)
        self.add_to_cache(bugs)
        if bugs:
            return self.organize(bugs)

    def get_email(self, date, bug_ids=[]):
        """Get title and body for the email"""
        data = self.get_email_data(date, bug_ids)
        if data:
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
                preamble=self.preamble(),
            )
            common = env.get_template("common.html")
            body = common.render(
                message=message, query_url=utils.shorten_long_bz_url(self.query_url)
            )
            return self.get_email_subject(date), body
        return None, None

    def send_email(self, date="today"):
        """Send the email"""
        if date:
            date = lmdutils.get_date(date)
            d = lmdutils.get_date_ymd(date)
            if isinstance(self, Nag):
                self.nag_date: datetime = d

            if not self.must_run(d):
                return

        if not self.has_enough_data():
            logger.info("The tool {} hasn't enough data to run".format(self.name()))
            return

        login_info = utils.get_login_info()
        title, body = self.get_email(date)
        if title:
            receivers = utils.get_receivers(self.name())
            status = "Success"
            try:
                mail.send(
                    login_info["ldap_username"],
                    receivers,
                    title,
                    body,
                    html=True,
                    login=login_info,
                    dryrun=self.dryrun,
                )
            except Exception:
                logger.exception("Tool {}".format(self.name()))
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

    def add_custom_arguments(self, parser):
        pass

    def parse_custom_arguments(self, args):
        pass

    def get_args_parser(self):
        """Get the argumends from the command line"""
        parser = argparse.ArgumentParser(description=self.description())
        parser.add_argument(
            "--production",
            dest="dryrun",
            action="store_false",
            help="If the flag is not passed, just do the query, and print emails to console without emailing anyone",
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

    def run(self):
        """Run the tool"""
        args = self.get_args_parser().parse_args()
        self.parse_custom_arguments(args)
        date = "" if self.ignore_date() else args.date
        self.dryrun = args.dryrun
        self.cache.set_dry_run(self.dryrun)
        try:
            self.send_email(date=date)
            self.terminate()
            logger.info("Tool {} has finished.".format(self.get_tool_path()))
        except Exception:
            logger.exception("Tool {}".format(self.name()))
