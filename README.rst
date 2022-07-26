.. image:: https://community-tc.services.mozilla.com/api/github/v1/repository/mozilla/relman-auto-nag/master/badge.svg
    :target: https://community-tc.services.mozilla.com/api/github/v1/repository/mozilla/relman-auto-nag/master/latest
.. image:: https://coveralls.io/repos/github/mozilla/relman-auto-nag/badge.svg
    :target: https://coveralls.io/github/mozilla/relman-auto-nag


This tool is used by Mozilla release management to send emails to the Firefox developers. It will query the bugzilla.mozilla.org database and send emails to Mozilla developers and their managers (if Mozilla staff).

The tool will also notify release managers about potential issues in bugzilla and autofix some categories of issues.

The list of checkers is documented on the Mozilla wiki:
https://wiki.mozilla.org/Release_Management/autonag


This package currently uses Mozilla's `Bugzilla REST API <https://wiki.mozilla.org/Bugzilla:REST_API>`_, and optionally the Mozilla IAM `phonebook <https://github.com/mozilla-iam/cis/blob/master/docs/PersonAPI.md>`_ (to access bug assignees' managers & Mozilla email addresses).


Installation
------------

#. Check out the code::

    git clone git://github.com/mozilla/relman-auto-nag.git

#. (optional) Create your virtualenv using virtualenvwrapper::

    virtualenv -p python3 venv
    source venv/bin/activate

#. Install pip::

    easy_install pip

#. Install the dependencies for Python 3 too::

    pip3 install -r requirements.txt


To run it into production, you will need the full list of employees + managers.

Automated Nagging Script
------------------------

Before running:

1. The LDAP + SMTP infos are used to send emails
2. Need to generate an API key from bugzilla admin ( https://bugzilla.mozilla.org/userprefs.cgi?tab=apikey )
3. Should generate an API key from Phabricator ( https://phabricator.services.mozilla.com/settings/user )
4. The IAM secrets are used to generate a dump of phonebook, which is required for some scripts (employees can request them by `filing a bug in the SSO: Requests component <https://bugzilla.mozilla.org/enter_bug.cgi?product=Infrastructure%20%26%20Operations&component=SSO%3A%20Requests>`_ )
5. The private entry contains URLs for private calendar in ICS format:

.. code-block:: json

    # in scripts/configs/config.json
    {
      "ldap_username": "xxx@xxxx.xxx",
      "ldap_password": "xxxxxxxxxxxxxx",
      "smtp_server": "smtp.xxx.xxx",
      "smtp_port": 314,
      "smtp_ssl": true,
      "bz_api_key": "xxxxxxxxxxxxxx",
      "phab_api_key": "xxxxxxxxxxxxxx",
      "iam_client_secret": "xxxxxxxxxxxxxx",
      "iam_client_id": "xxxxxxxxxxxxxx",
      "private":
      {
        "Core::General": "https://..."
      }
    }

Do a dryrun::
    python -m auto_nag.scripts.stalled -d

There is a ton of scripts in auto_nag/scripts/ so you should be able to find some good examples.

Setting up 'Round Robin' triage rotations
-----------------------------------------

One use case for this tool is managing triage of multiple components across a team of multiple people.

To set up a new Round Robin rotation, a manager or team lead should create a Google Calendar with the rotation of triagers.

Then the administrators will need to create a configuration file:

.. code-block:: json

    # in scripts/configs/<name of rotation>_round_robin.json
    {
        "fallback": "<Name of manager or lead>",
        "components":
        {
            "Product::Component": "default",
            "Product::Component": "default",
            …
        },
        "default":
        {
            "calendar": "private://<Name of calendar>"
        }
    }

The person requesting the round robin schedule must provide the URL of the calendar's `.ics` file.

In the calendar, the summary of the events must be the full name (eventually prefixed with text between square brackets) of triage owner as it appears in Phonebook, e.g. `[Gfx Triage] Foo Bar` or just `Foo Bar`.

And then you just have to add an entry in `auto_nag/scripts/config/tools.json <https://github.com/mozilla/relman-auto-nag/blob/333ec164ba5c3ceebf3c39cf84196fa35c667b1b/auto_nag/scripts/configs/tools.json#L2>`_ in the round-robin section.

Once everything is set-up you can make a PR similar too https://github.com/mozilla/relman-auto-nag/pull/858/files

Running on a server
-------------------

This needs to run on a private server because it will have login for smtp and bugzilla key so it can't currently be shared access.

Cronjob::

  00 17 * * 2 $HOME/relman-auto-nag/runauto_nag_tuesday.sh &> /tmp/autonag-tuesday.log
  00 7 * * 2 $HOME/relman-auto-nag/update_people.sh &> /tmp/autonag-people.log
  00 12 * * 1-5 $HOME/relman-auto-nag/run_autonags_daily.sh &> /tmp/autonag-day.log
  30 */1 * * * $HOME/relman-auto-nag/runauto_nag_hourly.sh &> /tmp/autonag-hour.log
