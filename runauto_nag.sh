#!/bin/bash
PATH_SCRIPT="$( cd "$(dirname "$0")" ; pwd -P )"
. $PATH_SCRIPT/venv/bin/activate
cd $PATH_SCRIPT
python -m auto_nag.scripts.query_creator
python -m auto_nag.scripts.rm_query_creator
python -m auto_nag.scripts.no_assignee
