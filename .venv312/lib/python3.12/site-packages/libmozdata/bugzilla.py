# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import functools
import re

import requests
import six
from requests import HTTPError

import libmozdata.versions

from . import config, utils
from .connection import Connection, Query
from .handler import Handler


class BugzillaBase(Connection):
    URL = config.get("Bugzilla", "URL", "https://bugzilla.mozilla.org")
    # URL = config.get('Allizgub', 'URL', 'https://bugzilla-dev.allizom.org')
    TOKEN = config.get("Bugzilla", "token", "")
    # TOKEN = config.get('Allizgub', 'token', '')

    def get_header(self):
        header = super(BugzillaBase, self).get_header()
        header["X-Bugzilla-API-Key"] = self.get_apikey()
        return header


class Bugzilla(BugzillaBase):
    """Connection to bugzilla.mozilla.org"""

    API_URL = BugzillaBase.URL + "/rest/bug"
    ATTACHMENT_API_URL = API_URL + "/attachment"
    BUGZILLA_CHUNK_SIZE = 100

    def __init__(
        self,
        bugids=None,
        include_fields="_default",
        bughandler=None,
        bugdata=None,
        historyhandler=None,
        historydata=None,
        commenthandler=None,
        commentdata=None,
        comment_include_fields=None,
        attachmentids=None,
        attachmenthandler=None,
        attachmentdata=None,
        attachment_include_fields=None,
        queries=None,
        **kwargs,
    ):
        """Constructor

        Args:
            bugids (List[str]): list of bug ids or search query
            include_fields (List[str]): list of include fields
            bughandler (Optional[function]): the handler to use with each retrieved bug
            bugdata (Optional): the data to use with the bug handler
            historyhandler (Optional[function]): the handler to use with each retrieved bug history
            historydata (Optional): the data to use with the history handler
            commenthandler (Optional[function]): the handler to use with each retrieved bug comment
            commentdata (Optional): the data to use with the comment handler
            comment_include_fields (Optional[List[str]]): list of comment include fields
            attachmentids (List[str]): list of attachment ids to retrieve
            attachmenthandler (Optional[function]): the handler to use with each retrieved bug attachment
            attachmentdata (Optional): the data to use with the attachment handler
            attachment_include_fields (Optional[List[str]]): list of attachment include fields
            queries (List[Query]): queries rather than single query
        """
        if queries is not None:
            super(Bugzilla, self).__init__(Bugzilla.URL, queries=queries, **kwargs)
        else:
            super(Bugzilla, self).__init__(Bugzilla.URL, **kwargs)
            if isinstance(bugids, six.string_types) or isinstance(bugids, dict):
                self.bugids = [bugids]
            elif isinstance(bugids, int):
                self.bugids = [str(bugids)]
            elif attachmentids is not None:
                self.bugids = None
            else:
                self.bugids = list(bugids)
            self.include_fields = include_fields
            self.bughandler = Handler.get(bughandler, bugdata)
            self.historyhandler = Handler.get(historyhandler, historydata)
            self.commenthandler = Handler.get(commenthandler, commentdata)
            self.comment_include_fields = comment_include_fields
            self.attachmentids = (
                attachmentids
                if isinstance(attachmentids, list) or attachmentids is None
                else [attachmentids]
            )
            self.attachmenthandler = Handler.get(attachmenthandler, attachmentdata)
            self.attachment_include_fields = attachment_include_fields
            self.bugs_results = []
            self.history_results = []
            self.comment_results = []
            self.attachment_results = []
            self.got_data = False
            self.no_private_bugids = None

    def put(self, data, attachment=False, retry_on_failure=False):
        """Put some data in bugs

        Args:
            data (dict): a dictionary
        """
        failures = []
        if self.bugids:
            if self.__is_bugid():
                ids = self.bugids
            else:
                ids = self.__get_bugs_list()

            url = Bugzilla.ATTACHMENT_API_URL if attachment else Bugzilla.API_URL
            url += "/"
            to_retry = ids
            header = self.get_header()

            def cb(data, res, *args, **kwargs):
                error = True
                if res.status_code == 200:
                    json = res.json()
                    if not json.get("error", False):
                        error = False

                if error:
                    if retry_on_failure:
                        to_retry.extend(data)
                    else:
                        failures.extend(data)

            while to_retry:
                _to_retry = list(to_retry)
                to_retry = []
                for _ids in Connection.chunks(
                    _to_retry, chunk_size=Bugzilla.BUGZILLA_CHUNK_SIZE
                ):
                    first_id = _ids[0]
                    if len(_ids) >= 2:
                        data["ids"] = _ids
                    elif "ids" in data:
                        del data["ids"]
                    self.session.put(
                        url + first_id,
                        json=data,
                        headers=header,
                        verify=True,
                        timeout=self.TIMEOUT,
                        hooks={"response": functools.partial(cb, _ids)},
                    ).result()
        return failures

    def get_data(self):
        """Collect the data"""
        if not self.got_data:
            self.got_data = True
            if self.__is_bugid():
                if self.bughandler.isactive():
                    self.__get_bugs()
                if self.historyhandler.isactive():
                    self.__get_history()
                if self.commenthandler.isactive():
                    self.__get_comment()
                if self.attachmenthandler.isactive():
                    self.__get_attachment()
            elif self.bughandler.isactive():
                self.__get_bugs_for_history_comment()

        return self

    def wait(self):
        if self.queries is not None:
            super(Bugzilla, self).wait()
        else:
            self.get_data()
            self.wait_bugs()
            for r in self.comment_results:
                r.result()
            for r in self.history_results:
                r.result()
            for r in self.attachment_results:
                r.result()

    def wait_bugs(self):
        """Just wait for bugs"""
        for r in self.bugs_results:
            r.result()

    def merge(self, bz):
        if self.bugids is None or bz.bugids is None:
            return None

        def __merge_fields(f1, f2):
            if f1:
                f1 = {f1} if isinstance(f1, six.string_types) else set(f1)
                if f2:
                    f2 = {f2} if isinstance(f2, six.string_types) else set(f2)
                    return list(f1.union(f2))
                else:
                    return f1
            else:
                if f2:
                    return f2
                else:
                    return None

        bugids = list(set(self.bugids).union(set(bz.bugids)))
        include_fields = __merge_fields(self.include_fields, bz.include_fields)
        comment_include_fields = __merge_fields(
            self.comment_include_fields, bz.comment_include_fields
        )
        attachment_include_fields = __merge_fields(
            self.attachment_include_fields, bz.attachment_include_fields
        )
        bughandler = self.bughandler.merge(bz.bughandler)
        historyhandler = self.historyhandler.merge(bz.historyhandler)
        commenthandler = self.commenthandler.merge(bz.commenthandler)
        attachmenthandler = self.attachmenthandler.merge(bz.attachmenthandler)

        return Bugzilla(
            bugids=bugids,
            include_fields=include_fields,
            bughandler=bughandler,
            historyhandler=historyhandler,
            commenthandler=commenthandler,
            attachmenthandler=attachmenthandler,
            comment_include_fields=comment_include_fields,
            attachment_include_fields=attachment_include_fields,
        )

    def __get_no_private_ids(self):
        if not self.no_private_bugids:
            self.no_private_bugids = Bugzilla.remove_private_bugs(self.bugids)
        return self.no_private_bugids

    @staticmethod
    def get_nightly_version():
        def handler(json, data):
            max_version = -1
            pat = re.compile("cf_status_firefox([0-9]+)")
            for key in json.keys():
                m = pat.match(key)
                if m:
                    version = int(m.group(1))
                    if max_version < version:
                        max_version = version
            data[0] = max_version

        nightly_version = [-1]
        Bugzilla(bugids=["1234567"], bughandler=handler, bugdata=nightly_version).wait()

        return nightly_version[0]

    @staticmethod
    def get_links(bugids):
        if isinstance(bugids, six.string_types) or isinstance(bugids, int):
            return "https://bugzilla.mozilla.org/" + str(bugids)
        else:
            return ["https://bugzilla.mozilla.org/" + str(bugid) for bugid in bugids]

    @staticmethod
    def follow_dup(bugids, only_final=True):
        """Follow the duplicated bugs

        Args:
            bugids (List[str]): list of bug ids
            only_final (bool): if True only the final bug is returned else all the chain

        Returns:
            dict: each bug in entry is mapped to the last bug in the duplicate chain (None if there's no dup and 'cycle' if a cycle is detected)
        """
        include_fields = ["id", "resolution", "dupe_of"]
        dup = {}
        _set = set()
        for bugid in bugids:
            dup[str(bugid)] = None

        def bughandler(bug):
            if bug["resolution"] == "DUPLICATE":
                dupeofid = str(bug["dupe_of"])
                dup[str(bug["id"])] = [dupeofid]
                _set.add(dupeofid)

        bz = Bugzilla(
            bugids=bugids, include_fields=include_fields, bughandler=bughandler
        ).get_data()
        bz.wait_bugs()

        def bughandler2(bug):
            if bug["resolution"] == "DUPLICATE":
                bugid = str(bug["id"])
                for _id, dupid in dup.items():
                    if dupid and dupid[-1] == bugid:
                        dupeofid = str(bug["dupe_of"])
                        if dupeofid == _id or dupeofid in dupid:
                            # avoid infinite loop if any
                            dup[_id].append("cycle")
                        else:
                            dup[_id].append(dupeofid)
                            _set.add(dupeofid)

        bz.bughandler = Handler(bughandler2)

        while _set:
            bz.bugids = list(_set)
            _set.clear()
            bz.got_data = False
            bz.get_data().wait_bugs()

        if only_final:
            for k, v in dup.items():
                dup[k] = v[-1] if v else None

        return dup

    @staticmethod
    def get_history_matches(history, change_to_match):
        history_entries = []

        for history_entry in history:
            for change in history_entry["changes"]:
                matches = True

                for change_key, change_value in change.items():
                    for key, value in change_to_match.items():
                        if (
                            key == change_key
                            and value != change_value
                            and value not in change_value.split(", ")
                        ):
                            matches = False
                            break

                    if not matches:
                        break

                if matches:
                    history_entries.append(history_entry)
                    break

        return history_entries

    @staticmethod
    def get_landing_patterns(channels=["release", "beta", "aurora", "nightly"]):
        if not isinstance(channels, list):
            channels = [channels]

        landing_patterns = []
        for channel in channels:
            if channel in ["central", "nightly"]:
                landing_patterns += [
                    (
                        re.compile(
                            r"://hg.mozilla.org/mozilla-central/rev/([0-9a-f]+)"
                        ),
                        channel,
                    ),
                    (
                        re.compile(
                            r"://hg.mozilla.org/mozilla-central/pushloghtml\?changeset=([0-9a-f]+)"
                        ),
                        channel,
                    ),
                ]
            elif channel == "inbound":
                landing_patterns += [
                    (
                        re.compile(
                            r"://hg.mozilla.org/integration/mozilla-inbound/rev/([0-9a-f]+)"
                        ),
                        "inbound",
                    )
                ]
            elif channel in ["release", "beta", "aurora"]:
                landing_patterns += [
                    (
                        re.compile(
                            r"://hg.mozilla.org/releases/mozilla-"
                            + channel
                            + "/rev/([0-9a-f]+)"
                        ),
                        channel,
                    )
                ]
            elif channel == "esr":
                landing_patterns += [
                    (
                        re.compile(
                            r"://hg.mozilla.org/releases/mozilla-esr(?:[0-9]+)/rev/([0-9a-f]+)"
                        ),
                        channel,
                    )
                ]
            elif channel == "fx-team":
                landing_patterns += [
                    (
                        re.compile(
                            r"://hg.mozilla.org/integration/fx-team/rev/([0-9a-f]+)"
                        ),
                        "inbound",
                    )
                ]
            elif channel == "autoland":
                landing_patterns += [
                    (
                        re.compile(
                            r"://hg.mozilla.org/integration/autoland/rev/([0-9a-f]+)"
                        ),
                        "autoland",
                    )
                ]
            else:
                raise Exception("Unexpected channel: " + channel)

        return landing_patterns

    @staticmethod
    def get_landing_comments(comments, channels, landing_patterns=None):
        if not landing_patterns:
            landing_patterns = Bugzilla.get_landing_patterns(channels)

        results = []

        for comment in comments:
            for landing_pattern in landing_patterns:
                for match in landing_pattern[0].finditer(comment["text"]):
                    results.append(
                        {
                            "comment": comment,
                            "revision": match.group(1),
                            "channel": landing_pattern[1],
                        }
                    )

        return results

    @staticmethod
    def get_status_flags(base_versions=None):
        if not base_versions:
            base_versions = libmozdata.versions.get(base=True)

        status_flags = {}
        for c, v in base_versions.items():
            v = str(v)
            if c == "esr":
                f = "cf_status_firefox_esr" + v
            else:
                f = "cf_status_firefox" + v
            status_flags[c] = f

        return status_flags

    @staticmethod
    def get_signatures(bugids):
        """Get the signatures in the bugs

        Args:
            bugids (list): list of bug ids

        Returns:
            (list): list of accessible bugs
        """
        if not bugids:
            return None

        def bug_handler(bug, data):
            data[str(bug["id"])] = utils.signatures_parser(
                bug.get("cf_crash_signature", None)
            )

        bugids = utils.get_str_list(bugids)
        data = {bugid: [] for bugid in bugids}
        Bugzilla(
            bugids=bugids,
            include_fields=["id", "cf_crash_signature"],
            bughandler=bug_handler,
            bugdata=data,
        ).wait()

        return data

    @staticmethod
    def remove_private_bugs(bugids):
        """Remove private bugs from the list

        Args:
            bugids (list): list of bug ids

        Returns:
            (list): list of accessible bugs
        """

        def bughandler(bug, data):
            data.append(str(bug["id"]))

        data = []
        Bugzilla(
            bugids, include_fields=["id"], bughandler=bughandler, bugdata=data
        ).wait()

        return data

    def __is_bugid(self):
        """Check if the first bugid is a bug id or a search query

        Returns:
            (bool): True if the first bugid is a bug id or None
        """
        if self.bugids:
            bugid = self.bugids[0]
            if not isinstance(bugid, dict) and str(bugid).isdigit():
                return True
        else:
            return True

        return False

    def __get_bugs_for_history_comment(self):
        """Get history and comment (if there are some handlers) after a search query"""
        if (
            self.historyhandler.isactive()
            or self.commenthandler.isactive()
            or self.attachmenthandler.isactive()
        ):
            bugids = []
            bughandler = self.bughandler

            def __handler(bug, bd):
                bughandler.handle(bug)
                bd.append(bug["id"])

            self.bughandler = Handler(__handler, bugids)

            self.__get_bugs_by_search()
            self.wait_bugs()

            self.bughandler = bughandler
            self.bugids = bugids

            if self.historyhandler.isactive():
                self.history_results = []
                self.__get_history()
            if self.commenthandler.isactive():
                self.comment_results = []
                self.__get_comment()
            if self.attachmenthandler.isactive():
                self.attachment_results = []
                self.__get_attachment()
        else:
            self.__get_bugs_by_search()

    def __bugs_cb(self, res, *args, **kwargs):
        """Callback for bug query

        Args:
            sess: session
            res: result
        """
        if res.status_code == 200:
            data = res.json()
            for bug in data["bugs"]:
                self.bughandler.handle(bug)
        elif self.RAISE_ERROR:
            res.raise_for_status()

    def __get_bugs(self):
        """Get the bugs"""
        header = self.get_header()
        for bugids in Connection.chunks(
            sorted(self.bugids, key=lambda k: int(k)),
            chunk_size=Bugzilla.BUGZILLA_CHUNK_SIZE,
        ):
            self.bugs_results.append(
                self.session.get(
                    Bugzilla.API_URL,
                    params={
                        "id": ",".join(map(str, bugids)),
                        "include_fields": self.include_fields,
                    },
                    headers=header,
                    verify=True,
                    timeout=self.TIMEOUT,
                    hooks={"response": self.__bugs_cb},
                )
            )

    def __get_bugs_by_search(self):
        """Get the bugs in making a search query"""
        url = Bugzilla.API_URL + "?"
        header = self.get_header()
        specials = {"count_only", "limit", "order", "offset"}
        for query in self.bugids:
            if isinstance(query, six.string_types):
                url = Bugzilla.API_URL + "?" + query
                self.bugs_results.append(
                    self.session.get(
                        url,
                        headers=header,
                        verify=True,
                        timeout=self.TIMEOUT,
                        hooks={"response": self.__bugs_cb},
                    )
                )
            elif specials.isdisjoint(query.keys()):
                url = Bugzilla.API_URL
                params = query.copy()
                params["count_only"] = 1
                r = requests.get(
                    url,
                    params=params,
                    headers=header,
                    verify=True,
                    timeout=self.TIMEOUT,
                )
                if r.ok:
                    data = r.json()
                    count = data["bug_count"]
                    del params["count_only"]
                    params["limit"] = Bugzilla.BUGZILLA_CHUNK_SIZE
                    params["order"] = "bug_id"
                    for i in range(0, count, Bugzilla.BUGZILLA_CHUNK_SIZE):
                        # Batch the execution to avoid timeouts
                        params = params.copy()
                        params["offset"] = i
                        self.bugs_results.append(
                            self.session.get(
                                url,
                                params=params,
                                headers=header,
                                verify=True,
                                timeout=self.TIMEOUT,
                                hooks={"response": self.__bugs_cb},
                            )
                        )
            else:
                self.bugs_results.append(
                    self.session.get(
                        url,
                        params=query,
                        headers=header,
                        verify=True,
                        timeout=self.TIMEOUT,
                        hooks={"response": self.__bugs_cb},
                    )
                )

    def __get_bugs_list(self):
        """Get the bugs list corresponding to the search query"""
        _list = set()

        def cb(res, *args, **kwargs):
            if res.status_code == 200:
                data = res.json()
                for bug in data["bugs"]:
                    _list.add(bug["id"])
            elif self.RAISE_ERROR:
                res.raise_for_status()

        results = []
        url = Bugzilla.API_URL + "?"
        header = self.get_header()
        for query in self.bugids:
            results.append(
                self.session.get(
                    url + query,
                    headers=header,
                    verify=True,
                    timeout=self.TIMEOUT,
                    hooks={"response": cb},
                )
            )

        for r in results():
            r.result()

        return list(_list)

    def __history_cb(self, res, *args, **kwargs):
        """Callback for bug history

        Args:
            sess: session
            res: result
        """
        if res.status_code == 200:
            json = res.json()
            if "bugs" in json and json["bugs"]:
                for h in json["bugs"]:
                    self.historyhandler.handle(h)
        elif self.RAISE_ERROR:
            res.raise_for_status()

    def __get_history(self):
        """Get the bug history"""
        url = Bugzilla.API_URL + "/%s/history"
        header = self.get_header()
        # TODO: remove next line after the fix of bug 1283392
        bugids = self.__get_no_private_ids()
        for _bugids in Connection.chunks(
            sorted(bugids, key=lambda k: int(k)),
            chunk_size=Bugzilla.BUGZILLA_CHUNK_SIZE,
        ):
            first = _bugids[0]
            remainder = _bugids[1:] if len(_bugids) >= 2 else []
            self.history_results.append(
                self.session.get(
                    url % first,
                    headers=header,
                    params={"ids": remainder},
                    verify=True,
                    timeout=self.TIMEOUT,
                    hooks={"response": self.__history_cb},
                )
            )

    def __comment_cb(self, res, *args, **kwargs):
        """Callback for bug comment

        Args:
            sess: session
            res: result
        """
        if res.status_code == 200:
            json = res.json()
            if "bugs" in json:
                bugs = json["bugs"]
                if bugs:
                    for key in bugs.keys():
                        if isinstance(key, six.string_types) and key.isdigit():
                            comments = bugs[key]
                            self.commenthandler.handle(comments, key)
        elif self.RAISE_ERROR:
            res.raise_for_status()

    def __get_comment(self):
        """Get the bug comment"""
        url = Bugzilla.API_URL + "/%s/comment"
        header = self.get_header()
        # TODO: remove next line after the fix of bug 1283392
        bugids = self.__get_no_private_ids()
        for _bugids in Connection.chunks(
            sorted(bugids, key=lambda k: int(k)),
            chunk_size=Bugzilla.BUGZILLA_CHUNK_SIZE,
        ):
            first = _bugids[0]
            remainder = _bugids[1:] if len(_bugids) >= 2 else []
            self.comment_results.append(
                self.session.get(
                    url % first,
                    headers=header,
                    params={
                        "ids": remainder,
                        "include_fields": self.comment_include_fields,
                    },
                    verify=True,
                    timeout=self.TIMEOUT,
                    hooks={"response": self.__comment_cb},
                )
            )

    def __attachment_bugs_cb(self, res, *args, **kwargs):
        """Callback for bug attachment

        Args:
            sess: session
            res: result
        """
        if res.status_code == 200:
            json = res.json()
            if "bugs" in json:
                bugs = json["bugs"]
                if bugs:
                    for key in bugs.keys():
                        if isinstance(key, six.string_types) and key.isdigit():
                            attachments = bugs[key]
                            self.attachmenthandler.handle(attachments, key)
        elif self.RAISE_ERROR:
            res.raise_for_status()

    def __attachment_cb(self, res, *args, **kwargs):
        """Callback for bug attachment

        Args:
            sess: session
            res: result
        """
        if res.status_code == 200:
            json = res.json()
            attachments = json.get("attachments")
            if attachments:
                self.attachmenthandler.handle(list(attachments.values()))
        elif self.RAISE_ERROR:
            res.raise_for_status()

    def __get_attachment(self):
        """Get the bug attachment"""
        header = self.get_header()
        if self.attachmentids:
            url = Bugzilla.API_URL + "/attachment/%s"
            ids = self.attachmentids
            field = "attachment_ids"
            cb = self.__attachment_cb
        else:
            url = Bugzilla.API_URL + "/%s/attachment"
            # TODO: remove next line after the fix of bug 1283392
            ids = self.__get_no_private_ids()
            field = "ids"
            cb = self.__attachment_bugs_cb

        for _ids in Connection.chunks(
            sorted(ids, key=lambda k: int(k)), chunk_size=Bugzilla.BUGZILLA_CHUNK_SIZE
        ):
            first = _ids[0]
            remainder = _ids[1:] if len(_ids) >= 2 else []
            self.attachment_results.append(
                self.session.get(
                    url % first,
                    headers=header,
                    params={
                        field: remainder,
                        "include_fields": self.attachment_include_fields,
                    },
                    verify=True,
                    timeout=self.TIMEOUT,
                    hooks={"response": cb},
                )
            )


class BugzillaUser(BugzillaBase):
    """Connection to bugzilla.mozilla.org"""

    API_URL = BugzillaBase.URL + "/rest/user"

    def __init__(
        self,
        user_names=None,
        search_strings=None,
        include_fields="_default",
        user_handler=None,
        fault_user_handler=None,
        user_data=None,
        **kwargs,
    ):
        """Constructor

        Args:
            user_names (List[str]): list of user names or IDs
            search_strings (List[str]): list of search strings
            include_fields (List[str]): list of include fields
            user_handler (Optional[function]): the handler to use with each retrieved user
            fault_user_handler (Optional[function]): the handler to use with
                each user error (e.g. user not existed).
            user_data (Optional): the data to use with the user handler
        """
        self.user_handler = Handler.get(user_handler, user_data)
        self.fault_user_handler = Handler.get(fault_user_handler, user_data)

        if user_names is not None:
            if isinstance(user_names, six.string_types) or isinstance(user_names, int):
                user_names = [user_names]

            params = [
                {
                    "include_fields": include_fields,
                    "names": [
                        user_name
                        for user_name in user_names
                        if isinstance(user_name, six.string_types)
                        and not user_name.isdigit()
                    ],
                    "ids": [
                        str(user_id)
                        for user_id in user_names
                        if isinstance(user_id, int) or user_id.isdigit()
                    ],
                    "permissive": fault_user_handler is not None or None,
                }
                for user_names in self.chunks(
                    user_names, chunk_size=Bugzilla.BUGZILLA_CHUNK_SIZE
                )
            ]

            super(BugzillaUser, self).__init__(
                BugzillaUser.URL,
                Query(BugzillaUser.API_URL, params, self.__users_cb),
                **kwargs,
            )
        elif search_strings is not None:
            if isinstance(search_strings, six.string_types):
                search_strings = [search_strings]

            queries = []
            for search_string in search_strings:
                queries.append(
                    Query(
                        BugzillaUser.API_URL + "?" + search_string,
                        handler=self.__users_cb,
                    )
                )

            super(BugzillaUser, self).__init__(BugzillaUser.URL, queries, **kwargs)

    def __users_cb(self, res):
        if self.user_handler.isactive():
            for user in res["users"]:
                self.user_handler.handle(user)

        if self.fault_user_handler.isactive():
            for user in res["faults"]:
                self.fault_user_handler.handle(user)


class BugzillaProduct(BugzillaBase):
    """
    Connection to bugzilla.mozilla.org

    API docs: https://bugzilla.readthedocs.io/en/latest/api/core/v1/product.html
    """

    API_URL = BugzillaBase.URL + "/rest/product"

    def __init__(
        self,
        product_names=None,
        product_types=None,
        include_fields="_default",
        product_handler=None,
        product_data=None,
        **kwargs,
    ):
        """Constructor

        Args:
            product_names (List[str]): search query or list of product names or IDs
            product_types (List[str]): list of the group of products to return
            include_fields (List[str]): list of include fields
            product_handler (Optional[function]): the handler to use with each retrieved product
            product_data (Optional): the data to use with the product handler
        """
        self.product_handler = Handler.get(product_handler, product_data)

        if isinstance(product_names, dict):
            if include_fields or product_types:
                params = product_names.copy()
            else:
                params = product_names

            if include_fields:
                if "include_fields" in params:
                    if isinstance(include_fields, six.string_types):
                        include_fields = [include_fields]
                    if isinstance(params.get("include_fields"), six.string_types):
                        params["include_fields"] = [params["include_fields"]]

                    params["include_fields"] = list(
                        set(params["include_fields"]).union(include_fields)
                    )
                else:
                    params["include_fields"] = include_fields

            if product_types:
                if "type" in params:
                    if isinstance(product_types, six.string_types):
                        product_types = [product_types]
                    if isinstance(params.get("type"), six.string_types):
                        params["type"] = [params["type"]]

                    params["type"] = list(set(params["type"]).union(product_types))
                else:
                    params["type"] = product_types

        elif product_names is not None:
            if isinstance(product_names, six.string_types) or isinstance(
                product_names, int
            ):
                product_names = [product_names]

            params = {
                "include_fields": include_fields,
                "type": product_types,
                "names": [
                    product_name
                    for product_name in product_names
                    if isinstance(product_name, six.string_types)
                    and not product_name.isdigit()
                ],
                "ids": [
                    str(product_id)
                    for product_id in product_names
                    if isinstance(product_id, int) or product_id.isdigit()
                ],
            }

        elif product_types is not None:
            params = {
                "include_fields": include_fields,
                "type": product_types,
            }

        else:
            raise Exception(
                "Should set one of the following: product_names or product_types"
            )

        super(BugzillaProduct, self).__init__(
            BugzillaProduct.URL,
            Query(BugzillaProduct.API_URL, params, self.__products_cb),
            **kwargs,
        )

    def __products_cb(self, res):
        if not self.product_handler.isactive():
            return

        for product in res["products"]:
            self.product_handler.handle(product)


class BugzillaShorten(BugzillaBase):
    """
    Connection to bugzilla.mozilla.org
    """

    API_URL = BugzillaBase.URL + "/rest/bitly/shorten"

    def __init__(self, url, url_data=None, url_handler=None, **kwargs):
        """Constructor

        Args:
            url (List[str]): the url to shorten
            url_handler (Optional[function]): the handler to use with each retrieved url
            url_data (Optional): the data to use with the url handler
        """
        self.url_handler = Handler.get(url_handler, url_data)

        params = {
            "url": url,
        }

        super(BugzillaShorten, self).__init__(
            BugzillaShorten.URL,
            Query(BugzillaShorten.API_URL, params, self.__urls_cb),
            **kwargs,
        )

    def __urls_cb(self, res):
        if not self.url_handler.isactive():
            return

        if not isinstance(res, dict):
            # This is a workaround to handle cases where Bugzilla returns 200
            # response with HTML content instead of 4xx error.
            # See https://github.com/mozilla/libmozdata/issues/227
            if self.RAISE_ERROR:
                raise HTTPError("The response is not a valid JSON")
            return

        self.url_handler.handle(res["url"])


class BugzillaComponent(BugzillaBase):
    """
    Connection to bugzilla.mozilla.org
    """

    API_URL = BugzillaBase.URL + "/rest/component"

    def __init__(
        self, product, component, component_data=None, component_handler=None, **kwargs
    ):
        """Constructor

        Args:
            product (str): the product that the component belongs to
            component (str): the name of the component
            component_handler (Optional[function]): the handler to use with each retrieved component
            component_data (Optional): the data to use with the component handler
        """
        self.component_handler = Handler.get(component_handler, component_data)
        params = {
            "product": product,
            "component": component,
        }

        super(BugzillaComponent, self).__init__(
            BugzillaComponent.URL,
            Query(
                BugzillaComponent.API_URL,
                params,
                self.__components_cb,
            ),
            **kwargs,
        )

    def __components_cb(self, res):
        if not self.component_handler.isactive():
            return

        self.component_handler.handle(res)

    def put(self, data):
        """Update a component

        Args:
            data (dict): a dictionary
        """

        assert len(self.queries) == 1
        query = self.queries[0]

        response = requests.put(
            query.url,
            params=query.params,
            json=data,
            headers=self.get_header(),
        )
        response.raise_for_status()

        return response.json()


class BugFields(BugzillaBase):
    """Fetching bug fields information from Bugzilla

    Docs: https://bmo.readthedocs.io/en/latest/api/core/v1/field.html#fields
    """

    API_URL = BugzillaBase.URL + "/rest/field/bug"

    def __init__(
        self, field=None, handler=None, handlerdata=None, queries=None, **kwargs
    ):
        """Constructor

        Args:
            field (Optional[str]): the name of the field, if empty will fetch all fields
            handler (Optional[function]): the handler to use with each retrieved field
            handlerdata (Optional): the data to use with the field handler
            queries (Optional[Query]): the queries to use
        """
        if not queries:
            endpoint_url = f"{self.API_URL}/{field}" if field else self.API_URL
            queries = Query(endpoint_url, None, handler, handlerdata)

        super(BugFields, self).__init__(self.URL, queries, **kwargs)

    @classmethod
    def fetch_all_fields_info(cls):
        """Get information about all fields

        Returns:
            list: the information about the fields
        """

        def handler(resp, data):
            data.update(resp)

        data = {}
        cls(
            handler=handler,
            handlerdata=data,
        ).wait()

        return data["fields"]

    @classmethod
    def fetch_field_info(cls, field):
        """Get information about a field

        Args:
            field (str): the name of the field

        Returns:
            dict: the information about the field
        """

        def handler(resp, data):
            data.update(resp)

        data = {}
        cls(
            field=field,
            handler=handler,
            handlerdata=data,
        ).wait()

        field_info = data["fields"][0]
        assert field_info["name"] == field

        return field_info

    @classmethod
    def fetch_field_values(cls, field):
        """Get the legal values of a field

        Args:
            field (str): the name of the field

        Returns:
            List[str]: the legal values of the field
        """
        return [value["name"] for value in cls.fetch_field_info(field)["values"]]
