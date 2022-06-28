# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from . import mail, utils
from .round_robin import RoundRobin


def send_mail(err, dryrun=False):
    for fb, bzmails in err.items():
        mail.send_from_template(
            "erroneous_bzmail_email.html",
            fb,
            "Triage owners with erroneous Bugzilla email",
            Cc=utils.get_receivers("common"),
            dryrun=dryrun,
            bzmails=bzmails,
            plural=utils.plural,
        )


def check_erroneous_bzmail(dryrun=False):
    rr = RoundRobin.get_instance()
    err = rr.get_erroneous_bzmail()
    if err:
        send_mail(err, dryrun=dryrun)
