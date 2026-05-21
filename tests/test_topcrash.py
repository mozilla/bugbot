import responses
from libmozdata.socorro import Socorro

from bugbot.topcrash import Topcrash


@responses.activate
def test_get_blocked_signatures(setup_mock_urls):
    setup_mock_urls([Socorro.API_URL])
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
