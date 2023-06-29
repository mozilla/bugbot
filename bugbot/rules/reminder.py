# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from dateutil.parser import ParserError
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import BugzillaUser

from bugbot import utils
from bugbot.bzcleaner import BzCleaner

REMINDER_TYPES = ["test", "pref", "disclosure", "deprecation"]
DATE_MATCH = re.compile(
    r"\[reminder\-(%s) ([0-9]{4}-[0-9]{1,2}-[0-9]{1,2})\]" % "|".join(REMINDER_TYPES)
)


class Reminder(BzCleaner):
    def __init__(self):
        super(Reminder, self).__init__()
        self.extra_ni = {}
        self.autofix_whiteboard = {}

    def description(self):
        return "Bugs with whiteboard reminders"

    def get_bz_params(self, date):
        self.today = lmdutils.get_date_ymd(date)

        params = {
            "include_fields": [
                "assigned_to",
                "whiteboard",
                "triage_owner",
                "history",
                "creator",
                "creation_time",
            ],
            "f1": "status_whiteboard",
            "o1": "substring",
            "v1": "[reminder-",
        }

        return params

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        new_whiteboard = whiteboard = bug["whiteboard"]
        matches = DATE_MATCH.findall(whiteboard)

        # We support having multiple reminders that expire on a single day.
        # (I'm not sure why, but I guess we should.)
        reminders = []

        for m in matches:
            tag, date = m

            # If we can't parse the date, do a little hack to throw it back
            # at the user.
            try:
                parsed_date = lmdutils.get_date_ymd(date)
            except ParserError:
                replace_string = f"[reminder-{tag} {date}]"
                new_whiteboard = new_whiteboard.replace(replace_string, "")
                reminders.append({"full_tag": replace_string, "invalid_date": True})
                continue

            if parsed_date <= self.today:
                replace_string = f"[reminder-{tag} {date}]"
                new_whiteboard = new_whiteboard.replace(replace_string, "")
                reminders.append({"full_tag": replace_string})

        if new_whiteboard == whiteboard:
            return

        target_entries = []
        for entry in bug["history"]:
            for field in entry["changes"]:
                if field["field_name"] == "whiteboard":
                    # Check to see if any of the replace strings appeared in this change.
                    for r in reminders:
                        if (
                            r["full_tag"] in field["added"]
                            and r["full_tag"] not in field["removed"]
                        ):
                            entry["full_tag"] = r["full_tag"]
                            target_entries.append(entry)
                    break

        if not target_entries:
            # If the history shows no changes, it indicates that the reminders
            # were added when the bug was filed.
            target_entries.extend(
                {
                    "who": bug["creator"],
                    "when": bug["creation_time"],
                    "full_tag": reminder["full_tag"],
                }
                for reminder in reminders
            )

        user_emails_to_names = self._get_user_emails_to_names(target_entries)

        for r in reminders:
            for entry in target_entries:
                if r["full_tag"] == entry["full_tag"]:
                    if user_emails_to_names[entry["who"]] == "Invalid User":
                        reminders.remove(r)
                    else:
                        r["who"] = user_emails_to_names[entry["who"]]
                        r["when"] = utils.get_human_lag(entry["when"])

        if not reminders:
            return

        data[bugid] = {
            "full_tags": ", ".join([r["full_tag"] for r in reminders]),
        }

        self.autofix_whiteboard[bugid] = {
            "whiteboard": new_whiteboard,
        }

        self.extra_ni[bugid] = {"reminders": reminders}

        return bug

    def _get_user_emails_to_names(self, target_entries):
        """
        Do a bunch of annoying stuff to translate bugzilla email addresses
        to nicknames, and then from a list of nicknames to a nicely formatted
        string.
        """

        # emails -> nicks
        def user_handler(user, data):
            data[user["name"]] = "Invalid User"
            for g in user["groups"]:
                if g["name"] == "editbugs" or g["name"] == "canconfirm":
                    data[user["name"]] = (
                        user["real_name"] or user["nick"] or user["name"]
                    )

        user_emails_to_names = {}
        BugzillaUser(
            user_names=[entry["who"] for entry in target_entries],
            include_fields=["real_name", "nick", "name", "groups"],
            user_handler=user_handler,
            user_data=user_emails_to_names,
        ).wait()

        return user_emails_to_names

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def get_autofix_change(self):
        return self.autofix_whiteboard

    def columns(self):
        return ["id", "summary", "full_tags"]

    def get_mail_to_auto_ni(self, bug):
        for field in ["assigned_to", "triage_owner"]:
            person = bug.get(field, "")
            if person and not utils.is_no_assignee(person):
                return {"mail": person, "nickname": bug[f"{field}_detail"]["nick"]}

        return None


if __name__ == "__main__":
    Reminder().run()
