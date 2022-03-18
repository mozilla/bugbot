#!/bin/bash
set -e

export PYTHONPATH=.

./runauto_nag_common.sh

. venv/bin/activate

# force the update of dependencies
pip install -r requirements.txt

# Clean the log files
python -m auto_nag.log --clean

# Close inactive intermittent bugs
python -m auto_nag.scripts.survey_sec_bugs --production

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

deactivate
