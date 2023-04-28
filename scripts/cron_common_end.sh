#!/bin/bash

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m bugbot.log --send

deactivate

if [ "$errored" = true ]; then
    exit -1
fi
