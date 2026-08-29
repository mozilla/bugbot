from bugbot import utils


def process_bugs(bugs, get_revisions_fn, needinfo_func):
    rev_ids = {rev_id for bug in bugs.values() for rev_id in bug["rev_ids"]}
    revisions = get_revisions_fn(list(rev_ids))

    for bugid, bug in list(bugs.items()):
        inactive_revs = [
            revisions[rev_id] for rev_id in bug["rev_ids"] if rev_id in revisions
        ]
        if inactive_revs:
            bug["revisions"] = inactive_revs
            needinfo_user = needinfo_func(bugid, inactive_revs)
            bug["needinfo_user"] = needinfo_user
        else:
            del bugs[bugid]

    # Resolving https://github.com/mozilla/bugbot/issues/1300 should clean this
    # including improve the wording in the template (i.e., "See the search query on Bugzilla").
    query_url = utils.get_bz_search_url({"bug_id": ",".join(bugs.keys())})

    return bugs, query_url


def handle_bug_util(bug, data, PHAB_FILE_NAME_PAT, PHAB_TABLE_PAT, bot):
    rev_ids = [
        # To avoid loading the attachment content (which can be very large),
        # we extract the revision id from the file name, which is in the
        # format of "phabricator-D{revision_id}-url.txt".
        # len("phabricator-D") == 13
        # len("-url.txt") == 8
        int(attachment["file_name"][13:-8])
        for attachment in bug["attachments"]
        if attachment["content_type"] == "text/x-phabricator-request"
        and PHAB_FILE_NAME_PAT.match(attachment["file_name"])
        and not attachment["is_obsolete"]
    ]

    if not rev_ids:
        return

    # We should not comment about the same patch more than once.
    rev_ids_with_ni = set()
    for comment in bug["comments"]:
        if comment["creator"] == bot and comment["raw_text"].startswith(
            "The following patch"
        ):
            rev_ids_with_ni.update(
                int(id) for id in PHAB_TABLE_PAT.findall(comment["raw_text"])
            )

    if rev_ids_with_ni:
        rev_ids = [id for id in rev_ids if id not in rev_ids_with_ni]

    if not rev_ids:
        return

    # It will be nicer to show a sorted list of patches
    rev_ids.sort()

    bugid = str(bug["id"])
    data[bugid] = {
        "rev_ids": rev_ids,
    }
    return bug


def get_revisions(
    revs,
    fetch_revs_func,
    get_phab_users_with_status_func,
    status_note_func,
    user_status_active,
):
    revisions = []

    for _rev_ids in revs:
        for revision in fetch_revs_func(_rev_ids):
            if (
                len(revision["attachments"]["reviewers"]["reviewers"]) == 0
                or revision["fields"]["status"]["value"] != "needs-review"
                or revision["fields"]["isDraft"]
            ):
                continue

            reviewers = [
                {
                    "phid": reviewer["reviewerPHID"],
                    "is_group": reviewer["reviewerPHID"].startswith("PHID-PROJ"),
                    "is_blocking": reviewer["isBlocking"],
                    "is_accepted": reviewer["status"] == "accepted",
                    "is_resigned": reviewer["status"] == "resigned",
                }
                for reviewer in revision["attachments"]["reviewers"]["reviewers"]
            ]

            # Group reviewers will be consider always active; so if there is
            # no other reviewers blocking, we don't need to check further.
            if any(
                reviewer["is_group"] or reviewer["is_accepted"]
                for reviewer in reviewers
            ) and not any(
                not reviewer["is_accepted"]
                for reviewer in reviewers
                if reviewer["is_blocking"]
            ):
                continue

            revisions.append(
                {
                    "rev_id": revision["id"],
                    "title": revision["fields"]["title"],
                    "created_at": revision["fields"]["dateCreated"],
                    "author_phid": revision["fields"]["authorPHID"],
                    "reviewers": reviewers,
                }
            )

    user_phids = set()
    for revision in revisions:
        user_phids.add(revision["author_phid"])
        for reviewer in revision["reviewers"]:
            user_phids.add(reviewer["phid"])

    users = get_phab_users_with_status_func(list(user_phids), keep_active=True)

    result = {}
    for revision in revisions:
        # It is not useful to notify an inactive author about an inactive
        # reviewer, thus we should exclude revisions with inactive authors.
        author_info = users[revision["author_phid"]]
        if author_info["status"] != user_status_active:
            continue

        revision["author"] = author_info

        inactive_reviewers = []
        for reviewer in revision["reviewers"]:
            if reviewer["is_group"]:
                continue

            reviewer_info = users[reviewer["phid"]]
            if (
                not reviewer["is_resigned"]
                and reviewer_info["status"] == user_status_active
            ):
                continue

            reviewer["info"] = reviewer_info
            inactive_reviewers.append(reviewer)

        if len(inactive_reviewers) == len(revision["reviewers"]) or any(
            reviewer["is_blocking"] and not reviewer["is_accepted"]
            for reviewer in inactive_reviewers
        ):
            revision["reviewers"] = [
                {
                    "phab_username": reviewer["info"]["phab_username"],
                    "status_note": status_note_func(reviewer),
                }
                for reviewer in inactive_reviewers
            ]
            result[revision["rev_id"]] = revision

    return result
