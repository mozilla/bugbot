#!/bin/bash

source ./scripts/cron_common_start.sh

# Update the triage owners on Bugzilla
python -m bugbot.scripts.triage_owner_rotations --production

# Close inactive intermittent bugs
python -m bugbot.scripts.close_intermittents --production

# Send a todo list to set priority
# Daily
python -m bugbot.scripts.to_triage --production

# Process reminders
# Daily
python -m bugbot.scripts.reminder --production

# Nag triage fallback to update calendar
# Daily
python -m bugbot.round_robin_fallback --production

# Needinfo assignee when a patch could be uplifted to beta
# Daily
python -m bugbot.scripts.uplift_beta --production

# What is fixed in nightly but affecting beta or release
# Daily
python -m bugbot.scripts.missed_uplifts --production

# Bug with both the regression and feature keywords
# Pretty rare
python -m bugbot.scripts.feature_regression --production

# Detect one word summary
# a bit rare
python -m bugbot.scripts.one_two_word_summary --production

# Bugs where the reporter has a needinfo
# Pretty common
python -m bugbot.scripts.reporter_with_ni --production

# Notify bugs in untriaged with an important severity
python -m bugbot.scripts.untriage_important_sev --production

# Needinfo the assignee or the triage owner when a bug has leave-open keyword an no activity
# Pretty common
python -m bugbot.scripts.leave_open_no_activity --production

# Needinfo the triage owner or the assignee when we find meta bugs not depending on bugs and no activity
# Pretty common
python -m bugbot.scripts.meta_no_deps_no_activity --production

# Several tools here
#  1) has an unlanded patch or some flags not up-to-date
#     Pretty rare
#  2) Tracked bugs
#  3) Tracked bugs with needinfos
python -m bugbot.scripts.multi_nag --production

# has a r+ patch, is open, has no activity for few weeks
# Pretty common
python -m bugbot.scripts.not_landed --production

# New workflow
# https://docs.google.com/document/d/1EHuWa-uR-7Sq63X1ZiDN1mvJ9gQtWiqYrCifkySJyW0/edit#
# https://docs.google.com/drawings/d/1oZA-AUvkOxGMNhZNofL8Wlfk6ol3o5ATQCV5DJJKbwM/edit
python -m bugbot.scripts.workflow.multi_nag --production

# Defect with the "feature" keyword
python -m bugbot.scripts.feature_but_type_defect --production

# Defect with the "meta" keyword
python -m bugbot.scripts.meta_defect --production

# Bugs with several duplicates
python -m bugbot.scripts.several_dups --production

# Bugs with a lot of cc
python -m bugbot.scripts.lot_of_cc --production

# Bugs with a lot of votes
python -m bugbot.scripts.lot_of_votes --production

# Bug caused several regressions recently reported
# Pretty rare
python -m bugbot.scripts.warn_regressed_by --production

# Defect starting with please or enable in the title
python -m bugbot.scripts.defect_with_please_or_enable --production

# Regressions without regressed_by and some dependencies (blocks, depends_on)
# Pretty rare
python -m bugbot.scripts.regression_without_regressed_by --production

# Bugs with a fuzzing bisection but without regressed_by
python -m bugbot.scripts.bisection_without_regressed_by --production

# Suggest components for untriaged bugs (daily, full list without confidence threshold)
python -m bugbot.scripts.component --frequency daily --production

# Try to detect potential wrong bug types using bugbug
python -m bugbot.scripts.defectenhancementtask --production

# Try to detect potential missing Has STR using bugbug
python -m bugbot.scripts.stepstoreproduce --production

# Unassign inactive bugs with the good-first-bug keyword
python -m bugbot.scripts.good_first_bug_unassign_inactive --production

# Look for missing bugzilla comments for recently-landed changesets
python -m bugbot.scripts.missed_landing_comment --production

# Look for recently landed changesets referencing leave-open security bugs
python -m bugbot.scripts.leave_open_sec --production

# Look for recent PDF.js updates that fix some bug
python -m bugbot.scripts.pdfjs_update --production

# Look for tracked bugs with a needinfo from a release manager
python -m bugbot.scripts.ni_from_manager --production

# Approve tracking request for bugs automatically filed for expiring telemetry probes
python -m bugbot.scripts.telemetry_expiry_tracking_autoapproval --production

# Needinfo triage owner on bugs assigned to inactive accounts
python -m bugbot.scripts.assignee_no_login --production

# Needinfo for bugs with inconsistent severity flags
python -m bugbot.scripts.severity_inconsistency --production

# Needinfo for bugs with underestimated severity levels
# python -m bugbot.scripts.severity_underestimated --production

# Needinfo for bugs with high security keywords whose set to low severity
python -m bugbot.scripts.severity_high_security --production

# Nag for components that need triage owner to be assigned
python -m bugbot.scripts.vacant_triage_owner --production

# Notify about bugs with needinfo requests on inactive users
python -m bugbot.scripts.inactive_ni_pending --production

# Confirm bugs with crash signatures
python -m bugbot.scripts.crash_signature_confirm --production

# Bugs with patches after being closed
# Disabled temporarily until fixing https://github.com/mozilla/relman-auto-nag/issues/1953
# python -m bugbot.scripts.patch_closed_bug --production

# Confirm bugs with affected flags
python -m bugbot.scripts.affected_flag_confirm --production

# Suggest increasing the severity for bugs with P1 WebCompat priority
python -m bugbot.scripts.severity_high_compat_priority --production

# Identify missing or inactive team managers
python -m bugbot.scripts.vacant_team_manager --production

# Highlight topcrash bugs
python -m bugbot.scripts.topcrash_highlight --production

# Notify about tracked bugs with no assignee, low severity, or low priority
python -m bugbot.scripts.tracked_attention --production

# Needinfo patch authors to find active reviewers
python -m bugbot.scripts.inactive_reviewer --production

# Nag on fuzz blocker bugs
python -m bugbot.scripts.fuzz_blockers --production

# Drop old severities
python -m bugbot.scripts.severity_migration --production

# Detect bugs with small crash volume
python -m bugbot.scripts.crash_small_volume --production

# Suggest increasing the severity when duplicate bugs have higher severity
python -m bugbot.scripts.severity_higher_dups --production

# Detect outdated triage owner rotation definitions
python -m bugbot.scripts.triage_rotations_outdated --production

# Follow up on expiring variants
python -m bugbot.scripts.variant_expiration --production

# Set nightly status to affected on newly filed regressions
python -m bugbot.scripts.regression_new_set_nightly_affected --production

# Suggest increasing the severity of performance-impacting bugs
python -m bugbot.scripts.severity_high_performance_impact --production

# Request potential missing info when a bug is moved to Core::Performance
python -m bugbot.scripts.moved_to_performance --production

source ./scripts/cron_common_end.sh
