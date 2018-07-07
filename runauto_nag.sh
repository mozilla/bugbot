#!/bin/bash
PATH_SCRIPT="$( cd "$(dirname "$0")" ; pwd -P )"
. $PATH_SCRIPT/venv/bin/activate
cd $PATH_SCRIPT
PYTHONPATH=. python -m auto_nag.scripts.query_creator
PYTHONPATH=. python -m auto_nag.scripts.rm_query_creator
# very common
PYTHONPATH=. python -m auto_nag.scripts.no_assignee
# very common
PYTHONPATH=. python -m auto_nag.scripts.leave_open
# very common
PYTHONPATH=. python -m auto_nag.scripts.regression
# common
PYTHONPATH=. python -m auto_nag.scripts.has_regression_range_no_keyword
# Pretty rare
PYTHONPATH=. python -m auto_nag.scripts.topcrash_bad_severity
# Pretty rare
PYTHONPATH=. python -m auto_nag.scripts.feature_regression
# Pretty common
PYTHONPATH=. python -m auto_nag.scripts.unaffected_affected_no_reg
