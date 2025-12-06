# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pprint
from functools import cached_property

import humanize
import jinja2
import requests
from libmozdata.bugzilla import Bugzilla

from bugbot import logger, utils
from bugbot.bug.analyzer import BugAnalyzer
from bugbot.bzcleaner import BzCleaner
from bugbot.crash import socorro_util
from bugbot.crash.analyzer import SignatureAnalyzer, SignaturesDataFetcher
from bugbot.user_activity import UserActivity, UserStatus


class FileCrashBug(BzCleaner):
    """File bugs for new actionable crashes."""

    MAX_BUG_TITLE_LENGTH = 255

    def __init__(self):
        super().__init__()

        self.bug_description_template = jinja2.Environment(
            loader=jinja2.FileSystemLoader("templates")
        ).get_template("file_crash_bug_description.md.jinja")

    def description(self):
        return "New actionable crashes"

    def columns(self):
        return ["component", "id", "summary"]

    def get_bz_params(self, date):
        return {
            "resolution": ["---", "FIXED"],
            "keywords": ["feature", "regression"],
            "keywords_type": "allwords",
        }

    @cached_property
    def current_status_flags(self) -> list[str]:
        """The status flags for Firefox, which includes Nightly, Beta, Release, and ESR."""
        status = "cf_status_firefox"
        status_esr = "cf_status_firefox_esr"
        data: dict[str, list[str]] = {
            status: [],
            status_esr: [],
        }

        def handler(bug):
            for field in bug.keys():
                if field.startswith(status_esr):
                    data[status_esr].append(field)
                elif field.startswith(status):
                    data[status].append(field)

        Bugzilla(bugids=1234567, include_fields="_custom", bughandler=handler).wait()

        return (
            # ESR
            sorted(
                data[status_esr],
                key=lambda flag: int(flag[len(status_esr) :]),
            )[-1:]
            # Release, Beta, Nightly
            + sorted(
                data[status],
                key=lambda flag: int(flag[len(status) :]),
            )[-3:]
        )

    @cached_property
    def nightly_status_flag(self) -> str:
        """The nightly release status flag for Firefox."""
        return self.current_status_flags[-1]

    def _active_regression_authors(
        self, signatures: list[SignatureAnalyzer]
    ) -> set[str]:
        """Get Bugzilla usernames for users who are active and can be needinfo'd.

        Args:
            signatures: a list of signatures for which to check the status of
                their regression author.

        Returns:
            A set of user emails.
        """
        ni_skiplist = self.get_auto_ni_skiplist()
        users = UserActivity(include_fields=["requests"]).check_users(
            (
                signature.regressed_by_author["name"]
                for signature in signatures
                if signature.regressed_by_author
            ),
            keep_active=True,
            fetch_employee_info=True,
        )

        return {
            name
            for name, user in users.items()
            if name not in ni_skiplist
            and user["status"] == UserStatus.ACTIVE
            and not user["requests"]["needinfo"]["blocked"]
        }

    def get_bugs(self, date):
        self.query_url = None
        bugs = {}

        data_fetcher = SignaturesDataFetcher.find_new_actionable_crashes(
            "Firefox", "nightly"
        )
        signatures = data_fetcher.analyze()
        # This is the last filtering stage which aims to avoid filing bugs for
        # junky crashes, where the volume is low and the crashes do not show
        # signals of being actionable or critical.
        signatures = [
            signature
            for signature in signatures
            if signature.num_installs > 5
            or signature.num_crashes > 25
            or signature.is_potential_near_null_crash
            or signature.is_potential_security_crash
            or signature.regressed_by
            or signature.has_moz_crash_reason("MOZ_RELEASE_ASSERT")
            or signature.has_moz_crash_reason("DocumentChannel::SetLoadFlags")
        ]

        signature_details_delta = humanize.naturaldelta(data_fetcher.SUMMARY_DURATION)

        active_regression_authors = self._active_regression_authors(signatures)

        for signature in signatures:
            logger.debug("Generating bug for signature: %s", signature.signature_term)

            title = (
                f"Startup crash in [@ {signature.signature_term}]"
                if signature.is_startup_related_crash
                else f"Crash in [@ {signature.signature_term}]"
            )
            if len(title) > self.MAX_BUG_TITLE_LENGTH:
                title = title[: self.MAX_BUG_TITLE_LENGTH - 3] + "..."

            # Whether we should needinfo the regression author.
            needinfo_regression_author = (
                signature.regressed_by
                and signature.regressed_by_author["email"] in active_regression_authors
            )

            report = signature.fetch_representative_processed_crash()
            description = self.bug_description_template.render(
                {
                    **socorro_util.generate_bug_description_data(report),
                    "signature": signature,
                    "needinfo_regression_author": needinfo_regression_author,
                    "signature_details_delta": signature_details_delta,
                    "signature_details_channel": "Nightly",
                }
            )

            # TODO: Provide the following information:
            # [X] Crash signature
            # [X] Top 10 frames of crashing thread
            # [X] Component
            # [X] The kind of crash
            # [ ] Regression window
            # [X] Inducing patch
            # [X] Reason
            # [X] Regressed by
            # [X] Platform
            # [x] Firefox status flags
            # [ ] Severity
            # [ ] Time correlation
            # [X] User comments
            # [X] Crash address commonalities
            # [ ] Estimated future crash volume

            bug_data = {
                "blocks": ["bugbot-auto-crash"],
                "type": "defect",
                "keywords": ["crash"],
                "summary": title,
                "product": signature.crash_component.product,
                "component": signature.crash_component.name,
                "op_sys": signature.bugzilla_op_sys,
                "rep_platform": signature.bugzilla_cpu_arch,
                "cf_crash_signature": f"[@ {signature.signature_term}]",
                "description": description,
                self.nightly_status_flag: "affected",
                # NOTE(suhaib): the following CC is for testing purposes only
                # to allow us access and evaluate security bugs. It should be
                # removed at some point after we move to production.
                "cc": [
                    "smujahid@mozilla.com",
                    "aryx.bugmail@gmx-topmail.de",
                ],
            }

            if needinfo_regression_author:
                bug_data["flags"] = [
                    {
                        "name": "needinfo",
                        "requestee": signature.regressed_by_author["name"],
                        "status": "?",
                        "new": "true",
                    }
                ]
                bug_data["cc"].append(signature.regressed_by_author["name"])

            if signature.is_potential_phc_crash:
                bug_data["blocks"].append("PHC")

            if signature.is_potential_security_crash:
                bug_data["groups"] = ["core-security"]

            if signature.regressed_by:
                bug_data["keywords"].append("regression")
                bug_data["regressed_by"] = [signature.regressed_by]

                # Empty statuses are needed to detect the affected releases.
                for flag in self.current_status_flags:
                    if flag not in bug_data:
                        bug_data[flag] = "---"

                bug_analyzer = BugAnalyzer(bug_data, signature.bugs_store)
                updates = bug_analyzer.detect_version_status_updates()
                for update in updates:
                    bug_data[update.flag] = update.status

            if self.dryrun:
                logger.info("Dry-run bug:")
                pprint.pprint(bug_data)
                bug_id = str(len(bugs) + 1)
            else:
                try:
                    bug = utils.create_bug(bug_data)
                except requests.HTTPError as err:
                    logger.exception(
                        "Failed to create a bug for signature %s: %s",
                        signature.signature_term,
                        err.response.text,
                    )
                    continue

                bug_id = str(bug["id"])
                # TODO: log the created bugs info somewhere (e.g., DB,
                # spreadsheet, or LabelStudio)

            bugs[bug_id] = {
                "id": bug_id,
                "summary": "..." if signature.is_potential_security_crash else title,
                "component": signature.crash_component,
            }

        logger.debug("Total of %d bugs have been filed", len(bugs))

        return bugs


if __name__ == "__main__":
    FileCrashBug().run()
