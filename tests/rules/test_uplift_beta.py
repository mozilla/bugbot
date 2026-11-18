# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from libmozdata.bugzilla import Bugzilla as RealBugzilla

from bugbot.bzcleaner import BzCleaner
from bugbot.rules import uplift_beta
from bugbot.rules.uplift_beta import UpliftBeta

VERSIONS = {"central": 146, "beta": 145, "release": 144, "esr": 140}

# Thresholds covering all kinds of entries, independently of the configured
# ones: S3 with a `fix-optional` threshold, S4 setting it at any time, and S5
# (not a real severity) never setting `wontfix`.
DAYS_TO_RELEASE = {
    "S3": {"fix-optional": 7, "wontfix": 3},
    "S4": {"fix-optional": None, "wontfix": 5},
    "S5": {"fix-optional": 7},
}

REGRESSION_ID = 456


@pytest.fixture
def configured_rule(monkeypatch):
    def init_versions(self):
        self.versions = VERSIONS
        return True

    monkeypatch.setattr(BzCleaner, "init_versions", init_versions)
    rule = UpliftBeta()
    rule.days_to_release = 20
    return rule


@pytest.fixture
def rule(configured_rule):
    configured_rule.low_severity_days_to_release = DAYS_TO_RELEASE
    return configured_rule


def _bug(**overrides):
    return {
        "id": 123,
        "summary": "Bug 123",
        "groups": [],
        "severity": "S3",
        "assigned_to": "dev@example.com",
        "assigned_to_detail": {"nick": "dev"},
        "regressions": [],
        "flags": [],
        "attachments": [],
        "cf_status_firefox145": "affected",
        "cf_status_firefox_esr140": "unaffected",
        **overrides,
    }


def _run(monkeypatch, rule, bug, regression_status="RESOLVED", risks={}):
    """Run the rule on a single bug.

    `risks` is what `get_risks` returns, it can be an exception to raise.

    Return the bugs left for the email, and the change applied to the bug.
    """

    def get_risks(self, bugs):
        if isinstance(risks, Exception):
            raise risks
        return risks

    def get_bugs(self, date="today", bug_ids=[], chunk_size=None):
        data = {}
        self.handle_bug(bug, data)
        return data

    class Bugzilla:
        def __init__(self, bugids, include_fields, bughandler, bugdata):
            for bugid in bugids:
                bughandler({"id": bugid, "status": regression_status}, bugdata)

        def get_data(self):
            return self

        def wait(self):
            pass

    monkeypatch.setattr(BzCleaner, "get_bugs", get_bugs)
    monkeypatch.setattr(UpliftBeta, "get_risks", get_risks)
    monkeypatch.setattr(uplift_beta, "Bugzilla", Bugzilla)
    bugs = rule.get_bugs()
    rule.apply_autofix = False
    rule.autofix(bugs)
    return bugs, rule.autofix_changes.get("123", {})


def _assert_beta_asked(bugs, change):
    assert bugs["123"]["channels"] == ["beta"]
    assert "cf_status_firefox145" not in change
    assert change["flags"][0]["requestee"] == "dev@example.com"


@pytest.mark.parametrize(
    "severity, days_to_release, status, expected",
    [
        # Severities without thresholds are always asked.
        ("S2", 1, "affected", None),
        ("--", 1, "affected", None),
        # S3 bugs are asked until a week before the release.
        ("S3", 20, "affected", None),
        ("S3", 8, "fix-optional", None),
        ("S3", 7, "affected", "fix-optional"),
        ("S3", 4, "affected", "fix-optional"),
        ("S3", 3, "affected", "wontfix"),
        ("S3", 3, "fix-optional", "wontfix"),
        # S4 bugs are never asked.
        ("S4", 20, "affected", "fix-optional"),
        ("S4", 6, "affected", "fix-optional"),
        ("S4", 5, "affected", "wontfix"),
        ("S4", 5, "fix-optional", "wontfix"),
        # Without a `wontfix` threshold, it is never set.
        ("S5", 8, "affected", None),
        ("S5", 1, "affected", "fix-optional"),
    ],
)
def test_beta_status_change(
    monkeypatch, rule, severity, days_to_release, status, expected
):
    rule.days_to_release = days_to_release
    bug = _bug(severity=severity, cf_status_firefox145=status)
    bugs, change = _run(monkeypatch, rule, bug)

    if expected is None:
        _assert_beta_asked(bugs, change)
    else:
        assert bugs == {}
        assert change["cf_status_firefox145"] == expected
        assert "flags" not in change
        assert f"this is an {severity} bug" in change["comment"]["body"]


@pytest.mark.parametrize(
    "severity, days_to_release, mentions_days",
    [("S3", 7, True), ("S4", 20, False)],
)
def test_fix_optional_comment(
    monkeypatch, rule, severity, days_to_release, mentions_days
):
    rule.days_to_release = days_to_release
    _, change = _run(monkeypatch, rule, _bug(severity=severity))
    body = change["comment"]["body"]
    assert (f"{days_to_release} days away" in body) == mentions_days


@pytest.mark.parametrize("severity, days_to_release", [("S3", 5), ("S4", 6)])
def test_fix_optional_left_alone(monkeypatch, rule, severity, days_to_release):
    rule.days_to_release = days_to_release
    bug = _bug(severity=severity, cf_status_firefox145="fix-optional")
    assert _run(monkeypatch, rule, bug) == ({}, {})


@pytest.mark.parametrize("severity, days_to_release", [("S3", 2), ("S4", 20)])
def test_beta_approval_requested_left_alone(
    monkeypatch, rule, severity, days_to_release
):
    rule.days_to_release = days_to_release
    bug = _bug(
        severity=severity,
        attachments=[{"flags": [{"name": "approval-mozilla-beta", "status": "?"}]}],
    )
    assert _run(monkeypatch, rule, bug) == ({}, {})


@pytest.mark.parametrize("severity, days_to_release", [("S3", 2), ("S4", 20)])
@pytest.mark.parametrize("status", ["wontfix", "unaffected"])
def test_beta_decided_left_alone(monkeypatch, rule, severity, days_to_release, status):
    rule.days_to_release = days_to_release
    bug = _bug(severity=severity, cf_status_firefox145=status)
    assert _run(monkeypatch, rule, bug) == ({}, {})


@pytest.mark.parametrize("severity, days_to_release", [("S3", 5), ("S4", 20)])
@pytest.mark.parametrize("beta", ["wontfix", "fixed", "fix-optional"])
def test_esr_still_asked(monkeypatch, rule, severity, days_to_release, beta):
    rule.days_to_release = days_to_release
    bug = _bug(
        severity=severity,
        cf_status_firefox145=beta,
        cf_status_firefox_esr140="affected",
    )
    bugs, change = _run(monkeypatch, rule, bug)
    assert bugs["123"]["channels"] == ["ESR"]
    assert "cf_status_firefox145" not in change
    assert change["flags"][0]["requestee"] == "dev@example.com"
    assert change["comment"]["body"].startswith(
        "The patch landed in nightly and ESR is affected.\n\n"
        ":dev, please make an uplift decision for ESR:\n"
    )


def test_beta_changed_and_esr_asked(monkeypatch, rule):
    rule.days_to_release = 3
    bug = _bug(severity="S3", cf_status_firefox_esr140="affected")
    bugs, change = _run(monkeypatch, rule, bug)
    assert bugs["123"]["channels"] == ["ESR"]
    assert change["cf_status_firefox145"] == "wontfix"
    assert change["flags"][0]["requestee"] == "dev@example.com"
    body = change["comment"]["body"]
    assert body.startswith(
        "The patch landed in nightly and ESR is affected.\n\n"
        "Beta is affected. Since this is an S3 bug and the release is 3 days "
        "away, setting `cf_status_firefox145` to `wontfix`: the fix will ship "
        "with the next release.\n\n"
        ":dev, please make an uplift decision for ESR:\n"
    )
    assert "For **beta**" not in body


@pytest.mark.parametrize("esr", ["affected", "unaffected"])
def test_beta_changed_without_needinfo(monkeypatch, rule, esr):
    rule.days_to_release = 3
    bug = _bug(
        severity="S3",
        cf_status_firefox_esr140=esr,
        flags=[{"name": "needinfo", "status": "?", "requestee": "dev@example.com"}],
    )
    bugs, change = _run(monkeypatch, rule, bug)
    assert bugs == {}
    assert change["cf_status_firefox145"] == "wontfix"
    assert "flags" not in change
    assert change["comment"]["body"].startswith(
        "The patch landed in nightly and beta is affected. Since this is an S3 bug"
    )


@pytest.mark.parametrize("esr", ["affected", "unaffected"])
def test_open_regression_left_alone(monkeypatch, rule, esr):
    bug = _bug(severity="S4", regressions=[REGRESSION_ID], cf_status_firefox_esr140=esr)
    assert _run(monkeypatch, rule, bug, regression_status="NEW") == ({}, {})


def test_fixed_regression_changed(monkeypatch, rule):
    bug = _bug(severity="S4", regressions=[REGRESSION_ID])
    bugs, change = _run(monkeypatch, rule, bug, regression_status="RESOLVED")
    assert bugs == {}
    assert change["cf_status_firefox145"] == "fix-optional"


@pytest.mark.parametrize(
    "severity, days_to_release, expected",
    [
        ("S3", 20, None),
        ("S3", 1, None),
        ("S4", 20, None),
        ("S4", 3, None),
        ("S4", 2, "fix-optional"),
        ("S4", 0, "fix-optional"),
    ],
)
def test_configured_thresholds(configured_rule, severity, days_to_release, expected):
    configured_rule.days_to_release = days_to_release
    bug = _bug(severity=severity)
    assert configured_rule.get_low_severity_status(bug) == expected


@pytest.mark.parametrize(
    "overrides",
    [
        {"groups": ["core-security"]},
        {"groups": ["dom-core-security"]},
        {"keywords": ["sec-low"]},
    ],
)
@pytest.mark.parametrize(
    "severity, days_to_release", [("S3", 2), ("S4", 20), ("S4", 2)]
)
def test_security_bugs_asked(monkeypatch, rule, overrides, severity, days_to_release):
    rule.days_to_release = days_to_release
    bug = _bug(severity=severity, **overrides)
    _assert_beta_asked(*_run(monkeypatch, rule, bug))


def test_non_security_group_changed(monkeypatch, rule):
    bug = _bug(severity="S4", groups=["mozilla-employee-confidential"])
    _, change = _run(monkeypatch, rule, bug)
    assert change["cf_status_firefox145"] == "fix-optional"


REV = "229f27b81ffdc833b55cf3072033102dbc324e42"
OTHER_REV = "1dabe5a869816d6b2c8e0a3f3b8c4bf0d1a2b3c4"


def _risk(band, patches=1, rev=REV):
    return {
        "band": band,
        "rev": rev,
        "patches": patches,
        **uplift_beta.RISK_BANDS[band],
    }


@pytest.mark.parametrize(
    "overrides, band, advice",
    [
        ({"severity": "S2"}, "l", uplift_beta.RECOMMEND_UPLIFT),
        ({"severity": "S1"}, "a", uplift_beta.RECOMMEND_UPLIFT),
        ({"severity": "S2"}, "v", uplift_beta.MITIGATE_RISK),
        ({"keywords": ["sec-high"]}, "h", uplift_beta.MITIGATE_RISK),
        ({"severity": "S3"}, "l", uplift_beta.CONSIDER_UPLIFT),
        ({"severity": "S3"}, "a", None),
        ({"severity": "S3"}, "h", uplift_beta.RIDE_THE_TRAINS),
        ({"severity": "S4", "keywords": ["sec-low"]}, "v", uplift_beta.RIDE_THE_TRAINS),
        ({"severity": "--"}, "l", None),
        ({"severity": "--"}, "a", uplift_beta.LOW_SEVERITY_RIDE_THE_TRAINS),
        ({"severity": "N/A"}, "v", uplift_beta.LOW_SEVERITY_RIDE_THE_TRAINS),
    ],
)
def test_risk_advice(monkeypatch, rule, overrides, band, advice):
    bug = _bug(**overrides)
    bugs, change = _run(monkeypatch, rule, bug, risks={"123": _risk(band)})
    _assert_beta_asked(bugs, change)

    label = uplift_beta.RISK_BANDS[band]["label"]
    rate = uplift_beta.RISK_BANDS[band]["regression_rate"]
    assert bugs["123"]["risk"] == label
    body = change["comment"]["body"]
    sentence = (
        "regressor model rates the patch as "
        f"**{label}** risk: about {rate} of the patches with this rating cause "
        "a regression."
    )
    if advice:
        sentence += f" {advice}"
    assert f"{sentence}\n" in body
    for other in (
        uplift_beta.RECOMMEND_UPLIFT,
        uplift_beta.MITIGATE_RISK,
        uplift_beta.CONSIDER_UPLIFT,
        uplift_beta.RIDE_THE_TRAINS,
        uplift_beta.LOW_SEVERITY_RIDE_THE_TRAINS,
    ):
        if other != advice:
            assert other not in body


def test_risk_several_patches(monkeypatch, rule):
    risks = {"123": _risk("h", patches=3)}
    _, change = _run(monkeypatch, rule, _bug(), risks=risks)
    assert (
        "rates the riskiest of the 3 patches ([229f27b81ffd]"
        "(https://hg.mozilla.org/integration/autoland/rev/229f27b81ffd)) as **high**"
        in change["comment"]["body"]
    )


@pytest.mark.parametrize("risks", [{}, Exception("bugbug is down")])
def test_no_risk(monkeypatch, rule, risks):
    bugs, change = _run(monkeypatch, rule, _bug(), risks=risks)
    _assert_beta_asked(bugs, change)
    assert bugs["123"]["risk"] == ""
    assert "regressor model" not in change["comment"]["body"]


def test_risk_not_computed_without_question(monkeypatch, rule):
    rule.days_to_release = 3
    bug = _bug(severity="S3")
    # Raise if called: the bug only gets a status change.
    bugs, change = _run(monkeypatch, rule, bug, risks=AssertionError())
    assert bugs == {}
    assert change["cf_status_firefox145"] == "wontfix"


def test_get_risks(monkeypatch, rule):
    revs = {
        "1": [REV, OTHER_REV, "backout"],
        "2": ["unavailable"],
        "3": [OTHER_REV],
    }
    classifications = {
        REV: {"risk_band": "a"},
        OTHER_REV: {"risk_band": "v"},
        "backout": {"risk_band": None, "ignored_reason": "backout"},
        "unavailable": {"available": False},
    }

    def get_commits_classification(model, branch, all_revs):
        assert (model, branch) == ("regressor", "autoland")
        assert sorted(all_revs) == sorted(sum(revs.values(), []))
        return classifications

    monkeypatch.setattr(UpliftBeta, "get_landed_revs", lambda self, bugs: revs)
    monkeypatch.setattr(
        uplift_beta, "get_commits_classification", get_commits_classification
    )

    assert rule.get_risks({}) == {
        "1": _risk("v", patches=2, rev=OTHER_REV),
        "3": _risk("v", rev=OTHER_REV),
    }


def test_get_landed_revs(monkeypatch, rule):
    def comment(text):
        return {"text": text}

    comments = {
        "123": [
            comment("Some comment"),
            comment(
                "Pushed by dev@example.com:\n"
                "https://github.com/mozilla-firefox/firefox/commit/aaaaaaaaaaaa\n"
                "https://hg.mozilla.org/integration/autoland/rev/111111111111\n"
                "Bug 123 - Fix it. r=reviewer\n"
                "https://github.com/mozilla-firefox/firefox/commit/bbbbbbbbbbbb\n"
                "https://hg.mozilla.org/integration/autoland/rev/222222222222\n"
                "Bug 123 - Fix it more. r=reviewer"
            ),
            comment(
                "Regressed by https://hg.mozilla.org/integration/autoland/rev/333333333333"
            ),
            comment(
                "Pushed by sheriff@example.com:\n"
                "https://hg.mozilla.org/integration/autoland/rev/444444444444\n"
                'Revert "Bug 123 - Fix it more. r=reviewer" for causing failures'
            ),
            comment("https://hg.mozilla.org/integration/autoland/rev/555555555555"),
        ],
        "456": [],
    }
    hg = {
        "111111111111": {"node": "1" * 40, "desc": "Bug 123 - Fix it. r=reviewer"},
        "222222222222": {
            "node": "2" * 40,
            "desc": "Bug 123 - Fix it more. r=reviewer",
            "backedoutby": "4" * 40,
        },
        "333333333333": {"node": "3" * 40, "desc": "Bug 1234 - Regressor."},
        "444444444444": {
            "node": "4" * 40,
            "desc": 'Revert "Bug 123 - Fix it more. r=reviewer"',
        },
        "555555555555": {"node": "5" * 40, "desc": "Bug 123 - Relanded. r=reviewer"},
    }

    class Bugzilla:
        get_landing_comments = staticmethod(RealBugzilla.get_landing_comments)

        def __init__(self, bugids, commenthandler, commentdata, **kwargs):
            assert sorted(bugids) == ["123", "456"]
            for bugid in bugids:
                commenthandler({"comments": comments[bugid]}, bugid, commentdata)

        def get_data(self):
            return self

        def wait(self):
            pass

    class Revision:
        def __init__(self, queries):
            for query in queries:
                assert query.url.endswith("/integration/autoland/json-rev")
                query.handler(hg[query.params["node"]], query.handlerdata)

        def wait(self):
            pass

    monkeypatch.setattr(uplift_beta, "Bugzilla", Bugzilla)
    monkeypatch.setattr(uplift_beta.hgmozilla, "Revision", Revision)

    assert rule.get_landed_revs({"123": {}, "456": {}}) == {
        "123": ["1" * 40, "5" * 40],
    }
