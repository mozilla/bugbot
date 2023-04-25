#!/bin/bash

source ./scripts/cron_common_start.sh

# Update the people.json file
python -m auto_nag.iam

# Code freeze week information for release managers
# Daily (but really runs during the soft freeze week)
python -m auto_nag.scripts.code_freeze_week -D yesterday --production

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

source ./scripts/cron_common_end.sh
