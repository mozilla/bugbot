#!/bin/bash
PATH_SCRIPT="$( cd "$(dirname "$0")" ; pwd -P )"
. $PATH_SCRIPT/venv/bin/activate
cd $PATH_SCRIPT
export PYTHONPATH=.
# Nag to developers
# Daily
python -m auto_nag.scripts.query_creator

# What is fixed in nightly but affecting beta or release
# Daily
python -m auto_nag.scripts.rm_query_creator

# Bug fixed without assignee
# very common
python -m auto_nag.scripts.no_assignee

# Bug closed with the leave open keyword
# very common
python -m auto_nag.scripts.leave_open

# Try to detect potential regressions by looking at comments
# very common
python -m auto_nag.scripts.regression

# hasRegressionRange is set but no regression keyword
# common
python -m auto_nag.scripts.has_regression_range_no_keyword

# Top crash with an incorrect severity
# Pretty rare
python -m auto_nag.scripts.topcrash_bad_severity

# Bug with both the regression and feature keywords
# Pretty rare
python -m auto_nag.scripts.feature_regression

# Bug marked as unaffecting the release bug affecting beta/nightly
# Pretty common
python -m auto_nag.scripts.unaffected_affected_no_reg

# Version is set but status_firefox isn't
# Very common
python -m auto_nag.scripts.version_affected

# Bug is tracked for a release but the bug severity is small
# pretty common
python -m auto_nag.scripts.tracked_bad_severity

# Detect one word summary
# a bit rare
python -m auto_nag.scripts.one_two_word_summary

# Closes crash bug without any crashes for the last 12 weeks
# pretty common
python -m auto_nag.scripts.no_crashes

# Notify bugs tracked with P4 or P5 priorities for the ongoing releases
# Pretty common
python -m auto_nag.scripts.mismatch-priority-tracking

# Bugs where the reporter has a needinfo
# Pretty common
python -m auto_nag.scripts.reporter_with_ni

# P1 bug with no activity for more than 24 weeks (with autofix)
# Pretty common
python -m auto_nag.scripts.old_p1_bug

# Unconfirmed bugs with an assignee (with autofix)
# Pretty common
python -m auto_nag.scripts.assignee_but_unconfirmed

# Notify bugs in untriaged with an important severity
python -m auto_nag.scripts.untriage_important_sev

# List bug with the meta keyword but not [meta] in the title
# Pretty common
python -m auto_nag.scripts.meta_summary_missing

# List bug without the meta keyword with [meta] in the title (with autofix)
# Pretty common
python -m auto_nag.scripts.summary_meta_missing

# P2 bug with no activity for more than 1 years (with autofix)
# Pretty common
python -m auto_nag.scripts.old_p2_bug -d

# List reopened bugs with invalid nightly status flag
# Pretty common
python -m auto_nag.scripts.nightly_reopened

# Needinfo the triage owner when we find bugs without the priority set
# Pretty common
# Only on Andrew for now
python -m auto_nag.scripts.ni_triage_owner

# Needinfo the assignee or the triage owner when a bug has leave-open keyword an no activty
# Pretty common
python -m auto_nag.scripts.leave_open_no_activity
