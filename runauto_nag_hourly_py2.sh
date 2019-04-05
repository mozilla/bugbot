#!/bin/bash
set -e

. venv2/bin/activate

# Clean the log files
python -m auto_nag.log --clean

# Bug fixed without assignee
# very common
python -m auto_nag.scripts.no_assignee

# Bug closed with the leave open keyword
# very common
python -m auto_nag.scripts.leave_open

# has a STR without flag has_str
# common
# python -m auto_nag.scripts.has_str_no_hasstr

# Closes crash bug without any crashes for the last 12 weeks
# pretty common
python -m auto_nag.scripts.no_crashes

# Unconfirmed bugs with an assignee (with autofix)
# Pretty common
python -m auto_nag.scripts.assignee_but_unconfirmed

# List bug with the meta keyword but not [meta] in the title
# Pretty common
python -m auto_nag.scripts.meta_summary_missing

# List bug without the meta keyword with [meta] in the title (with autofix)
# Pretty common
python -m auto_nag.scripts.summary_meta_missing

# List reopened bugs with invalid nightly status flag
# Pretty common
python -m auto_nag.scripts.nightly_reopened

# Bug closed with the stalled keyword
# Pretty rare
python -m auto_nag.scripts.stalled

# Bugs with missing beta status
# Pretty rare
python -m auto_nag.scripts.missing_beta_status

# Bugs with STR and no regression-range
# Pretty rare
python -m auto_nag.scripts.has_str_no_range

# Notify bugs tracked (+ or blocking)
# with P3, P4 or P5 priorities for the ongoing releases
# Pretty common
python -m auto_nag.scripts.mismatch-priority-tracking-esr
python -m auto_nag.scripts.mismatch-priority-tracking-release
python -m auto_nag.scripts.mismatch-priority-tracking-beta
python -m auto_nag.scripts.mismatch-priority-tracking-nightly

# Bug is tracked for a release but the bug severity is small
# pretty common
python -m auto_nag.scripts.tracked_bad_severity

# Move info (signatures, product/component) from/to bugs & their dups
# Pretty common
python -m auto_nag.scripts.copy_duplicate_info

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

deactivate
