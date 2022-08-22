#!/bin/bash

export PYTHONPATH=.

./runauto_nag_common.sh

. venv/bin/activate

# force the update of dependencies
pip install -r requirements.txt

# Clean the log files
python -m auto_nag.log --clean

# Not up-to-date release date
# Daily
python -m auto_nag.next_release --production

# Update the triage owners on Bugzilla
python -m auto_nag.scripts.triage_owner_rotations --production

# Send a todo list to set priority
# Daily
python -m auto_nag.scripts.to_triage --production

# Process reminders
# Daily
python -m auto_nag.scripts.reminder --production

# Nag triage fallback to update calendar
# Daily
python -m auto_nag.round_robin_fallback --production

# Needinfo assignee when a patch could be uplifted to beta
# Daily
python -m auto_nag.scripts.uplift_beta --production

# What is fixed in nightly but affecting beta or release
# Daily
python -m auto_nag.scripts.missed_uplifts --production

# Top crash with an incorrect severity
# Pretty rare
python -m auto_nag.scripts.topcrash_bad_severity --production

# Bug with both the regression and feature keywords
# Pretty rare
python -m auto_nag.scripts.feature_regression --production

# Detect one word summary
# a bit rare
python -m auto_nag.scripts.one_two_word_summary --production

# Bugs where the reporter has a needinfo
# Pretty common
python -m auto_nag.scripts.reporter_with_ni --production

# Notify bugs in untriaged with an important severity
python -m auto_nag.scripts.untriage_important_sev --production

# Needinfo the assignee or the triage owner when a bug has leave-open keyword an no activity
# Pretty common
python -m auto_nag.scripts.leave_open_no_activity --production

# Needinfo the triage owner or the assignee when we find meta bugs not depending on bugs and no activity
# Pretty common
python -m auto_nag.scripts.meta_no_deps_no_activity --production

# Several tools here
#  1) has an unlanded patch or some flags not up-to-date
#     Pretty rare
#  2) Tracked bugs
#  3) Tracked bugs with needinfos
python -m auto_nag.scripts.multi_nag --production

# has a r+ patch, is open, has no activity for few weeks
# Pretty common
python -m auto_nag.scripts.not_landed --production

# New workflow
# https://docs.google.com/document/d/1EHuWa-uR-7Sq63X1ZiDN1mvJ9gQtWiqYrCifkySJyW0/edit#
# https://docs.google.com/drawings/d/1oZA-AUvkOxGMNhZNofL8Wlfk6ol3o5ATQCV5DJJKbwM/edit
python -m auto_nag.scripts.workflow.multi_nag --production

# Defect with the "feature" keyword
python -m auto_nag.scripts.feature_but_type_defect --production

# Defect with the "meta" keyword
python -m auto_nag.scripts.meta_defect --production

# Bugs with several duplicates
python -m auto_nag.scripts.several_dups --production

# Bugs with a lot of cc
python -m auto_nag.scripts.lot_of_cc --production

# Bugs with a lot of votes
python -m auto_nag.scripts.lot_of_votes --production

# reporter has a needinfo and no activity for the last X weeks
# Pretty common
python -m auto_nag.scripts.newbie_with_ni

# Bug caused several regressions recently reported
# Pretty rare
python -m auto_nag.scripts.warn_regressed_by --production

# Defect starting with please or enable in the title
python -m auto_nag.scripts.defect_with_please_or_enable --production

# Regressions without regressed_by and some dependencies (blocks, depends_on)
# Pretty rare
python -m auto_nag.scripts.regression_without_regressed_by --production

# Bugs with a fuzzing bisection but without regressed_by
python -m auto_nag.scripts.fuzzing_bisection_without_regressed_by --production

# Suggest components for untriaged bugs (daily, full list without confidence threshold)
python -m auto_nag.scripts.component --frequency daily --production

# Try to detect potential wrong bug types using bugbug
python -m auto_nag.scripts.defectenhancementtask --production

# Try to detect potential missing Has STR using bugbug
python -m auto_nag.scripts.stepstoreproduce --production

# Unassign inactive bugs with the good-first-bug keyword
python -m auto_nag.scripts.good_first_bug_unassign_inactive --production

# Look for missing bugzilla comments for recently-landed changesets
python -m auto_nag.scripts.missed_landing_comment --production

# Look for recently landed changesets referencing leave-open security bugs
python -m auto_nag.scripts.leave_open_sec --production

# Look for recent PDF.js updates that fix some bug
python -m auto_nag.scripts.pdfjs_update --production

# Look for tracked bugs with a needinfo from a release manager
python -m auto_nag.scripts.ni_from_manager --production

# Approve tracking request for bugs automatically filed for expiring telemetry probes
python -m auto_nag.scripts.telemetry_expiry_tracking_autoapproval --production

# Needinfo triage owner on bugs assigned to inactive accounts
python -m auto_nag.scripts.assignee_no_login --production

# Needinfo for bugs with inconsistent severity flags
python -m auto_nag.scripts.severity_inconsistency --production

# Needinfo for bugs with underestimated severity levels
python -m auto_nag.scripts.severity_underestimated --production

# Needinfo for bugs with high security keywords whose set to low severity
python -m auto_nag.scripts.severity_high_security --production

# Nag for components that need triage owner to be assigned
python -m auto_nag.scripts.vacant_triage_owner --production

# Notify about bugs with needinfo requests on inactive users
python -m auto_nag.scripts.inactive_ni_pending --production

# Confirm bugs with crash signatures
python -m auto_nag.scripts.crash_signature_confirm --production

# Bugs with patches after being closed
python -m auto_nag.scripts.patch_closed_bug --production

# Confirm bugs with affected flags
python -m auto_nag.scripts.affected_flag_confirm --production

# Suggest increasing the severity for bugs with P1 WebCompat priority
python -m auto_nag.scripts.severity_high_compat_priority --production

# Identify missing or inactive team managers
python -m auto_nag.scripts.vacant_team_manager --production

# Notify about tracked bugs with no assignee, low severity, or low priority
python -m auto_nag.scripts.tracked_attention --production

# Needinfo patch authors to find active reviewers
python -m auto_nag.scripts.inactive_reviewer --production

# Nag on fuzz blocker bugs
python -m auto_nag.scripts.fuzz_blockers --production

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

deactivate

if [ "$errored" = true ] ; then
    exit -1
fi
