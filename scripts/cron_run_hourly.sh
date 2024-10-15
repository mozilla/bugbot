#!/bin/bash

source ./scripts/cron_common_start.sh

# Bug fixed without assignee
# very common
python -m bugbot.rules.no_assignee --production

# Bug closed with the leave open keyword
# very common
python -m bugbot.rules.leave_open --production

# has a STR without flag has_str
# common
# python -m bugbot.rules.has_str_no_hasstr

# Closes crash bug without any crashes for the last 12 weeks
# pretty common
python -m bugbot.rules.no_crashes --production

# List bug with the meta keyword but not [meta] in the title
# Pretty common
python -m bugbot.rules.meta_summary_missing --production

# List bug without the meta keyword with [meta] in the title (with autofix)
# Pretty common
python -m bugbot.rules.summary_meta_missing --production

# List reopened bugs with invalid nightly status flag
# Pretty common
python -m bugbot.rules.nightly_reopened --production

# Bug closed with the stalled keyword
# Pretty rare
python -m bugbot.rules.stalled --production

# Bugs with missing beta status
# Pretty rare
python -m bugbot.rules.missing_beta_status --production

# File bugs for new actionable crashes
python -m bugbot.rules.file_crash_bug --production

# Try to detect potential regressions using bugbug
python -m bugbot.rules.regression --production

# Move info (signatures, product/component) from/to bugs & their dups
# Pretty common
python -m bugbot.rules.copy_duplicate_info --production

# Move dupeme from whiteboard to keyword
# Pretty rare
python -m bugbot.rules.dupeme_whiteboard_keyword --production

# Remove dupeme keyword when the bug is closed
# Pretty rare
python -m bugbot.rules.closed_dupeme --production

# Detect spam bugs using bugbug
python -m bugbot.rules.spambug --production

# Suggest components for untriaged bugs (hourly, list only bugs on which we acted)
python -m bugbot.rules.component --frequency hourly --production

# MUST ALWAYS BE AFTER COMPONENTS (to reset the priority if mandatory)
# Reset the priority if the product::component changed after the priority has been set
python -m bugbot.rules.prod_comp_changed_with_priority --production

# Run regression related rules
python -m bugbot.rules.multifix_regression --production

# Copy metadata from duplicates
python -m bugbot.rules.duplicate_copy_metadata --production

# Add `webcompat:platform-bug` keyword to bugs without a platform keyword
python -m bugbot.rules.webcompat_platform_without_keyword --production

# Add `[webcompat:sightline]` whiteboard entry to bugs in sightline metric set
python -m bugbot.rules.webcompat_sightline --production

source ./scripts/cron_common_end.sh
