#!/bin/bash
set -e

. venv3/bin/activate

# Clean the log files
python -m auto_nag.log --clean

# Suggest components for untriaged bugs (hourly, list only bugs on which we acted)
python -m auto_nag.scripts.component --frequency hourly

# MUST ALWAYS BE AFTER COMPONENTS (to reset the priority if mandatory)
# Reset the priority if the product::component changed after the priority has been set
python -m auto_nag.scripts.prod_comp_changed_with_priority

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m auto_nag.log --send

deactivate
