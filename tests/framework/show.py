# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""Run scenarios and print their actual outcome, to help writing expectations.

    python -m tests.framework.show tests/scenarios/RULE/NAME.yaml [--rows] [--email] [--searches]
"""

import argparse
import logging
import sys

from tests.framework.scenario import check, dump_yaml, load_scenario, run_scenario
from tests.framework.search import search_criteria


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", help="scenario files")
    parser.add_argument("--rows", action="store_true", help="show the email rows")
    parser.add_argument("--email", action="store_true", help="show the email body")
    parser.add_argument(
        "--searches",
        action="store_true",
        help="show the searches of the rule, and the bugs they matched",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="show the logs")
    args = parser.parse_args(argv)
    if not args.verbose:
        logging.disable(logging.WARNING)

    failed = False
    for path in args.paths:
        scenario = load_scenario(path)
        result = run_scenario(scenario)
        print(f"# {path}")
        outcome = result.as_expectation()
        if not result.ran:
            outcome["ran"] = False
        if args.rows:
            outcome["email"] = {int(k): v for k, v in result.email.items()}
        print(dump_yaml({"expect": outcome}))
        if args.searches:
            searches = [
                {
                    "params": {
                        k: v[0] if len(v) == 1 else v
                        for k, v in search_criteria(search["params"]).items()
                    },
                    "matched": search["ids"],
                }
                for search in result.searches
            ]
            print(dump_yaml({"searches": searches}))
        if args.email and result.email_body:
            print(result.email_body)
        errors = check(result, scenario.expect)
        if errors:
            failed = True
            print("# Differences with the expectations:")
            print("\n".join(f"#   {e}" for e in errors))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
