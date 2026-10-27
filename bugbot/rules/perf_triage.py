# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.hackbot_utils import api_url, trigger_agent_run

AGENT = "perf-triage"

# A bug arriving here is asking for a Performance Impact rating. Kept here rather
# than in configs/rules.json on purpose: the agent's rating lands on the bug
# unattended, so widening its reach should take a code review.
TRIAGED_COMPONENT = ("Core", "Performance: General")

# Every hackbot agent comments as this account, so a bug `bug-fix` has worked is
# skipped too. Safe direction: the cost is a bug we skip, not a second unattended
# comment on one that already has one.
HACKBOT_EMAIL = "hackbot@mozilla.tld"


class PerfTriage(BzCleaner):
    """Ask hackbot's perf-triage agent to rate bugs waiting for performance triage.

    A bug qualifies when, within the lookup window, its Performance Impact was set
    to `?` (and still is) or it landed in `TRIAGED_COMPONENT` (and is still there),
    whether by being filed that way or by a later change. `handle_bug` drops bots.

    This rule only starts runs: the agent rates the bug and comments on it itself,
    so nothing is written to Bugzilla from here.
    """

    def __init__(self) -> None:
        super().__init__()
        self.max_triggers = self.get_config("max_triggers", 10)
        self.left_for_next_run = 0
        self.backlog = False

    def add_custom_arguments(self, parser):
        parser.add_argument(
            "--backlog",
            action="store_true",
            help=(
                "Ignore the lookup window: every open bug at `?`, and every unrated "
                f"one in {' :: '.join(TRIAGED_COMPONENT)}. For clearing the backlog "
                "when the rule is first enabled; still capped per invocation."
            ),
        )

    def parse_custom_arguments(self, args):
        self.backlog = args.backlog

    def description(self):
        return "[Using AI] Bugs sent for automatic performance triage"

    def columns(self):
        return ["id", "summary", "product", "component", "creator", "run_id"]

    def has_default_products(self):
        # A `?` is a request for performance triage in any product.
        return False

    def has_product_component(self):
        return True

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        params = {
            "include_fields": ["id", "summary", "creator"],
            "resolution": "---",
            "n1": 1,
            "f1": "commenter",
            "o1": "equals",
            "v1": HACKBOT_EMAIL,
        }

        def add(**clause):
            n = utils.get_last_field_num(params)
            params.update({f"{k}{n}": v for k, v in clause.items()})

        def recently(field, value):
            if self.backlog:
                return
            # Bugzilla writes no activity row for the value a bug was filed with,
            # so "set recently" is either a recent change to it or a recent filing.
            # Both change clauses: `changedto` alone matches a change made years
            # ago, `changedafter` alone matches a change to anything.
            add(j="OR", f="OP")
            add(j="AND", f="OP")
            add(f=field, o="changedto", v=value)
            add(f=field, o="changedafter", v=start_date)
            add(f="CP")
            add(f="creation_ts", o="greaterthan", v=start_date)
            add(f="CP")

        product, component = TRIAGED_COMPONENT

        add(j="OR", f="OP")

        add(j="AND", f="OP")
        add(f="cf_performance_impact", o="equals", v="?")
        recently("cf_performance_impact", "?")
        add(f="CP")

        add(j="AND", f="OP")
        add(f="product", o="equals", v=product)
        add(f="component", o="equals", v=component)
        if self.backlog:
            # Already-rated bugs here get a comment-only run when they arrive, but
            # sweeping all of them would re-triage the component's whole history.
            add(f="cf_performance_impact", o="anyexact", v="---,?")
        recently("component", component)
        add(f="CP")

        add(f="CP")

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
            raise ValueError(f"HACKBOT_API_URL is not set; cannot start {AGENT} runs")

        triggered: dict = {}
        for bugid, bug in bugs.items():
            if len(triggered) >= self.max_triggers:
                logger.warning(
                    "Reached the cap of %d %s runs; the rest wait for the next run",
                    self.max_triggers,
                    AGENT,
                )
                break

            try:
                # One run per bug, ever: the cache forgets after
                # `max_days_in_cache`, and a bug reset to `?` after the agent
                # rated it is asking a person to re-triage, not the agent.
                bug["run_id"] = trigger_agent_run(
                    AGENT, {"bug_id": int(bugid)}, dedupe_key=f"{AGENT}:{bugid}"
                )
            except Exception:
                logger.exception("Failed to trigger %s for bug %s", AGENT, bugid)
                continue

            triggered[bugid] = bug

        self.left_for_next_run = len(bugs) - len(triggered)

        return triggered

    def get_extra_for_template(self):
        return {"left_for_next_run": self.left_for_next_run}


if __name__ == "__main__":
    PerfTriage().run()
