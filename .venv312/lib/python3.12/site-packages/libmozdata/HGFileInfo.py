# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import re

import six

from . import hgmozilla
from .connection import Query


class HGFileInfo(object):
    """File info from Mercurial

    We collect the different authors, reviewers and related bugs from the patches which touched to the file.
    The patches can be filtered according to pushdate.
    """

    MAX_REV_COUNT = 4095

    def __init__(self, paths, channel="nightly", node="default", date_type="push"):
        """Constructor

        Args:
            paths (List[str]): the paths
            channel (str): channel version of firefox
            node (Optional[str]): the node, by default 'default'
        """
        self.channel = channel
        self.node = node
        self.date_type = "date" if date_type == "creation" else "pushdate"
        self.data = {}
        self.paths = [paths] if isinstance(paths, six.string_types) else paths
        for p in self.paths:
            self.data[p] = []
        self.bug_pattern = re.compile(r"[\t ]*[Bb][Uu][Gg][\t ]*([0-9]+)")
        self.rev_pattern = re.compile(r"r=([a-zA-Z0-9]+)")
        self.results = []
        self.__get_info(self.paths, self.node)

    def get(self, path, utc_ts_from=None, utc_ts_to=None, authors=[]):
        if utc_ts_to is None:
            revision = hgmozilla.Revision.get_revision(self.channel, self.node)
            assert self.date_type in revision
            assert isinstance(revision[self.date_type], list)
            utc_ts_to = revision[self.date_type][0]

        for result in self.results:
            result.wait()

        author_pattern = re.compile(r"<([^>]+)>")
        email_pattern = re.compile(r"<?([\w\-\._\+%]+@[\w\-\._\+%]+)>?")

        entries = self.data[path]

        authors_result = {}
        bugs = set()
        patches = []

        for entry in entries:
            assert self.date_type in entry

            # no pushdate
            # TODO: find a way to estimate the pushdate (e.g. (prev + next) / 2 or use the author date)
            if entry[self.date_type] == "":
                logging.getLogger(__name__).warning(
                    "Entry for file %s with node %s has no pushdate"
                    % (path, entry["node"])
                )
                continue

            assert isinstance(entry[self.date_type], list)
            utc_date = entry[self.date_type][0]

            if (
                utc_ts_from is not None and utc_ts_from > utc_date
            ) or utc_ts_to < utc_date:
                continue

            m = author_pattern.search(entry["user"])
            if m is None:
                m = email_pattern.search(entry["user"])
            if m:
                entry["user"] = m.group(1)
            patch_author = entry["user"]
            if authors and patch_author not in authors:
                continue

            if patch_author not in authors_result:
                authors_result[patch_author] = {"count": 1, "reviewers": {}}
            else:
                authors_result[patch_author]["count"] += 1

            info_desc = self.__get_info_from_desc(entry["desc"])
            starter = info_desc["starter"]
            if starter:
                bugs.add(info_desc["starter"])

            reviewers = info_desc["reviewers"]
            if reviewers:
                _reviewers = authors_result[patch_author]["reviewers"]
                for reviewer in reviewers:
                    if reviewer not in _reviewers:
                        _reviewers[reviewer] = 1
                    else:
                        _reviewers[reviewer] += 1

            patches.append(entry)

        return {"authors": authors_result, "bugs": bugs, "patches": patches}

    def __get_info_from_desc(self, desc):
        """Get some information from the patch description

        Args:
            desc (str): the description

        Returns:
            dict: some information
        """
        desc = desc.strip()
        info = {"starter": "", "refs": set(), "reviewers": set()}
        s = info["refs"]
        for m in self.bug_pattern.finditer(desc):
            if m.start(0) == 0:
                # the description begins with Bug 1234....
                info["starter"] = m.group(1)
            s.add(m.group(1))

        for m in self.rev_pattern.finditer(desc):
            info["reviewers"].add(m.group(1))

        return info

    def __handler(self, json, path):
        """Handler

        Args:
            json (dict): json
            info (dict): info
        """
        entries = json["entries"]
        if entries:
            if len(entries) == HGFileInfo.MAX_REV_COUNT + 1:
                self.data[path].extend(entries[:-1])
                last_node = entries[-1]["node"]
                self.__get_info([path], last_node)
            else:
                self.data[path].extend(entries)

    def __get_info(self, paths, node):
        """Get info"""
        __base = {"node": node, "file": None, "revcount": HGFileInfo.MAX_REV_COUNT + 1}
        queries = []
        url = hgmozilla.FileInfo.get_url(self.channel)
        for path in paths:
            cparams = __base.copy()
            cparams["file"] = path
            queries.append(
                Query(url, cparams, handler=self.__handler, handlerdata=path)
            )

        self.results.append(hgmozilla.FileInfo(queries=queries))
