import responses
from libmozdata.socorro import Socorro

from bugbot.auto_mock import MockTestCase
from bugbot.topcrash import Topcrash


class TestTopcrash(MockTestCase):

    mock_urls = [Socorro.API_URL]

    @responses.activate
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
        assert "EMPTY: no frame data available; StreamSizeMismatch" in signatures
