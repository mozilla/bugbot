#!/bin/bash
set -e

./runauto_nag_common.sh
./runauto_nag_hourly_py2.sh
./runauto_nag_hourly_py3.sh
