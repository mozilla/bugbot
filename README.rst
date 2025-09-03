.. image:: https://community-tc.services.mozilla.com/api/github/v1/repository/mozilla/bugbot/master/badge.svg
    :target: https://community-tc.services.mozilla.com/api/github/v1/repository/mozilla/bugbot/master/latest
.. image:: https://coveralls.io/repos/github/mozilla/bugbot/badge.svg
    :target: https://coveralls.io/github/mozilla/bugbot


This tool is used by Mozilla release management to send emails to the Firefox developers. It will query the bugzilla.mozilla.org database and send emails to Mozilla developers and their managers (if Mozilla staff).

The tool will also notify release managers about potential issues in bugzilla and autofix some categories of issues.

The list of checkers is documented on the Mozilla wiki:
https://wiki.mozilla.org/BugBot

This package currently uses Mozilla's `Bugzilla REST API <https://wiki.mozilla.org/Bugzilla:REST_API>`_, and the Mozilla IAM `phonebook <https://github.com/mozilla-iam/cis/blob/master/docs/PersonAPI.md>`_ (to access bug assignees' managers & Mozilla email addresses).


Installation
------------

#. Check out the code::

    git clone https://github.com/mozilla/bugbot.git

bugbot uses `uv <https://docs.astral.sh/uv/>`_ to manage the Python environment; this must be installed locally.

Auto-formatting with pre-commit
-------------------------------

This project uses `pre-commit <https://pre-commit.com/>`_.

#. Install pre-commit::

    uv tool install pre-commit

Every time you try to commit, pre-commit checks your files to ensure they follow our style standards and aren't affected by some simple issues. If the checks fail, pre-commit won't let you commit.

Running the Bot Rules
---------------------

Before running:

1. The LDAP + SMTP infos are used to send emails
2. Need to generate an API key from bugzilla admin ( https://bugzilla.mozilla.org/userprefs.cgi?tab=apikey )
3. Should generate an API key from Phabricator ( https://phabricator.services.mozilla.com/settings/user )
4. The IAM secrets are used to generate a dump of phonebook, which is required for some scripts (employees can request them by `filing a bug in the SSO: Requests component <https://bugzilla.mozilla.org/enter_bug.cgi?product=Infrastructure%20%26%20Operations&component=SSO%3A%20Requests>`_ )

.. code-block:: json

    # in configs/config.json
    {
      "ldap_username": "xxx@xxxx.xxx",
      "ldap_password": "xxxxxxxxxxxxxx",
      "smtp_server": "smtp.xxx.xxx",
      "smtp_port": 314,
      "smtp_ssl": true,
      "bz_api_key": "xxxxxxxxxxxxxx",
      "bz_api_key_nomail": "xxxxxxxxxxxxxx",
      "phab_api_key": "xxxxxxxxxxxxxx",
      "iam_client_secret": "xxxxxxxxxxxxxx",
      "iam_client_id": "xxxxxxxxxxxxxx",
      "socorro_token": "xxxxxxxxxxxxxx"
    }

Do a dryrun::

   uv run -m bugbot.rules.stalled

There is a ton of rules in bugbot/rules/ so you should be able to find some good examples.

Setting up 'Round Robin' triage rotations
-----------------------------------------

One use case for this tool is managing triage of multiple components across a team of multiple people.

To set up a new Round Robin rotation, a manager or team lead should create a calendar with the rotation of triagers and add a link to the rotation calendar in the `triage rotations spreadsheet <https://docs.google.com/spreadsheets/d/1EK6iCtdD8KP4UflIHscuZo6W5er2vy_TX7vsmaaBVd4>`_.


Running on a server
-------------------

This needs to run on a private server because it will have login for smtp and bugzilla key so it can't currently be shared access.

Cronjob::

    CRON_DIR=/path/to/repository
    00 12  * * 1-5 cd $CRON_DIR ; ./cron_run_weekdays.sh &> /tmp/bugbot-weekdays.log
    00 8   * * *   cd $CRON_DIR ; ./cron_run_daily.sh    &> /tmp/bugbot-daily.log
    40 */1 * * *   cd $CRON_DIR ; ./cron_run_hourly.sh   &> /tmp/bugbot-hourly.log


We run hourly jobs at minute 40 past every hour to avoid overlap with daily jobs.
