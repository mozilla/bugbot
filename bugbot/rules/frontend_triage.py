# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.hackbot_utils import api_url, trigger_agent_run

AGENT = "frontend-triage"

# The components the agent triages, as `(product, component)` pairs. Kept here rather
# than in configs/rules.json on purpose: the agent's analysis lands on the bug
# unattended, so widening its reach should take a code review.
#
# Every pair here needs a channel in the agent's own `TRIAGE_SCOPE` (bugbug's
# agents/frontend-triage/hackbot_agents/frontend_triage/config.py), and the agent has to
# be deployed with it first. `channel_for` fails closed, which silences the Slack
# notification but not the run: the comment and the severity change still apply, so a
# pair added here ahead of the agent gets unattended triage with nobody told. Nothing
# checks this -- the two lists are in separate repos and cannot see each other.
TRIAGED_COMPONENTS = (
    ("Firefox", "New Tab Page"),
    ("Firefox for Android", "History"),
    ("Toolkit", "Application Update"),
    ("Firefox", "Installer"),
    ("Firefox", "Site Permissions"),
    ("Firefox", "Sharing"),
    ("Firefox", "IP Protection"),
    ("Firefox for Android", "Toolbar"),
    ("Firefox for Android", "Homepage"),
    ("Firefox", "Messaging System"),
    ("Toolkit", "Data Sanitization"),
)


class FrontendTriage(BzCleaner):
    """Ask hackbot's frontend-triage agent to triage newly filed frontend bugs.

    Scoped to bugs filed by a reporter holding `editbugs`, in the components listed
    in `TRIAGED_COMPONENTS`, because the agent's analysis is posted to the bug
    unattended when it is confident. `editbugs` is Bugzilla's own signal that a
    reporter is trusted with bug metadata, so it is a closer match for "files a
    report the agent can work from" than the IAM staff roster this used to read,
    which missed vendor QA and long-standing community contributors alike. This
    rule only starts runs: the agent investigates the source, comments on the bug,
    and reports to Slack itself, so nothing is written to Bugzilla from here.
    """

    def __init__(self) -> None:
        super().__init__()
        self.max_triggers = self.get_config("max_triggers", 10)
        self.left_for_next_run = 0

    def description(self):
        return "[Using AI] Bugs sent for automatic frontend triage"

    def columns(self):
        return ["id", "summary", "product", "component", "creator", "run_id"]

    def has_default_products(self):
        # The query names its own products; the 19-product default list would put
        # the whole tree in scope.
        return False

    def has_product_component(self):
        # `TRIAGED_COMPONENTS` spans three products, so "which component is this
        # row about" is no longer obvious from the summary alone. Returning True
        # gets both fields into `include_fields` and into every row for free
        # (bzcleaner's `amend_bzparams` and `bughandler`), so unlike `creator`
        # they need no stashing here.
        return True

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        params = {
            "include_fields": ["id", "summary", "creator"],
            # Defects only: the agent triages broken behaviour, not feature work.
            "bug_type": "defect",
            "resolution": "---",
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": start_date,
            "f2": "reporter",
            "o2": "substring",
            "v2": "%group.editbugs%",
        }

        # One AND group per pair, inside a top-level OR. Top-level `product` and
        # `component` params are matched independently, so passing a list of each
        # would also put every cross pairing in scope -- `Toolkit :: Installer`
        # the day somebody creates it. No cross pairing exists today, but this
        # rule spends money and posts to bugs unattended, so its reach should not
        # be able to widen on its own.
        n = utils.get_last_field_num(params)
        params[f"j{n}"] = "OR"
        params[f"f{n}"] = "OP"
        for product, component in TRIAGED_COMPONENTS:
            n = utils.get_last_field_num(params)
            params[f"j{n}"] = "AND"
            params[f"f{n}"] = "OP"
            n = utils.get_last_field_num(params)
            params.update({f"f{n}": "product", f"o{n}": "equals", f"v{n}": product})
            n = utils.get_last_field_num(params)
            params.update({f"f{n}": "component", f"o{n}": "equals", f"v{n}": component})
            n = utils.get_last_field_num(params)
            params[f"f{n}"] = "CP"
        n = utils.get_last_field_num(params)
        params[f"f{n}"] = "CP"

        return params

    def handle_bug(self, bug, data):
        if utils.is_bot_email(bug["creator"]):
            return None

        # `bughandler` rebuilds each row from id + summary alone, so the reporter
        # has to be carried over by hand to reach the report.
        data[str(bug["id"])] = {"creator": bug["creator"]}

        return bug

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        return self.trigger_runs(
            super().get_bugs(date=date, bug_ids=bug_ids, chunk_size=chunk_size)
        )

    def trigger_runs(self, bugs: dict) -> dict:
        """Start a triage run per bug, and return the ones we actually started.

        Bugs we did not trigger are dropped from the result so they are neither
        reported as triaged nor added to the cache — a bug skipped over the cap,
        or one whose trigger failed, gets another chance on the next run.
        """
        if self.dryrun:
            logger.info(
                "Dry run: would trigger %s for bugs %s",
                AGENT,
                ", ".join(bugs) or "(none)",
            )
            for bug in bugs.values():
                bug["run_id"] = "(dry run)"
            return bugs

        if not api_url():
            # A misconfiguration, not a transient failure: fail once here rather
            # than letting every bug look like its own flaky trigger below. The
            # rule aborts and the cron error digest picks it up.
            raise ValueError(f"HACKBOT_API_URL is not set; cannot start {AGENT} runs")

        triggered: dict = {}
        for bugid, bug in bugs.items():
            if len(triggered) >= self.max_triggers:
                # Each run is real LLM spend, so a flood of filings must not turn
                # into a flood of agent runs.
                logger.warning(
                    "Reached the cap of %d %s runs; the rest wait for the next run",
                    self.max_triggers,
                    AGENT,
                )
                break

            try:
                bug["run_id"] = trigger_agent_run(AGENT, {"bug_id": int(bugid)})
            except Exception:
                logger.exception("Failed to trigger %s for bug %s", AGENT, bugid)
                continue

            triggered[bugid] = bug

        # Covers both causes — over the cap, and a trigger that failed — since
        # either way the bug stays out of the cache and comes back next run.
        self.left_for_next_run = len(bugs) - len(triggered)

        return triggered

    def get_extra_for_template(self):
        return {"left_for_next_run": self.left_for_next_run}


if __name__ == "__main__":
    FrontendTriage().run()
