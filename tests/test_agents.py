from bugzilla.agents import BMOAgent
from bugzilla.utils import os, json

import json
from nose.tools import *

CONFIG_JSON = os.path.abspath(os.path.join(os.getcwd(), '..',
                              'scripts/configs/config.json'))
config = json.load(open(CONFIG_JSON, 'r'))


# Test bugzilla agent methods
def test_get_bug_list():
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
    bmo = BMOAgent(config['bz_api_key'])
    # Get the bugs from the api
    buglist = bmo.get_bug_list(options)
    assert buglist != []


def test_get_bug():
    # Load our agent for BMO
    bmo = BMOAgent(config['bz_api_key'])
    # Get the bugs from the api
    bug = bmo.get_bug(656222)
    assert bug != []


@raises(Exception)
def test_get_bug_list_wrng_api_k():
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
def test_get_bug_wrng_api_k():
    """ Wrong API Key, it should raise an Error"""
    # Load our agent for BMO
    bmo = BMOAgent('wrong_api_key_test')
    # Get the bugs from the api
    bug = bmo.get_bug(656222)
    print bug
