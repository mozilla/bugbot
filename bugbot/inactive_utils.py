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
