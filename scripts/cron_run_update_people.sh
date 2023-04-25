#!/bin/bash
set -e

export PYTHONPATH=.

./scripts/cron_common_start.sh

. venv/bin/activate

# force the update of dependencies
pip install -r requirements.txt

# Clean the log files
python -m auto_nag.log --clean

# Try to detect potential wrong bug types using bugbug
python -m auto_nag.iam

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

deactivate
