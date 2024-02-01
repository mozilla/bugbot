#!/bin/bash

source ./scripts/cron_common_start.sh

# Update the people.json file
python -m bugbot.iam

# Code freeze week information for release managers
# Daily (but really runs during the soft freeze week)
python -m bugbot.rules.code_freeze_week -D yesterday --production

# Detect accessibility-related bugs using accessibility model from bugbug
python -m bugbot.rules.accessibility --production

# Try to detect potential performance-related bugs using bugbug
python -m bugbot.rules.performancebug --production

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m bugbot.log --send

source ./scripts/cron_common_end.sh
