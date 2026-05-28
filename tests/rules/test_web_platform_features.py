from bugbot.rules.web_platform_features import (
    AddRemoveChange,
    BugzillaUpdate,
    FeatureBugUpdate,
    Resolution,
    UserStoryChange,
    UserStoryChangeType,
    WebPlatformFeatures,
    parse_user_story,
    url_keys,
)


def test_parse_user_story():
    user_story = """
foo:bar
abcde:
  foo : baz
some long line: with a colon
key-:value
"""
    assert list(parse_user_story(user_story)) == [
        ("", None, None),
        ("foo:bar", "foo", "bar"),
        ("abcde:", None, None),
        ("  foo : baz", "foo", "baz"),
        ("some long line: with a colon", None, None),
        ("key-:value", "key-", "value"),
    ]


def test_url_keys():
    urls = ["https://example.org/foo/?test#bar"]
    assert url_keys(urls) == {("example.org", "/foo/"): urls}

    urls = ["https://example.org/foo/?test#bar", "https://example.org/foo/"]
    assert url_keys(urls) == {("example.org", "/foo/"): urls}

    urls = ["https://example.org/foo/", "https://example.org/bar/"]
    assert url_keys(urls) == {
        ("example.org", "/foo/"): urls[:1],
        ("example.org", "/bar/"): urls[1:],
    }


def test_bugzilla_update_to_json():
    assert BugzillaUpdate(keywords=AddRemoveChange(add=["test"])).to_json() == {
        "keywords": {"add": ["test"]}
    }
    assert BugzillaUpdate(keywords=AddRemoveChange(remove=["test"])).to_json() == {
        "keywords": {"remove": ["test"]}
    }
    assert BugzillaUpdate(see_also=AddRemoveChange(remove=["test"])).to_json() == {
        "see_also": {"remove": ["test"]}
    }
    assert BugzillaUpdate(whiteboard="test").to_json() == {"whiteboard": "test"}
    assert BugzillaUpdate(user_story="test").to_json() == {"cf_user_story": "test"}
    assert BugzillaUpdate(status="test").to_json() == {"status": "test"}
    assert BugzillaUpdate(resolution="test").to_json() == {"resolution": "test"}
    assert BugzillaUpdate(comment="test").to_json() == {"comment": {"body": "test"}}


def test_feature_bug_update_into_bugzilla_update():
    assert FeatureBugUpdate(
        keywords={
            "test_add": True,
            "test_add_present": True,
            "test_remove": False,
            "test_remove_missing": False,
        }
    ).into_bugzilla_update(
        {"keywords": ["existing", "test_remove", "test_add_present"]}
    ) == BugzillaUpdate(
        keywords=AddRemoveChange(add=["test_add"], remove=["test_remove"])
    )
    assert FeatureBugUpdate(
        see_also={
            "https://example.org/add/": True,
            "https://example.org/add_present/?query#hash": True,
            "https://example.org/remove/": False,
            "https://example.org/remove_missing/": False,
        }
    ).into_bugzilla_update(
        {
            "url": "https://example.org/url/",
            "see_also": [
                "https://example.org/add_present/",
                "https://example.org/remove/",
            ],
        }
    ) == BugzillaUpdate(
        see_also=AddRemoveChange(
            add=["https://example.org/add/"], remove=["https://example.org/remove/"]
        )
    )
    assert FeatureBugUpdate(
        user_story=[
            UserStoryChange(
                "test-1", UserStoryChangeType.REPLACE, "test-1_old", "test-1_new"
            ),
            UserStoryChange("test-2", UserStoryChangeType.APPEND, None, "test-2_old"),
            UserStoryChange("test-2", UserStoryChangeType.APPEND, None, "test-2_new"),
            UserStoryChange("test-3", UserStoryChangeType.DELETE, "test-3_old", None),
            UserStoryChange(
                "test-4",
                UserStoryChangeType.REPLACE,
                "test-4_old-missing",
                "test-4_new",
            ),
        ]
    ).into_bugzilla_update(
        {
            "cf_user_story": """
test-1:test-1_old
test-2:test-2_old
test-3:test-3_old
test-3:test-3_old-unremoved
test-4:test-4_old
"""
        }
    ) == BugzillaUpdate(
        user_story="""
test-1:test-1_new
test-2:test-2_old
test-3:test-3_old-unremoved
test-4:test-4_old
test-2:test-2_new"""
    )

    assert (
        FeatureBugUpdate(comment=["test", "test1"]).into_bugzilla_update({})
        == BugzillaUpdate()
    )
    assert FeatureBugUpdate(
        comment=["test", "test1"], comment_when_unchanged=True
    ).into_bugzilla_update({}) == BugzillaUpdate(comment="test\n\ntest1")

    assert FeatureBugUpdate(resolve=Resolution.FIXED).into_bugzilla_update(
        {"resolution": "", "status": "NEW"}
    ) == BugzillaUpdate(resolution="FIXED", status="RESOLVED")
    assert FeatureBugUpdate(resolve=Resolution.NONE).into_bugzilla_update(
        {"resolution": "RESOLVED", "status": "FIXED"}
    ) == BugzillaUpdate(resolution="", status="REOPENED")


def test_handlebug():
    cleaner = WebPlatformFeatures()
    cleaner.bug_updates = {1234: FeatureBugUpdate(keywords={"add-keyword": True})}
    data = {}
    input_bug = {
        "id": "1234",
        "url": "https://example.org",
        "see_also": [],
        "keywords": ["web-feature"],
        "whiteboard": "",
        "cf_user_story": "web-feature: test",
        "status": "NEW",
        "resolution": "",
    }
    output_bug = cleaner.handle_bug(
        input_bug.copy(),
        data,
    )
    assert data["1234"] == {
        "changes": BugzillaUpdate(keywords=AddRemoveChange(add=["add-keyword"])),
        "whiteboard": "",
        "user_story": "web-feature: test",
    }
    assert output_bug == input_bug
    assert cleaner.autofix_changes == {"1234": {"keywords": {"add": ["add-keyword"]}}}
