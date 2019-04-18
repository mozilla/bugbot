#!/bin/bash
set -e

. venv3/bin/activate

# force the update of dependencies
pip install  -r requirements.txt

# Clean the log files
python -m auto_nag.log --clean

# Try to detect potential regressions using bugbug
python -m auto_nag.scripts.regression

# Suggest components for untriaged bugs (daily, full list without confidence threshold)
python -m auto_nag.scripts.component --frequency daily

# Try to detect potential wrong bug types using bugbug
python -m auto_nag.scripts.defectenhancementtask

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

deactivate
