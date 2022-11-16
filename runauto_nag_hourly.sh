#!/bin/bash

export PYTHONPATH=.

./runauto_nag_common.sh

. venv/bin/activate

# Clean the log files
python -m auto_nag.log --clean

# Bug fixed without assignee
# very common
python -m auto_nag.scripts.no_assignee --production

# Bug closed with the leave open keyword
# very common
python -m auto_nag.scripts.leave_open --production

# has a STR without flag has_str
# common
# python -m auto_nag.scripts.has_str_no_hasstr

# Closes crash bug without any crashes for the last 12 weeks
# pretty common
python -m auto_nag.scripts.no_crashes --production

# List bug with the meta keyword but not [meta] in the title
# Pretty common
python -m auto_nag.scripts.meta_summary_missing --production

# List bug without the meta keyword with [meta] in the title (with autofix)
# Pretty common
python -m auto_nag.scripts.summary_meta_missing --production

# List reopened bugs with invalid nightly status flag
# Pretty common
python -m auto_nag.scripts.nightly_reopened --production

# Bug closed with the stalled keyword
# Pretty rare
python -m auto_nag.scripts.stalled --production

# Bugs with missing beta status
# Pretty rare
python -m auto_nag.scripts.missing_beta_status --production

# Try to detect potential regressions using bugbug
python -m auto_nag.scripts.regression --production

# Bugs with STR and no regression-range
# Pretty rare
python -m auto_nag.scripts.has_str_no_range --production

# Move info (signatures, product/component) from/to bugs & their dups
# Pretty common
python -m auto_nag.scripts.copy_duplicate_info --production

# Move dupeme from whiteboard to keyword
# Pretty rare
python -m auto_nag.scripts.dupeme_whiteboard_keyword --production

# Remove dupeme keyword when the bug is closed
# Pretty rare
python -m auto_nag.scripts.closed_dupeme --production

# Detect spam bugs using bugbug
python -m auto_nag.scripts.spambug --production

# Suggest components for untriaged bugs (hourly, list only bugs on which we acted)
python -m auto_nag.scripts.component --frequency hourly --production

# MUST ALWAYS BE AFTER COMPONENTS (to reset the priority if mandatory)
# Reset the priority if the product::component changed after the priority has been set
python -m auto_nag.scripts.prod_comp_changed_with_priority --production

# Run regression related tools
python -m auto_nag.scripts.multifix_regression --production

# Copy metadata from duplicates
python -m auto_nag.scripts.duplicate_copy_metadata --production

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

deactivate

if [ "$errored" = true ] ; then
    exit -1
fi
