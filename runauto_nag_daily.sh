#!/bin/bash

export PYTHONPATH=.

./runauto_nag_common.sh

. venv/bin/activate

# force the update of dependencies
pip install -r requirements.txt

# Clean the log files
python -m auto_nag.log --clean

# Code freeze week information for release managers
# Daily (but really runs during the soft freeze week)
python -m auto_nag.scripts.code_freeze_week -D yesterday --production

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

deactivate

if [ "$errored" = true ]; then
    exit -1
fi
