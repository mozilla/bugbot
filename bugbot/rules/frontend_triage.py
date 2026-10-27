# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import requests

from bugbot import logger, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.hackbot_utils import api_url, trigger_agent_run

AGENT = "frontend-triage"

# The components the agent triages, read from bugbug, which owns the list: each entry
# there also carries the Slack channel the run reports to. When this list was a tuple
# here, the two copies drifted, and a pair here but not in bugbug got unattended triage
# with nobody told. Widening the agent's reach still takes a code review, of the bugbug
# PR, but no longer a bugbot change or release.
#
# Read from `master`, so a new entry is live here as soon as it merges, while the agent
# only learns its channel on the next hackbot deploy. Runs in that window apply but post
# nothing to Slack.
SCOPE_URL = (
    "https://raw.githubusercontent.com/mozilla/bugbug/refs/heads/master/"
    "agents/frontend-triage/scope.json"
)


def triaged_components() -> list[tuple[str, str]]:
    """The `(product, component)` pairs bugbug's `scope.json` lists.

    Raises rather than falling back to an empty or cached list, so a fetch that fails
    aborts the rule and lands in the cron error digest instead of quietly triaging
    nothing.
    """
    resp = requests.get(SCOPE_URL, timeout=20)
    resp.raise_for_status()
    pairs = [
        (entry["product"], entry["component"]) for entry in resp.json()["components"]
    ]
    if not pairs:
        raise ValueError(f"{SCOPE_URL} lists no components")
    # `get_bz_params` joins each product's components into one comma-separated
    # `anyexact` value, so a comma in a name would split it into two.
    if any("," in component for _, component in pairs):
        raise ValueError(f"{SCOPE_URL} has a component name with a comma")
    return pairs


# Every hackbot agent comments as this account, so a bug `bug-fix` has worked is
# skipped too. Safe direction: the cost is a bug we skip, not a second unattended
# comment on one that already has one.
HACKBOT_EMAIL = "hackbot@mozilla.tld"

# Pairs queried on "somebody moved the component here" rather than "the bug was filed
# here". `Firefox :: Untriaged` needs it because `component.py` moves a freshly filed
# bug out in the same `cron_run_hourly.sh` pass that starts the run, while a bug moved
# *back* is one it will never touch again. `changedto` separates the two: Bugzilla
# writes no activity row for the component a bug was filed with.
# A pair here that leaves bugbug's scope is simply not queried.
MOVED_BACK_COMPONENTS = frozenset({("Firefox", "Untriaged")})


class FrontendTriage(BzCleaner):
    """Ask hackbot's frontend-triage agent to triage newly filed frontend bugs.

    Scoped to the components in bugbug's `scope.json`, on the day the bug was filed
    into one of them, and to nothing else about the reporter; the exception is
    `MOVED_BACK_COMPONENTS`, queried on when the component last changed instead.
    `handle_bug` drops bots.

    This rule only starts runs: the agent investigates the source, comments on the
    bug, and reports to Slack itself, so nothing is written to Bugzilla from here.
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
        # The scope spans several products, so "which component is this
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
        }

        # One AND group per product, inside a top-level OR. Top-level `product` and
        # `component` params are matched independently, so passing a list of each
        # would also put every cross pairing in scope -- `Toolkit :: Installer`
        # the day somebody creates it. No cross pairing exists today, but this
        # rule spends money and posts to bugs unattended, so its reach should not
        # be able to widen on its own.
        #
        # The date sits inside each group rather than once at the top level: the same
        # query for the pairs that want `creation_ts`, since a top-level AND
        # distributes over the OR, and what lets `MOVED_BACK_COMPONENTS` differ.
        groups: dict[tuple[str, str | None], list[str]] = {}
        for product, component in triaged_components():
            # A moved-back pair gets a group of its own, since its date clauses differ.
            if (product, component) in MOVED_BACK_COMPONENTS:
                key = (product, component)
            else:
                key = (product, None)
            groups.setdefault(key, []).append(component)

        n = utils.get_last_field_num(params)
        params[f"j{n}"] = "OR"
        params[f"f{n}"] = "OP"
        for (product, moved_back_component), components in groups.items():
            n = utils.get_last_field_num(params)
            params[f"j{n}"] = "AND"
            params[f"f{n}"] = "OP"
            n = utils.get_last_field_num(params)
            params.update({f"f{n}": "product", f"o{n}": "equals", f"v{n}": product})
            n = utils.get_last_field_num(params)
            params.update(
                {
                    f"f{n}": "component",
                    f"o{n}": "anyexact",
                    f"v{n}": ",".join(components),
                }
            )

            if moved_back_component:
                # Both clauses: `changedto` alone matches a move made years ago,
                # `changedafter` alone matches a move to anywhere.
                n = utils.get_last_field_num(params)
                params.update(
                    {
                        f"f{n}": "component",
                        f"o{n}": "changedto",
                        f"v{n}": moved_back_component,
                    }
                )
                n = utils.get_last_field_num(params)
                params.update(
                    {
                        f"f{n}": "component",
                        f"o{n}": "changedafter",
                        f"v{n}": start_date,
                    }
                )
                n = utils.get_last_field_num(params)
                params.update(
                    {
                        f"n{n}": 1,
                        f"f{n}": "commenter",
                        f"o{n}": "equals",
                        f"v{n}": HACKBOT_EMAIL,
                    }
                )
            else:
                n = utils.get_last_field_num(params)
                params.update(
                    {
                        f"f{n}": "creation_ts",
                        f"o{n}": "greaterthan",
                        f"v{n}": start_date,
                    }
                )

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
