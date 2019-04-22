# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag.bzcleaner import BzCleaner

#https://bugzilla.mozilla.org/buglist.cgi?bug_type=defect&list_id=14677864&short_desc_type=regexp&short_desc=%5Eplease&resolution=---&classification=Client%20Software&classification=Developer%20Infrastructure&classification=Components&classification=Server%20Software&classification=Other&query_format=advanced

class DefectWithPlease(BzCleaner):
    def __init__(self):
        super(DefectWithPlease, self).__init__()

    def description(self):
        return "Defect with description starting with 'Please'"

    def ignore_date(self):
        return True

    def get_bz_params(self, date):
        params = {
            "resolution": "---",
            "short_desc": r'^please',
            "short_desc_type": "regexp",
            "bug_type": ["defect"],
        }
        return params


if __name__ == "__main__":
    DefectWithPlease().run()
