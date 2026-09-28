# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import requests

from . import config


class FirefoxTrains:
    """Firefox Trains

    Documentations: https://whattrainisitnow.com/about
    """

    URL = "https://whattrainisitnow.com/api/"
    TIMEOUT = 30

    _instance = None

    def __init__(self, cache: bool = True) -> None:
        """Constructor

        Args:
            cache: If True, the API responses will be cached.
        """

        self._cache = {} if cache else None
        self.USER_AGENT = config.get("User-Agent", "name", required=True)

    @classmethod
    def get_instance(cls):
        """Get the singleton instance of FirefoxTrains."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __get(self, path):
        if self._cache is not None and path in self._cache:
            return self._cache[path]

        resp = requests.get(
            self.URL + path,
            timeout=self.TIMEOUT,
            headers={"User-Agent": self.USER_AGENT},
        )
        resp.raise_for_status()
        resp_json = resp.json()

        if self._cache is not None:
            self._cache[path] = resp_json

        return resp_json

    def get_release_schedule(self, channel):
        """Get the release schedule for a given channel.

        Args:
            channel (str): The channel to get the release schedule for. Can be
                a version number or one of the beta or nightly keywords.

        Returns:
            dict: The release schedule for the given channel.
        """

        api_path = f"release/schedule/?version={channel}"
        return self.__get(api_path)

    def get_release_owners(self):
        """Get the historical list of all release managers for Firefox major
        release.

        We don't have the names before Firefox 27

        Returns:
            dict: the release number as key and the release owner as value.
        """

        api_path = "release/owners/"
        return self.__get(api_path)

    def get_firefox_releases(self):
        """Get release dates for all Firefox releases (including dot releases)
        Returns:
            dict: the release number as key and the release date as value.
        """

        api_path = "firefox/releases/"
        return self.__get(api_path)

    def get_lando_uplift_train(self):
        """Get the current version and release date for each channel.

        Returns:
            dict: keyed by channel (nightly, beta, release, esr, esr_previous),
                each value a dict with at least a "version" (int) key. A channel
                may be null (e.g. esr_previous outside an ESR overlap period).
        """

        api_path = "lando/uplift/train/"
        return self.__get(api_path)

    # TODO: add methods for the other API endpoints
