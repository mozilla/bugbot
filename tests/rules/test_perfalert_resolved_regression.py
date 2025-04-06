def test_get_resolution_comment():
    from datetime import datetime
    from bugbot.rules.perfalert_resolved_regression import PerfAlertResolvedRegression

    # Mock data
    comments = [
        {"creation_time": datetime(2023, 10, 1, 10, 0), "author": "user@example.com", "text": "Initial comment"},
        {"creation_time": datetime(2023, 10, 1, 11, 0), "author": "bot@example.com", "text": "Bot comment"},
        {"creation_time": datetime(2023, 10, 1, 12, 0), "author": "user@example.com", "text": "Resolution comment"},
    ]
    bug_history = {
        "status_time": datetime(2023, 10, 1, 12, 0),
        "status_author": "user@example.com",
    }

    # Instantiate the class
    perf_alert = PerfAlertResolvedRegression()

    # Test the method
    resolution_comment = perf_alert.get_resolution_comment(comments, bug_history)

    # Assert the expected outcome
    assert resolution_comment == "Resolution comment"