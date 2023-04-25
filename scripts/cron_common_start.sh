#!/bin/bash

PATH_SCRIPT="$( cd "$(dirname "$0")/.." ; pwd -P )"
cd "$PATH_SCRIPT"

export PYTHONPATH="$(pwd)"

if test ! -f auto_nag/scripts/configs/config.json; then
    echo "Cannot run without the config.json file in auto_nag/scripts/configs/"
    exit -1
fi

if test ! -f auto_nag/scripts/configs/people.json; then
    echo "Cannot run without the people.json file in auto_nag/scripts/configs/"
    exit -1
fi

errored=false
ErrorHandler () {
    errored=true
}

trap ErrorHandler ERR

. venv/bin/activate

# force the update of dependencies
pip install -r requirements.txt

# Clean the log files
python -m auto_nag.log --clean
