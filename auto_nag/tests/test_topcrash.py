import unittest

import libmozdata.socorro as socorro
from libmozdata import utils as lmdutils

from auto_nag.topcrash import Topcrash


class TestTopcrash(unittest.TestCase):
    def test___get_params_from_criteria(self):
        topcrash = Topcrash()

        start_date = lmdutils.get_date("today", 30)
        end_date = lmdutils.get_date("today")
        date_range = socorro.SuperSearch.get_search_date(start_date, end_date)

        crash_signature_block_patterns = [
            "!^EMPTY: ",
            "!=OOM | small",
            "!=IPCError-browser | ShutDownKill",
        ]

        signatures = topcrash._fetch_signatures_from_patters(
            crash_signature_block_patterns, date_range
        )

        assert "OOM | small" in signatures
        assert "IPCError-browser | ShutDownKill" in signatures
        assert "EMPTY: no crashing thread identified; EmptyMinidump" in signatures
