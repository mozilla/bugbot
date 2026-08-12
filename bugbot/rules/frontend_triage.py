# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import logger
from bugbot.bzcleaner import BzCleaner
from bugbot.hackbot_utils import api_url, trigger_agent_run
from bugbot.people import People

AGENT = "frontend-triage"


class FrontendTriage(BzCleaner):
    """Ask hackbot's frontend-triage agent to triage newly filed frontend bugs.

    Scoped to bugs filed by Mozilla staff (which includes QA) in
    `Firefox :: New Tab Page`, because the agent's analysis is posted to the bug
    unattended when it is confident. This rule only starts runs: the agent
    investigates the source, comments on the bug, and reports to Slack itself, so
    nothing is written to Bugzilla from here.
    """

    def __init__(self, people: People | None = None) -> None:
        super().__init__()
        # Injectable because configs/people.json is gitignored and absent in CI.
        self.people = people or People.get_instance()
        self.max_triggers = self.get_config("max_triggers", 10)
        self.left_for_next_run = 0

    def description(self):
        return "[Using AI] Bugs sent for automatic frontend triage"

    def columns(self):
        return ["id", "summary", "creator", "run_id"]

    def has_default_products(self):
        # The query names its own product; the 19-product default list would put
        # the whole tree in scope.
        return False

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        return {
            "include_fields": ["id", "summary", "creator"],
            # Named literally, one product and one component: Bugzilla matches
            # the two fields independently, so lists here would not express a
            # product-to-component mapping. Widening to a second component means
            # query groups, not another entry in a list.
            "product": "Firefox",
            "component": "New Tab Page",
            # Defects only: the agent triages broken behaviour, not feature work.
            "bug_type": "defect",
            "resolution": "---",
            "f1": "creation_ts",
            "o1": "greaterthan",
            "v1": start_date,
        }

    def handle_bug(self, bug, data):
        # The IAM roster covers QA too, now that they file from @mozilla.com
        # addresses, so staff membership is the whole filter. It beats a check on
        # the address itself, which would miss the employees who file from a
        # personal Bugzilla account.
        if not self.people.is_mozilla(bug["creator"]):
            return None

        # `bughandler` rebuilds each row from id + summary alone, so the reporter
        # has to be stashed here to reach the report.
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
