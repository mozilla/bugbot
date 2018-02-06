# If relman-auto-nag not installed, add project root directory into
# PYTHONPATH
import os
import inspect
import sys
currentdir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(currentdir))
sys.path.insert(0, project_root)
from auto_nag.bugzilla import utils

utils.get_credentials()
