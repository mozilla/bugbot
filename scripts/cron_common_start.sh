#!/bin/bash

git fetch --tags && git checkout $(curl -s https://api.github.com/repos/mozilla/bugbot/releases/latest | jq -r '.tag_name')

if test ! -f configs/config.json; then
    echo "Cannot run without the config.json file in /configs/"
    exit -1
fi

if test ! -f configs/people.json; then
    echo "Cannot run without the people.json file in /configs/"
    exit -1
fi

errored=false
ErrorHandler() {
    errored=true
}

trap ErrorHandler ERR

. .venv/bin/activate

# force the update of dependencies
uv sync --locked --no-dev

# Clean the log files
python -m bugbot.log --clean
