def test_get_resolution_comment():
    from datetime import datetime

    from bugbot.rules.perfalert_resolved_regression import PerfAlertResolvedRegression

    # Mock data
    comments = [
        {
            "creation_time": datetime(2023, 10, 1, 10, 0),
            "author": "user@example.com",
            "text": "Initial comment",
        },
        {
            "creation_time": datetime(2023, 10, 1, 11, 0),
            "author": "bot@example.com",
            "text": "Bot comment",
        },
        {
            "creation_time": datetime(2023, 10, 1, 12, 0),
            "author": "user@example.com",
            "text": "Resolution comment",
        },
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


def test_has_merged_github_pr():
    from unittest.mock import patch

    from bugbot.rules.perfalert_resolved_regression import PerfAlertResolvedRegression

    perf_alert = PerfAlertResolvedRegression()
    bug = {
        "attachments": [
            {
                "content_type": "text/x-phabricator-request",
                "file_name": "phabricator-D123-url.txt",
                "is_obsolete": 0,
            },
            {
                "content_type": "text/x-github-pull-request",
                "file_name": "github-mozilla_pdf.js-22027-url.txt",
                "is_obsolete": 0,
            },
        ]
    }

    with patch.object(
        perf_alert, "is_github_pr_merged", return_value=True
    ) as is_github_pr_merged:
        assert perf_alert.has_merged_github_pr(bug)
        is_github_pr_merged.assert_called_once_with("mozilla", "pdf.js", "22027")

    with patch.object(perf_alert, "is_github_pr_merged", return_value=False):
        assert not perf_alert.has_merged_github_pr(bug)

    bug["attachments"][1]["is_obsolete"] = 1
    with patch.object(
        perf_alert, "is_github_pr_merged", return_value=True
    ) as is_github_pr_merged:
        assert not perf_alert.has_merged_github_pr(bug)
        is_github_pr_merged.assert_not_called()
