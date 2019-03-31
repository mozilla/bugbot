#!/bin/bash
set -e

PATH_SCRIPT="$( cd "$(dirname "$0")" ; pwd -P )"
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
