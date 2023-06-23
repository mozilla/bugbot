# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pprint
import re
from datetime import timedelta

import jinja2
import requests
from libmozdata import socorro
from libmozdata import utils as lmdutils
from libmozdata.bugzilla import Bugzilla
from libmozdata.connection import Connection, Query

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.crash import socorro_util
from bugbot.crash.analyzer import SignaturesDataFetcher


# NOTE: At this point, we will file bugs on bugzilla-dev. Once we are confident
# that the bug filing is working as expected, we can switch to filing bugs in
# the production instance of Bugzilla.
class DevBugzilla(Bugzilla):
    URL = "https://bugzilla-dev.allizom.org"
    API_URL = URL + "/rest/bug"
    ATTACHMENT_API_URL = API_URL + "/attachment"
    TOKEN = utils.get_login_info()["bz_api_key_dev"]


class FileCrashBug(BzCleaner):
    """File bugs for new actionable crashes"""

    # NOTE: If you make changes that affect the output of the rule, you should
    # increment this number. This is needed in the experimental phase only.
    version = 1

    max_bug_title_length = 255

    memory_access_error_reasons = (
        # On Windows:
        "EXCEPTION_ACCESS_VIOLATION_READ",
        "EXCEPTION_ACCESS_VIOLATION_WRITE",
        "EXCEPTION_ACCESS_VIOLATION_EXEC"
        # On Linux:
        "SIGSEGV / SEGV_MAPERR",
        "SIGSEGV / SEGV_ACCERR",
    )

    excluded_moz_reason_strings = (
        "MOZ_CRASH(OOM)",
        "MOZ_CRASH(Out of memory)",
        "out of memory",
        "Shutdown hanging",
        # TODO(investigate): do we need to exclude signatures that their reason
        # contains `[unhandlable oom]`?
        # Example: arena_t::InitChunk | arena_t::AllocRun | arena_t::MallocLarge | arena_t::Malloc | BaseAllocator::malloc | Allocator::malloc | PageMalloc
        # "[unhandlable oom]",
    )

    # If any of the crash reason starts with any of the following, then it is
    # Network or I/O error.
    excluded_io_error_reason_prefixes = (
        "EXCEPTION_IN_PAGE_ERROR_READ",
        "EXCEPTION_IN_PAGE_ERROR_WRITE",
        "EXCEPTION_IN_PAGE_ERROR_EXEC",
    )

    # TODO(investigate): do we need to exclude all these signatures prefixes?
    excluded_signature_prefixes = (
        "OOM | ",
        "bad hardware | ",
        "shutdownhang | ",
    )

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

    def get_new_actionable_crashes(self):
        product = "Firefox"
        channel = "nightly"
        days_to_check = 7
        days_without_crashes = 7

        duration = days_to_check + days_without_crashes
        end_date = lmdutils.get_date_ymd("today")
        start_date = end_date - timedelta(duration)
        earliest_allowed_date = lmdutils.get_date_str(
            end_date - timedelta(days_to_check)
        )
        date_range = socorro.SuperSearch.get_search_date(start_date, end_date)

        params = {
            "product": product,
            "release_channel": channel,
            "date": date_range,
            # TODO(investigate): should we do a local filter instead of the
            # following (should we exclude the signature if one of the crashes
            # is a shutdown hang?):
            # If the `ipc_shutdown_state` or `shutdown_progress` field are
            # non-empty then it's a shutdown hang.
            "ipc_shutdown_state": "__null__",
            "shutdown_progress": "__null__",
            # TODO(investigate): should we use the following instead of the
            # local filter.
            # "oom_allocation_size": "!__null__",
            "_aggs.signature": [
                "moz_crash_reason",
                "reason",
                "_histogram.date",
                "_cardinality.install_time",
                "_cardinality.oom_allocation_size",
            ],
            "_results_number": 0,
            "_facets_size": 10000,
        }

        def handler(search_resp: dict, data: dict):
            logger.debug(
                "Total of %d signatures received from Socorro",
                len(search_resp["facets"]["signature"]),
            )

            for crash in search_resp["facets"]["signature"]:
                signature = crash["term"]
                if any(
                    signature.startswith(excluded_prefix)
                    for excluded_prefix in self.excluded_signature_prefixes
                ):
                    # Ignore signatures that start with any of the excluded prefixes.
                    continue

                facets = crash["facets"]
                installations = facets["cardinality_install_time"]["value"]
                if installations <= 1:
                    # Ignore crashes that only happen on one installation.
                    continue

                first_date = facets["histogram_date"][0]["term"]
                if first_date < earliest_allowed_date:
                    # The crash is not new, skip it.
                    continue

                if any(
                    reason["term"].startswith(io_error_prefix)
                    for reason in facets["reason"]
                    for io_error_prefix in self.excluded_io_error_reason_prefixes
                ):
                    # Ignore Network or I/O error crashes.
                    continue

                if crash["count"] < 20:
                    # For signatures with low volume, having multiple types of
                    # memory errors indicates potential bad hardware crashes.
                    num_memory_error_types = sum(
                        reason["term"] in self.memory_access_error_reasons
                        for reason in facets["reason"]
                    )
                    if num_memory_error_types > 1:
                        # Potential bad hardware crash, skip it.
                        continue

                # TODO: Add a filter using the `possible_bit_flips_max_confidence`
                # field to exclude bad hardware crashes. The filed is not available yet.
                # See: https://bugzilla.mozilla.org/show_bug.cgi?id=1816669#c3

                # TODO(investigate): is this needed since we are already
                # filtering signatures that start with "OOM | "
                if facets["cardinality_oom_allocation_size"]["value"]:
                    # If one of the crashes is an OOM crash, skip it.
                    continue

                # TODO(investigate): do we need to check for the `moz_crash_reason`
                moz_crash_reasons = facets["moz_crash_reason"]
                if moz_crash_reasons and any(
                    excluded_reason in reason["term"]
                    for reason in moz_crash_reasons
                    for excluded_reason in self.excluded_moz_reason_strings
                ):
                    continue

                data[signature] = crash

        signatures: dict[str, dict] = {}
        socorro.SuperSearch(
            params=params,
            handler=handler,
            handlerdata=signatures,
        ).wait()

        logger.debug(
            "Total of %d signatures left after applying the filtering criteria",
            len(signatures),
        )

        return signatures.keys()

    def filleter_signatures_with_bugs(self, signatures: set) -> set:
        """Filter out signatures that already have bugs filed for them.

        Args:
            signatures: The signatures to filter.

        Returns:
            The signatures that don't have bugs filed for them.
        """

        # TODO(investigate): is it better to use https://crash-stats.mozilla.org/api/Bugs/
        # instead of using bugzilla API directly?

        params_base: dict = {
            "include_fields": [
                "cf_crash_signature",
            ],
        }

        params_list = []
        for signatures_chunk in Connection.chunks(list(signatures), 30):
            params = params_base.copy()
            n = int(utils.get_last_field_num(params))
            params[f"f{n}"] = "OP"
            params[f"j{n}"] = "OR"
            for signature in signatures_chunk:
                n += 1
                params[f"f{n}"] = "cf_crash_signature"
                params[f"o{n}"] = "regexp"
                params[f"v{n}"] = rf"\[(@ |@){re.escape(signature)}( \]|\])"
            params[f"f{n+1}"] = "CP"
            params_list.append(params)

        bug_signatures = set(signatures)

        def handler(res, data):
            for bug in res["bugs"]:
                data.difference_update(utils.get_signatures(bug["cf_crash_signature"]))

        Bugzilla(
            queries=[
                Query(Bugzilla.API_URL, params, handler, bug_signatures)
                for params in params_list
            ],
        ).wait()

        # NOTE: this will not be needed when moving to production
        DevBugzilla(
            queries=[
                Query(DevBugzilla.API_URL, params, handler, bug_signatures)
                for params in params_list
            ],
        ).wait()

        return bug_signatures

    def get_bugs(self, date):
        self.query_url = None
        bugs = {}

        signatures = self.get_new_actionable_crashes()
        signatures = self.filleter_signatures_with_bugs(signatures)
        logger.debug(
            "Total of %d signatures left after filtering ones with a bug filed for them",
            len(signatures),
        )

        analyzed_signatures = SignaturesDataFetcher(
            signatures, "Firefox", "nightly"
        ).analyze()

        logger.debug("Total of %d bugs will be filed", len(analyzed_signatures))

        for signature in analyzed_signatures:
            logger.debug("Generating bug for signature: %s", signature.signature_term)

            title = f"Crash in [@ {signature.signature_term}]"
            if len(title) > self.max_bug_title_length:
                title = title[: self.max_bug_title_length - 3] + "..."

            # TODO: Handle cases where the regressor is a security bug. I such
            # cases, we may want to fil the bug as security bug.

            flags = None
            if signature.regressed_by:
                # TODO: check user activity and if the ni? is open
                flags = [
                    {
                        "name": "needinfo",
                        "requestee": signature.regressed_by_author["name"],
                        "status": "?",
                        "new": "true",
                    }
                ]

            report = signature.fetch_representing_processed_crash()
            description = self.bug_description_template.render(
                {
                    **socorro_util.generate_bug_description_data(report),
                    "signature": signature,
                    "needinfo_regression_author": bool(flags),
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
            # [ ] Firefox status flags
            # [ ] Severity
            # [ ] Time correlation
            # [X] User comments
            # [ ] Crash address commonalities
            # [ ] Estimated future crash volume

            bug_data = {
                "blocks": "bugbot-auto-crash",
                "type": "defect",
                "keywords": ["crash"],
                "status_whiteboard": f"[bugbot-crash-v{self.version}]",
                "summary": title,
                "product": signature.crash_component.product,
                "component": signature.crash_component.name,
                "op_sys": signature.bugzilla_op_sys,
                "rep_platform": signature.bugzilla_cpu_arch,
                "cf_crash_signature": f"[@ {signature.signature_term}]",
                "description": description,
                # TODO: Uncomment the following lines when we move to file on
                # the production instance of Bugzilla. Filling `regressed_by` or
                # `flags` on bugzilla-dev will cause "bug does not exist" errors.
                # "regressed_by": signature.regressed_by,
                # "flags": flags,
            }

            if self.dryrun:
                logger.info("Dry-run bug:")
                pprint.pprint(bug_data)
                bug_id = str(len(bugs) + 1)
            else:
                # NOTE: When moving to production:
                #   - Use Bugzilla instead of DevBugzilla
                #   - Drop the DevBugzilla class
                #   - Update the bug URL `file_crash_bug.html`
                #   - Drop the bug link `file_crash_bug_description.md.jinja`
                #   - Fill the `regressed_by` and `flags` fields
                resp = requests.post(
                    url=DevBugzilla.API_URL,
                    json=bug_data,
                    headers=DevBugzilla([]).get_header(),
                    verify=True,
                    timeout=DevBugzilla.TIMEOUT,
                )
                resp.raise_for_status()
                bug_id = str(resp.json()["id"])
                # TODO: log the created bugs info somewhere (e.g., DB,
                # spreadsheet, or LabelStudio)

            bugs[bug_id] = {
                "id": bug_id,
                "summary": title,
                "component": signature.crash_component,
            }

        return bugs


if __name__ == "__main__":
    FileCrashBug().run()
