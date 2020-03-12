""" Requests bugs from Bugzilla API that have "good-first-bug" in their whiteboard.
Update the whiteboard field, removing good-first-bug and cases such as [good-first-bug].
Add "good-first-bug" to keywords if not there already.
"""

import requests
import json


def remove_gfb_from_whiteboard(url, test=False):
    get_params = "?whiteboard=good-first-bug&include_fields=whiteboard,keywords,id"
    payload = {}
    headers = {} if not test else {'X-BUGZILLA-API-KEY': 'adrw0ONTkJoVuk1yhOMnF7vsnZzlQZUZg3th7Dez', 'Content-Type': 'application/json'}

    # ============== TEST CODE =================
    if test:
        test_post_bodys = [
            "{\n    \"product\": \"Bugzilla\",\n    \"component\": \"Testing Suite\",\n    \"version\": \"unspecified\",\n    \"summary\": \"'This is a test bug - please disregard\",\n    \"type\": \"task\",\n    \"whiteboard\": \"good-first-bugs\",\n    \"keywords\": \"good-first-bug\"\n    \n}",
            "{\n    \"product\": \"Bugzilla\",\n    \"component\": \"Testing Suite\",\n    \"version\": \"unspecified\",\n    \"summary\": \"This is a test bug - please disregard\",\n    \"type\": \"task\",\n    \"whiteboard\": \"[good-first-bug]\",\n    \"keywords\": \"good-first-bug\"\n}",
            "{\n    \"product\": \"Bugzilla\",\n    \"component\": \"Testing Suite\",\n    \"version\": \"unspecified\",\n    \"summary\": \"This is a test bug - please disregard\",\n    \"type\": \"task\",\n    \"whiteboard\": \"[good-first-bugs]\"\n}",
            "{\n    \"product\": \"Bugzilla\",\n    \"component\": \"Testing Suite\",\n    \"version\": \"unspecified\",\n    \"summary\": \"This is a test bug - please disregard\",\n    \"type\": \"task\",\n    \"whiteboard\": \"good-first-bug\"\n}"
            ]
        ids = []
        for post in test_post_bodys:
            post_rep = requests.request("POST", url, headers=headers, data=post)

            post_rep.raise_for_status()
            ids.append(post_rep.json()['id'])

    # Get request for bugs with "good-first-bug" in their whiteboard
    response = requests.request("GET", url + get_params, headers=headers, data=payload)

    # Check response status code is good
    response.raise_for_status()

    # Loop over the bugs in the response
    for bug in response.json()["bugs"]:
        # Initialize update dictionary
        updated_bug = {"id": bug["id"]}

        # Remove the "good-first-bug" from the whiteboard
        whiteboard = bug["whiteboard"]
        if "[good-first-bugs]" in whiteboard:
            updated_bug["whiteboard"] = whiteboard.replace("[good-first-bugs]", '').strip()
        if "[good-first-bug]" in whiteboard:
            updated_bug["whiteboard"] = whiteboard.replace("[good-first-bug]", '').strip()
        if "good-first-bugs" in whiteboard:
            updated_bug["whiteboard"] = whiteboard.replace("good-first-bugs", '').strip()
        if "good-first-bug" in whiteboard:
            updated_bug["whiteboard"] = whiteboard.replace("good-first-bug", '').strip()

        # Add "good-first-bug" to keywords if not there already.
        if bug["keywords"] and not ("good-first-bug" in bug["keywords"]):
            updated_bug["keywords"] = {"add": ["good-first-bug"]}
        elif not bug["keywords"]:
            updated_bug["keywords"] = {"add": ["good-first-bug"]}

        # PUT the updates to the API
        if (not test) or (test and bug["id"] in ids):
            put = requests.request("PUT", url + "/" + str(bug["id"]), headers=headers, data=json.dumps(updated_bug))
            put.raise_for_status()

    if test:
        checker(ids, url, headers)


def checker(ids, url_, headers):
    ids_string = "?id="
    for di in ids:
        ids_string += ',' + str(di) if len(ids_string) > len("?ids=") else str(di)
    ids_string += "&include_fields=whiteboard,keywords,id"
    response2 = requests.request("GET", url_ + ids_string, headers=headers, data={})
    response2.raise_for_status()
    bugs = response2.json()["bugs"]
    assert len(bugs) == len(ids), "Not all ids present"
    for bug in bugs:
        assert bug['id'] in ids, "Non matching ids"
        assert "good-first-bug" in bug['keywords'], "keywords does not contain good-first-bug"
        assert not ("good-first-bug" in bug['whiteboard']), "whiteboard still contains good-first-bug"


if __name__ == "__main__":
    main_url = "https://bugzilla.mozilla.org/rest/bug"
    test_url = "https://bugzilla-dev.allizom.org/rest/bug"

    remove_gfb_from_whiteboard(test_url, True)
