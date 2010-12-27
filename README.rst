This package defines `remoteobjects`_ models and some scripts for all the
resources provided in `Gervase Markham's`_ Bugzilla `REST API`_.  Right now it's
pretty damn slow.  I hope that will change.

.. _remoteobjects: http://sixapart.github.com/remoteobjects/
.. _Gervase Markham's: http://weblogs.mozillazine.org/gerv/
.. _REST API: https://wiki.mozilla.org/Bugzilla:REST_API


Installation
------------

Currently, this package depends on a pre-release version of remoteobjects, so
we'll have to do this the long way.

#. Check out the code::

    git clone git://github.com/LegNeato/bztools.git

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
