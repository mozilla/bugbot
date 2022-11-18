# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import List, Set

from libmozdata.bugzilla import Bugzilla

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.history import History


class DuplicateCopyMetadata(BzCleaner):
    def description(self):
        return "Copied fields from duplicate bugs"

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])
        data[bugid] = bug

        return bug

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        dup_bugs = super().get_bugs(date, bug_ids, chunk_size)

        original_bug_ids = {bug["dupe_of"] for bug in dup_bugs.values()}
        original_bugs = {}

        Bugzilla(
            original_bug_ids,
            include_fields=[
                "id",
                "summary",
                "whiteboard",
                "keywords",
                "duplicates",
                "comments",
                "is_open",
            ],
            bughandler=self.handle_bug,
            bugdata=original_bugs,
        ).wait()

        assert len(original_bug_ids) == len(original_bugs)

        results = {}
        for bug_id, bug in original_bugs.items():
            if not bug["is_open"]:
                continue

            copied_fields = {}
            for dup_bug_id in bug["duplicates"]:
                dup_bug = dup_bugs.get(str(dup_bug_id))
                if not dup_bug:
                    continue

                # Keywords: copy the `access` keyword from duplicates
                if "access" not in bug["keywords"] and "access" in dup_bug["keywords"]:
                    if "keywords" not in copied_fields:
                        copied_fields["keywords"] = {
                            "from": [dup_bug["id"]],
                            "value": "access",
                        }
                    else:
                        copied_fields["keywords"]["from"].append(dup_bug["id"])

                # Whiteboard: copy the `access-s*` whiteboard rating from duplicates
                if (
                    "access-s" not in bug["whiteboard"]
                    and "access-s" in dup_bug["whiteboard"]
                ):
                    new_access_tag = utils.get_whiteboard_access_rating(
                        dup_bug["whiteboard"]
                    )

                    if (
                        "whiteboard" not in copied_fields
                        or new_access_tag < copied_fields["whiteboard"]["value"]
                    ):
                        copied_fields["whiteboard"] = {
                            "from": [dup_bug["id"]],
                            "value": new_access_tag,
                        }
                    elif new_access_tag == copied_fields["whiteboard"]["value"]:
                        copied_fields["whiteboard"]["from"].append(dup_bug["id"])

            previously_copied_fields = self.get_previously_copied_fields(bug)
            copied_fields = sorted(
                (
                    field,
                    change["value"],
                    utils.english_list(
                        sorted(f"bug {bug_id}" for bug_id in change["from"])
                    ),
                )
                for field, change in copied_fields.items()
                if field not in previously_copied_fields
            )

            if copied_fields:
                results[bug_id] = {
                    "id": bug_id,
                    "summary": bug["summary"],
                    "copied_fields": copied_fields,
                }

                self.set_autofix(bug, copied_fields)

        return results

    def set_autofix(self, bug: dict, copied_fields: List[tuple]) -> None:
        """Set the autofix for a bug

        Args:
            bug: The bug to set the autofix for.
            copied_fields: The list of copied fields with their values and the
                bugs they were copied from (field, value, source).
        """
        bug_id = str(bug["id"])
        autofix = {}

        duplicates = {source for _, _, source in copied_fields}

        # NOTE: modifying the following comment template should also be
        # reflected in the `get_previously_copied_fields` method.
        comment = (
            f"The following {utils.plural('field has', copied_fields, 'fields have')} been copied "
            f"from {utils.plural('a duplicate bug', duplicates, 'duplicate bugs')}:\n"
            "| Field | Value | Source |\n"
            "| ----- | ----- | ------ |\n"
        )

        for field, value, source in copied_fields:
            if field == "keywords":
                autofix["keywords"] = {"add": value}
            elif field == "whiteboard":
                autofix["whiteboard"] = bug["whiteboard"] + value
            else:
                raise ValueError(f"Unsupported field: {field}")

            comment += f"| {field.capitalize()} | {value} | {source} |\n"

        comment += "\n\n" + self.get_documentation()
        autofix["comment"] = {"body": comment}
        self.autofix_changes[bug_id] = autofix

    def get_previously_copied_fields(self, bug: dict) -> Set[str]:
        """Get the fields that have been copied from a bug's duplicates in the past.

        Args:
            bug: The bug to get the previously copied fields for.

        Returns:
            A set of previously copied fields.
        """
        previously_copied_fields = set()

        for comment in bug["comments"]:
            if comment["author"] != History.BOT or not comment["text"].startswith(
                "The following field"
            ):
                continue

            lines = comment["text"].splitlines()
            if len(lines) < 4 or lines[1] != "| Field | Value | Source |":
                continue

            for line in lines[3:]:
                if line.startswith("|"):
                    field = line.split("|")[1].strip().lower()
                    previously_copied_fields.add(field)

        return previously_copied_fields

    def columns(self):
        return ["id", "summary", "copied_fields"]

    def get_bz_params(self, date):
        fields = [
            "whiteboard",
            "keywords",
            "dupe_of",
        ]

        params = {
            "include_fields": fields,
            "resolution": "DUPLICATE",
            "chfieldfrom": "-7d",
            "chfield": [
                "resolution",
                "keywords",
                "status_whiteboard",
            ],
            "j1": "OR",
            "f1": "OP",
            "f3": "status_whiteboard",
            "o3": "anywordssubstr",
            "v3": "[access-s",
            "f4": "keywords",
            "o4": "equals",
            "v4": "access",
            "f5": "CP",
        }

        return params


if __name__ == "__main__":
    DuplicateCopyMetadata().run()
