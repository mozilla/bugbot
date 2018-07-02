#!/bin/bash
PATH_SCRIPT="$( cd "$(dirname "$0")" ; pwd -P )"
. $PATH_SCRIPT/venv/bin/activate
cd $PATH_SCRIPT
PYTHONPATH=. python -m auto_nag.scripts.query_creator
PYTHONPATH=. python -m auto_nag.scripts.rm_query_creator
PYTHONPATH=. python -m auto_nag.scripts.no_assignee
PYTHONPATH=. python -m auto_nag.scripts.leave_open
PYTHONPATH=. python -m auto_nag.scripts.regression
PYTHONPATH=. python -m auto_nag.scripts.has_regression_range_no_keyword
PYTHONPATH=. python -m auto_nag.scripts.topcrash_bad_severity
