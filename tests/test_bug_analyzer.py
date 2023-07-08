import unittest

from bugbot.bug.analyzer import BugsStore


class TestSetStatusFlags(unittest.TestCase):
    def test_set_status_flags(self):
        all_bugs = [
            {
                "id": 1111,
                "cf_status_firefox_esr2": "---",
                "cf_status_firefox_esr3": "---",
                "cf_status_firefox2": "---",
                "cf_status_firefox3": "affected",
                "cf_status_firefox4": "fixed",
                "regressed_by": [111],
            },
            {
                "id": 2222,
                "cf_status_firefox_esr2": "---",
                "cf_status_firefox_esr3": "---",
                "cf_status_firefox2": "---",
                "cf_status_firefox3": "---",
                "cf_status_firefox4": "---",
                "regressed_by": [222],
            },
            {
                "id": 3333,
                "cf_status_firefox_esr2": "---",
                "cf_status_firefox_esr3": "---",
                "cf_status_firefox2": "---",
                "cf_status_firefox3": "affected",
                "cf_status_firefox4": "fixed",
                "regressed_by": [333],
            },
            {
                "id": 111,
                "cf_status_firefox_esr3": "fixed",
                "cf_status_firefox3": "fixed",
            },
            {
                "id": 222,
                "cf_status_firefox1": "fixed",
            },
            {
                "id": 333,
                "cf_status_firefox_esr3": "fixed",
                "cf_status_firefox3": "fixed",
                "groups": ["core-security-release"],
            },
        ]

        versions_map = {
            "release": 2,
            "beta": 3,
            "nightly": 4,
            "esr": 3,
            "esr_previous": 2,
        }

        bugs_store = BugsStore(all_bugs, versions_map)

        updates = bugs_store.get_bug_by_id(1111).detect_version_status_updates()
        flag_status = {update.flag: update.status for update in updates}
        self.assertEqual(
            sorted(flag_status),
            [
                "cf_status_firefox2",
                "cf_status_firefox_esr2",
                "cf_status_firefox_esr3",
            ],
        )

        self.assertEqual(flag_status["cf_status_firefox2"], "unaffected")
        self.assertEqual(flag_status["cf_status_firefox_esr2"], "unaffected")
        self.assertEqual(flag_status["cf_status_firefox_esr3"], "affected")
