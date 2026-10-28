# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import namedtuple
from urllib.parse import urljoin

import requests

from . import config


class LandoWarnings(object):
    """
    Encapsulates lando warning calls
    """

    def __init__(self, api_url, api_key):
        self.api_url = f"{api_url}/diff_warnings/"
        self.api_key = api_key
        self.USER_AGENT = config.get("User-Agent", "name", required=True)

    def del_warnings(self, warnings):
        """
        Deletes warnings from Lando based on a json warnings list
        """
        for warning in warnings:
            warning_id = warning["id"]

            response = requests.delete(
                f"{self.api_url}{warning_id}",
                headers={
                    "X-Phabricator-API-Key": self.api_key,
                    "User-Agent": self.USER_AGENT,
                },
            )

            if response.status_code != 200:
                raise Exception(
                    f"Failed to delete warning with ID {warning_id} with error {response.status_code}:\n{response.text}"
                )

    def add_warning(self, warning, revision_id, diff_id):
        """
        Adds a warning to Lando
        """
        response = requests.post(
            self.api_url,
            json={
                "revision_id": revision_id,
                "diff_id": diff_id,
                "group": "LINT",
                "data": {"message": warning},
            },
            headers={
                "X-Phabricator-API-Key": self.api_key,
                "User-Agent": self.USER_AGENT,
            },
        )
        if response.status_code != 201:
            raise Exception(
                f"Failed to add warnings for revision_id {revision_id} and diff_id {diff_id} with error {response.status_code}:\n{response.text}"
            )

    def get_warnings(self, revision_id, diff_id):
        """
        Gets a list of warnings
        """
        response = requests.get(
            self.api_url,
            params={
                "revision_id": revision_id,
                "diff_id": diff_id,
                "group": "LINT",
            },
            headers={
                "X-Phabricator-API-Key": self.api_key,
                "User-Agent": self.USER_AGENT,
            },
        )
        if response.status_code != 200:
            raise Exception(
                f"Failed to get warnings for revision_id {revision_id} and diff_id {diff_id} with error {response.status_code}:\n{response.text}"
            )

        return response.json()

    def del_all_warnings(self, revision_id, diff_id):
        """
        Deletes all warnings
        """
        current_warnings = self.get_warnings(revision_id, diff_id)

        if len(current_warnings):
            return self.del_warnings(current_warnings)


# Represent the commit in both mercurial & git sources, using full hashes
CommitMap = namedtuple("CommitMap", "git_hash, hg_hash")


class LandoMissingCommit(Exception):
    """
    Raised when a commit is not available on Lando CommitMap API
    """


class LandoCommitMapAPI:
    """
    Anonymous API calls on Lando API to convert mercurial <=> git commits
    """

    def __init__(self, api_url="https://lando.moz.tools/api/"):
        self.api_url = api_url
        assert self.api_url.endswith("/"), "Lando API url must end with a /"
        self.USER_AGENT = config.get("User-Agent", "name", required=True)

    def request(self, method, repository, revision) -> CommitMap:
        """
        Call a conversion method on Lando API and return a CommitMap object
        with both full hashes
        """
        url = urljoin(self.api_url, f"{method}/{repository}/{revision}")
        resp = requests.get(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
            },
        )
        if not resp.ok:
            if resp.status_code == 404:
                raise LandoMissingCommit(
                    f"No commit found for {method} {revision}@{repository}"
                )

            raise Exception(
                f"Failed to resolve {method} {revision}@{repository}: {resp.text}"
            )

        return CommitMap(**resp.json())

    def git2hg(self, revision: str, repository="firefox") -> CommitMap:
        """
        Convert a git hash into a mercurial one
        """
        return self.request("git2hg", repository, revision)

    def hg2git(self, revision: str, repository="firefox") -> CommitMap:
        """
        Convert a mercurial hash into a git one
        """
        return self.request("hg2git", repository, revision)
