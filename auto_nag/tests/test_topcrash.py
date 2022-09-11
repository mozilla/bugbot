import unittest

from auto_nag.topcrash import Topcrash


class TestTopcrash(unittest.TestCase):
    def test_get_blocked_signatures(self):
        crash_signature_block_patterns = [
            "!^EMPTY: ",
            "!=OOM | small",
            "!=IPCError-browser | ShutDownKill",
        ]

        topcrash = Topcrash(signature_block_patterns=crash_signature_block_patterns)
        signatures = topcrash.get_blocked_signatures()

        assert "OOM | small" in signatures
        assert "IPCError-browser | ShutDownKill" in signatures
        assert "EMPTY: no crashing thread identified; EmptyMinidump" in signatures
