#!/bin/bash

export PYTHONPATH=.

./runauto_nag_common.sh

. venv/bin/activate

# force the update of dependencies
pip install -r requirements.txt

# Clean the log files
python -m auto_nag.log --clean

# Not up-to-date release date
# Daily
python -m auto_nag.next_release

# Code freeze week information for release managers
# Daily (but really runs during the soft freeze week)
python -m auto_nag.scripts.code_freeze_week -D yesterday

# Send a todo list to set priority
# Daily
python -m auto_nag.scripts.to_triage

# Nag triage fallback to update calendar
# Daily
python -m auto_nag.round_robin_fallback

# Needinfo assignee when a patch could be uplifted to beta
# Daily
python -m auto_nag.scripts.uplift_beta

# What is fixed in nightly but affecting beta or release
# Daily
python -m auto_nag.scripts.missed_uplifts

# Top crash with an incorrect severity
# Pretty rare
python -m auto_nag.scripts.topcrash_bad_severity

# Bug with both the regression and feature keywords
# Pretty rare
python -m auto_nag.scripts.feature_regression

# Detect one word summary
# a bit rare
python -m auto_nag.scripts.one_two_word_summary

# Bugs where the reporter has a needinfo
# Pretty common
python -m auto_nag.scripts.reporter_with_ni

# Notify bugs in untriaged with an important severity
python -m auto_nag.scripts.untriage_important_sev

# Needinfo the assignee or the triage owner when a bug has leave-open keyword an no activty
# Pretty common
python -m auto_nag.scripts.leave_open_no_activity

# Needinfo the triage owner or the assignee when we find meta bugs not depending on bugs and no activity
# Pretty common
python -m auto_nag.scripts.meta_no_deps_no_activity

# Several tools here
#  1) has an unlanded patch or some flags not up-to-date
#     Pretty rare
#  2) Tracked bugs
#  3) Tracked bugs with needinfos
python -m auto_nag.scripts.multi_nag

# has a r+ patch, is open, has no activity for few weeks
# Pretty common
python -m auto_nag.scripts.not_landed

# New workflow
# https://docs.google.com/document/d/1EHuWa-uR-7Sq63X1ZiDN1mvJ9gQtWiqYrCifkySJyW0/edit#
# https://docs.google.com/drawings/d/1oZA-AUvkOxGMNhZNofL8Wlfk6ol3o5ATQCV5DJJKbwM/edit
python -m auto_nag.scripts.workflow.multi_nag

# Defect or task with the "feature" keyword
python -m auto_nag.scripts.feature_but_type_defect_task

# Defect with the "meta" keyword
python -m auto_nag.scripts.meta_defect

# reporter has a needinfo and no activity for the last X weeks
# Pretty common
python -m auto_nag.scripts.newbie_with_ni -d

# Bug caused several regressions recently reported
# Pretty rare
python -m auto_nag.scripts.warn_regressed_by

# Defect starting with please or enable in the title
python -m auto_nag.scripts.defect_with_please_or_enable

# Regressions without regressed_by and some dependencies (blocks, depends_on)
# Pretty rare
python -m auto_nag.scripts.regression_without_regressed_by

# Try to detect potential regressions using bugbug
python -m auto_nag.scripts.regression

# Suggest components for untriaged bugs (daily, full list without confidence threshold)
python -m auto_nag.scripts.component --frequency daily

# Try to detect potential wrong bug types using bugbug
python -m auto_nag.scripts.defectenhancementtask

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

# Try to detect potential missing Has STR using bugbug
python -m auto_nag.scripts.stepstoreproduce

deactivate

if [ "$errored" = true ] ; then
    exit -1
fi
