This package currently uses `remoteobjects`_ models, Mozilla's `_ Bugzilla `REST API`_, and optionally the Mozilla LDAP `phonebook`_ (to access bug assignees' managers & Mozilla email addresses).

.. _remoteobjects: http://sixapart.github.com/remoteobjects/
.. _REST API: https://wiki.mozilla.org/Bugzilla:REST_API
.. _phonebook: https://github.com/mozilla/mobile-phonebook


Installation
------------

Currently, this package depends on a pre-release version of remoteobjects, so
we'll have to do this the long way.

#. Check out the code::

    git clone git://github.com/mozilla/bztools.git

#. (optional) Create your virtualenv using virtualenvwrapper::

    mkvirtualenv --no-site-packages bztools

#. Install pip::

    easy_install pip

#. Install the dependencies for bztools::

    pip install -r requirements.txt

#. Run setup.py so the scripts are installed to your bin directory::

    python setup.py install


Now you'll have ``bzattach`` installed in the ``/bin`` directory of your
virtual environment.  To use the script, you'll have to activate this
environment with ``workon bztools``.

Note to developers: if you make any changes to the bugzilla/ files (agents, models, utils) during
work on other scripts, you will want to re-install the scripts as instructed above in order to pick
up changes

Usage 
----------

Example::

    from bugzilla.agents import BMOAgent
    from bugzilla.utils import get_credentials

    # We can use "None" for both instead to not authenticate
    username, password = get_credentials()

    # Load our agent for BMO
    bmo = BMOAgent(username, password)

    # Set whatever REST API options we want
    options = {
        'changed_after':    '2010-12-24',
        'changed_before':   '2010-12-26',
        'changed_field':    'status',
        'changed_field_to': 'RESOLVED',
        'product':          'Core,Firefox',
        'resolution':       'FIXED',
        'include_fields':   '_default,attachments',
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
2. you will need a local config for phonebook auth with your LDAP info::
    # in scripts/configs/config.json
    {
        "ldap_username": "you@mozilla.com",
        "ldap_password": "xxxxxxxxxxxxxx"
    }
    
Do a dryrun::
    python scripts/query_creator.py -d

The script does the following:
* Gathers the current list of employees and managers from Mozilla LDAP phonebook 
* Creates queries based on the day of the week the script is run
* Polls the bugzilla API with each query supplied and builds a dictionary of bugs found per query
* For each bug, finds the assignee and if possible the assignee's manager - then adds the bug to the manager's bug bucket for later email notification
* Goes through the manager dictionary and contructs an email with the bugs assigned to that manager's team members
* Outputs the message to console and waits for use input to either send/edit/cancel (save for manual notification)
* At the end it provides a list of all bugs that were not emailed about and provides the url for bugzilla of that buglist


Running on a server
-------------------

This needs to run on a private server because it will have both logins for Bugzilla and LDAP so it can't currently be shared access.
I run this on WebFaction with a wrapper script, virtualenv, and a cronjob:

Cronjob::
  00 14 * * 1-5 $HOME/bin/run_autonags.sh > $HOME/logs/user/autonag.log

Shell script::

  #!/bin/bash
  source $HOME/.virtualenvs/bztools/bin/activate
  cd $HOME/bztools
  /usr/local/bin/python $HOME/bztools/scripts/query_creator.py
    

When you change your Bugzilla password you need to change it in the virtualenv keyring as follows::

  python
  import keyring
  keyring.set_password("bugzilla", "username", "password") # using your username and password
  keyring.get_password("bugzilla", "username")  # should confirm the new password
  exit()
  deactivate
    
Then test a dry-run of the crontjob again (with or without the redirect to logs) to make sure the script runs through.
