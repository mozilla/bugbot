# If relman-auto-nag not installed, add project root directory into
# PYTHONPATH
import os
import inspect
import sys
currentdir = os.path.dirname(os.path.abspath(
                             inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
util_dir = parentdir + '/bugzilla'
sys.path.insert(0, util_dir)
import utils

utils.get_credentials()
