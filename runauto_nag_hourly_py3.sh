#!/bin/bash
set -e

PATH_SCRIPT="$( cd "$(dirname "$0")" ; pwd -P )"
. "$PATH_SCRIPT"/venv3/bin/activate

cd "$PATH_SCRIPT"
if test ! -f auto_nag/scripts/configs/config.json; then
    echo "Cannot run without the config.json file in auto_nag/scripts/configs/"
    exit -1
fi

if test ! -f auto_nag/scripts/configs/people.json; then
    echo "Cannot run without the people.json file in auto_nag/scripts/configs/"
    exit -1
fi
export PYTHONPATH=.

# Clean the log files
python -m auto_nag.log --clean

# Suggest components for untriaged bugs (hourly, list only bugs on which we acted)
python -m auto_nag.scripts.component --frequency hourly

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send
