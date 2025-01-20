#!/bin/bash

source ./scripts/cron_common_start.sh

# Update the people.json file
python -m bugbot.iam

# Code freeze week information for release managers
# Daily (but really runs during the soft freeze week)
python -m bugbot.rules.code_freeze_week -D yesterday --production

# Detect accessibility-related bugs using accessibility model from bugbug
python -m bugbot.rules.accessibilitybug --production

# Try to detect potential performance-related bugs using bugbug
python -m bugbot.rules.performancebug --production

# Try to detect potential performance alerts that have been inactive for too long
python -m bugbot.rules.perfalert_inactive_regression --production

# Send an email about all performance alerts who were recently resolved
python -m bugbot.rules.perfalert_resolved_regression --production

# Update the webcompat score fields
python -m bugbot.rules.webcompat_score --production

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m bugbot.log --send

source ./scripts/cron_common_end.sh
