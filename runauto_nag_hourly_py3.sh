#!/bin/bash
set -e

. venv3/bin/activate

# Clean the log files
python -m auto_nag.log --clean

# Suggest components for untriaged bugs (hourly, list only bugs on which we acted)
python -m auto_nag.scripts.component --frequency hourly

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

deactivate
