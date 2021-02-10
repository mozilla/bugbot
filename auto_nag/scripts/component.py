# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import logger
from auto_nag.bugbug_utils import get_bug_ids_classification
from auto_nag.bzcleaner import BzCleaner
from auto_nag.utils import get_config, nice_round


class Component(BzCleaner):
    def __init__(self):
        super().__init__()
        self.autofix_component = {}
        self.frequency = "daily"

    def add_custom_arguments(self, parser):
        parser.add_argument(
            "--frequency",
            help="Daily (noisy) or Hourly",
            choices=["daily", "hourly"],
            default="daily",
        )

    def parse_custom_arguments(self, args):
        self.frequency = args.frequency

    def description(self):
        return f"[Using ML] Assign a component to untriaged bugs ({self.frequency})"

    def columns(self):
        return ["id", "summary", "component", "confidence", "autofixed"]

    def sort_columns(self):
        return lambda p: (-p[3], -int(p[0]))

    def has_product_component(self):
        # Inject product and components when calling BzCleaner.get_bugs
        return True

    def get_bz_params(self, date):
        start_date, end_date = self.get_dates(date)

        bot = get_config("common", "bot_bz_mail")[0]

        return {
            "include_fields": ["id", "groups", "summary", "product", "component"],
            # Ignore bugs for which we ever modified the product or the component.
            "n1": 1,
            "f1": "product",
            "o1": "changedby",
            "v1": bot,
            "n2": 1,
            "f2": "component",
            "o2": "changedby",
            "v2": bot,
            # Ignore closed bugs.
            "bug_status": "__open__",
            # Get recent General bugs, and all Untriaged bugs.
            "j3": "OR",
            "f3": "OP",
            "j4": "AND",
            "f4": "OP",
            "f5": "component",
            "o5": "equals",
            "v5": "General",
            "f6": "creation_ts",
            "o6": "greaterthan",
            "v6": start_date,
            "f7": "CP",
            "f8": "component",
            "o8": "equals",
            "v8": "Untriaged",
            "f9": "CP",
        }

    def get_bugs(self, date="today", bug_ids=[]):
        # Retrieve the bugs with the fields defined in get_bz_params
        raw_bugs = super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=7000)

        if len(raw_bugs) == 0:
            return {}

        # Extract the bug ids
        bug_ids = list(raw_bugs.keys())

        # Classify those bugs
        bugs = get_bug_ids_classification("component", bug_ids)

        results = {}

        for bug_id in sorted(bugs.keys()):
            bug_data = bugs[bug_id]

            if not bug_data.get("available", True):
                # The bug was not available, it was either removed or is a
                # security bug
                continue

            if not {"prob", "index", "class", "extra_data"}.issubset(bug_data.keys()):
                raise Exception(f"Invalid bug response {bug_id}: {bug_data!r}")

            bug = raw_bugs[bug_id]
            prob = bug_data["prob"]
            index = bug_data["index"]
            suggestion = bug_data["class"]
            conflated_components_mapping = bug_data["extra_data"][
                "conflated_components_mapping"
            ]

            # Skip product-only suggestions that are not useful.
            if "::" not in suggestion and bug["product"] == suggestion:
                continue

            suggestion = conflated_components_mapping.get(suggestion, suggestion)

            if "::" not in suggestion:
                logger.error(
                    f"There is something wrong with this component suggestion! {suggestion}"
                )
                continue

            i = suggestion.index("::")
            suggested_product = suggestion[:i]
            suggested_component = suggestion[i + 2 :]

            # When moving bugs out of the 'General' component, we don't want to change the product (unless it is Firefox).
            if bug["component"] == "General" and bug["product"] not in {
                suggested_product,
                "Firefox",
            }:
                continue

            # Don't move bugs from Firefox::General to Core::Internationalization.
            if (
                bug["product"] == "Firefox"
                and bug["component"] == "General"
                and suggested_product == "Core"
                and suggested_component == "Internationalization"
            ):
                continue

            bug_id = str(bug["id"])

            result = {
                "id": bug_id,
                "summary": bug["summary"],
                "component": suggestion,
                "confidence": nice_round(prob[index]),
                "autofixed": False,
            }

            # In daily mode, we send an email with all results.
            if self.frequency == "daily":
                results[bug_id] = result

            confidence_threshold_conf = (
                "confidence_threshold"
                if bug["component"] != "General"
                else "general_confidence_threshold"
            )

            if prob[index] >= self.get_config(confidence_threshold_conf):
                self.autofix_component[bug_id] = {
                    "product": suggested_product,
                    "component": suggested_component,
                }

                result["autofixed"] = True

                # In hourly mode, we send an email with only the bugs we acted upon.
                if self.frequency == "hourly":
                    results[bug_id] = result

        return results

    def get_autofix_change(self):
        cc = self.get_config("cc")
        return {
            bug_id: (
                data.update(
                    {
                        "cc": {"add": cc},
                        "comment": {
                            "body": f"The [Bugbug](https://github.com/mozilla/bugbug/) bot thinks this bug should belong to the '{data['product']}::{data['component']}' component, and is moving the bug to that component. Please revert this change in case you think the bot is wrong."
                        },
                    }
                )
                or data
            )
            for bug_id, data in self.autofix_component.items()
        }

    def get_db_extra(self):
        return {
            bugid: "{}::{}".format(v["product"], v["component"])
            for bugid, v in self.get_autofix_change().items()
        }


if __name__ == "__main__":
    Component().run()
