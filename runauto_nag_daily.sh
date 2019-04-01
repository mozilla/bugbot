#!/bin/bash
set -e

export PYTHONPATH=.

./runauto_nag_common.sh
./runauto_nag_daily_py2.sh
./runauto_nag_daily_py3.sh
