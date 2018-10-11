#!/bin/bash
PATH_SCRIPT="$( cd "$(dirname "$0")" ; pwd -P )"
. $PATH_SCRIPT/venv/bin/activate
cd $PATH_SCRIPT
# Nag to developers
# Daily
PYTHONPATH=. python -m auto_nag.scripts.query_creator

# What is fixed in nightly but affecting beta or release
# Daily
PYTHONPATH=. python -m auto_nag.scripts.rm_query_creator

# Bug fixed without assignee
# very common
PYTHONPATH=. python -m auto_nag.scripts.no_assignee

# Bug closed with the leave open keyword
# very common
PYTHONPATH=. python -m auto_nag.scripts.leave_open

# Try to detect potential regressions by looking at comments
# very common
PYTHONPATH=. python -m auto_nag.scripts.regression

# hasRegressionRange is set but no regression keyword
# common
PYTHONPATH=. python -m auto_nag.scripts.has_regression_range_no_keyword

# Top crash with an incorrect severity
# Pretty rare
PYTHONPATH=. python -m auto_nag.scripts.topcrash_bad_severity

# Bug with both the regression and feature keywords
# Pretty rare
PYTHONPATH=. python -m auto_nag.scripts.feature_regression

# Bug marked as unaffecting the release bug affecting beta/nightly
# Pretty common
PYTHONPATH=. python -m auto_nag.scripts.unaffected_affected_no_reg

# Version is set but status_firefox isn't
# Very common
PYTHONPATH=. python -m auto_nag.scripts.version_affected

# Bug is tracked for a release but the bug severity is small
# pretty common
PYTHONPATH=. python -m auto_nag.scripts.tracked_bad_severity

# Detect one word summary
# a bit rare
PYTHONPATH=. python -m auto_nag.scripts.one_two_word_summary

# Closes crash bug without any crashes for the last 12 weeks
# pretty common
PYTHONPATH=. python -m auto_nag.scripts.no_crashes
