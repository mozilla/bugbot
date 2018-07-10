# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from auto_nag.scripts.regression import Regression


class TestRegression:

    def test_find_bug_reg(self):
        r = Regression()
        
        com = """Comment on attachment 8969768 [details]
Bug 1455726: Disable emails to release+tcstaging.

Approval Request Comment
[Feature/Bug causing the regression]: 1455678
[User impact if declined]:
[Is this code covered by automated tests?]: no
[Has the fix been verified in Nightly?]: n/a
[Needs manual test from QE? If yes, steps to reproduce]: no
[List of other uplifts needed for the feature/fix]: no
[Is the change risky?]: no
[Why is the change risky/not risky?]: only impacts staging releases
[String changes made/needed]: no"""

        assert r.find_bug_reg(com) == '1455678'

        com = """Comment on attachment 8969768 [details]
Bug 1455726: Disable emails to release+tcstaging.

Approval Request Comment
[Feature/Bug causing the regression]: foobar 1455678
[User impact if declined]:
[Is this code covered by automated tests?]: no
[Has the fix been verified in Nightly?]: n/a
[Needs manual test from QE? If yes, steps to reproduce]: no
[List of other uplifts needed for the feature/fix]: no
[Is the change risky?]: no
[Why is the change risky/not risky?]: only impacts staging releases
[String changes made/needed]: no"""

        assert r.find_bug_reg(com) == ''

        com = """Comment on attachment 8969768 [details]
Bug 1455726: Disable emails to release+tcstaging.

Approval Request Comment
[Feature/Bug causing the regression]: bug 1455678
[User impact if declined]:
[Is this code covered by automated tests?]: no
[Has the fix been verified in Nightly?]: n/a
[Needs manual test from QE? If yes, steps to reproduce]: no
[List of other uplifts needed for the feature/fix]: no
[Is the change risky?]: no
[Why is the change risky/not risky?]: only impacts staging releases
[String changes made/needed]: no"""

        assert r.find_bug_reg(com) == '1455678'
