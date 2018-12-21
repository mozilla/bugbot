This tool is used by Mozilla release management to send emails to the Firefox developers. It will query the bugzilla.mozilla.org database and send emails to Mozilla developers and their managers (if Mozilla staff).
The tool will also notify release managers about potential issues in bugzilla and autofix some categories of issues.

This package currently uses `remoteobjects <https://github.com/saymedia/remoteobjects>`_ models, Mozilla's `Bugzilla REST API <https://wiki.mozilla.org/Bugzilla:REST_API>`_, and optionally the Mozilla LDAP `phonebook <https://github.com/mozilla/mobile-phonebook>`_ (to access bug assignees' managers & Mozilla email addresses).


Installation
------------

Currently, this package depends on a pre-release version of remoteobjects, so
we'll have to do this the long way.

#. Check out the code::

    git clone git://github.com/mozilla/relman-auto-nag.git

#. (optional) Create your virtualenv using virtualenvwrapper::

    virtualenv --no-site-packages venv

#. Install pip::

    easy_install pip

#. Install the dependencies for bztools::

    pip install -r requirements.txt

#. Install the dependencies for Python 3 too::

    pip3 install -r requirements.txt

#. Run setup.py so the scripts are installed to your bin directory::

    python setup.py install

Note to developers: if you make any changes to the bugzilla/ files (agents, models, utils) during
work on other scripts, you will want to re-install the scripts as instructed above in order to pick
up changes

To run it into production, you will need the full list of employees + managers.

Usage
----------

Example::

    from auto_nag.bugzilla.agents import BMOAgent

    # We can use "None" for both instead to not authenticate
    api_key = 'xxx'

    # Load our agent for BMO
    bmo = BMOAgent(api_key)

    # Set whatever REST API options we want
    options = {
        'changed_after':    ['2010-12-24'],
        'changed_before':   ['2010-12-26'],
        'changed_field':    ['status'],
        'changed_field_to': ['RESOLVED'],
        'product':          ['Core,Firefox'],
        'resolution':       ['FIXED'],
        'include_fields':   ['_default,attachments'],
    }

    # Get the bugs from the api
    buglist = bmo.get_bug_list(options)

    print "Found %s bugs" % (len(buglist))

    for bug in buglist:
        print bug

Query Creator, Automated Nagging Script
---------------------------------------

Before running::

1. You'll need to create a writeable 'queries' directory at the top level of the checkout where the script is run from.
2. Need a local config for phonebook auth with your LDAP info
3. Need to generate an API key from bugzilla admin ( https://bugzilla.mozilla.org/userprefs.cgi?tab=apikey )

.. code-block:: bash

    # in scripts/configs/config.json
    {
      "ldap_username": "you@mozilla.com",
      "ldap_password": "xxxxxxxxxxxxxx",
      "bz_api_key": "xxxxxxxxxxxxxx"
    }

Do a dryrun::
    python auto_nag/scripts/query_creator.py -d

The script does the following:
* you will need a local config for smtp auth with your LDAP info::
    # in scripts/configs/config.json
    {
        "ldap_username": "you@mozilla.com",
        "ldap_password": "xxxxxxxxxxxxxx",
        "bz_api_key": "xxxxxxxxxxxxxx"
    }
* Creates queries based on the day of the week the script is run
* Polls the bugzilla API with each query supplied and builds a dictionary of bugs found per query
* For each bug, finds the assignee and if possible the assignee's manager - then adds the bug to the manager's bug bucket for later email notification
* Goes through the manager dictionary and constructs an email with the bugs assigned to that manager's team members
* Outputs the message to console and waits for use input to either send/edit/cancel (save for manual notification)
* At the end it provides a list of all bugs that were not emailed about and provides the url for bugzilla of that buglist


Running on a server
-------------------

This needs to run on a private server because it will have login for smtp and bugzilla key so it can't currently be shared access.

Cronjob::
  00 14 * * 1-5 $HOME/run_autonags.sh > $HOME/logs/user/autonag.log


Running the testsuite
---------------------

.. code-block:: bash

    tox -e py27
