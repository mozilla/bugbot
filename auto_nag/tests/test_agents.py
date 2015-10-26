
try:
    # If relman-auto-nag is installed
    from bugzilla.agents import BMOAgent
    from bugzilla.utils import os
    from bugzilla.utils import get_config_path
except:
    # If relman-auto-nag not installed, add project root directory into
    # PYTHONPATH
    import os
    import sys
    import inspect
    currentdir = os.path.dirname(os.path.abspath(
                                 inspect.getfile(inspect.currentframe())))
    parentdir = os.path.dirname(currentdir)
    sys.path.insert(0, parentdir)
    from bugzilla.agents import BMOAgent
    from bugzilla.utils import os
    from bugzilla.utils import get_config_path

import json
from nose.tools import *

class TestAgent:
    config = None

    def setUp(self):
        CONFIG_JSON = get_config_path()
        with open(CONFIG_JSON, 'r') as config:
            self.config = json.load(config)


    # Test bugzilla agent methods
    def test_get_bug_list(self):
        # Set whatever REST API options we want
        options = {
            'changed_after':    ['2012-12-24'],
            'changed_before':   ['2012-12-27'],
            'changed_field':    ['status'],
            'changed_field_to': ['RESOLVED'],
            'product':          ['Firefox'],
            'resolution':       ['FIXED'],
            'include_fields':   ['attachments'],
        }
        # Load our agent for BMO
        bmo = BMOAgent(self.config['bz_api_key'])
        # Get the bugs from the api
        buglist = bmo.get_bug_list(options)
        assert buglist != []


    def test_get_bug(self):
        # Load our agent for BMO
        bmo = BMOAgent(self.config['bz_api_key'])
        # Get the bugs from the api
        bug = bmo.get_bug(656222)
        assert bug != []


    @raises(Exception)
    def test_get_bug_list_wrng_api_k(self):
        """ Wrong API Key, it should raise an Error"""
        # Set whatever REST API options we want
        options = {
            'changed_after':    ['2012-12-24'],
            'changed_before':   ['2012-12-27'],
            'changed_field':    ['status'],
            'changed_field_to': ['RESOLVED'],
            'product':          ['Firefox'],
            'resolution':       ['FIXED'],
            'include_fields':   ['attachments'],
        }
        # Load our agent for BMO
        bmo = BMOAgent('wrong_api_key_test')
        # Get the bugs from the api
        bmo.get_bug_list(options)


    @raises(Exception)
    def test_get_bug_wrng_api_k(self):
        """ Wrong API Key, it should raise an Error"""
        # Load our agent for BMO
        bmo = BMOAgent('wrong_api_key_test')
        # Get the bugs from the api
        bug = bmo.get_bug(656222)
        print bug
