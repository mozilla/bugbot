# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import numbers
from datetime import datetime, timedelta, timezone
from pprint import pprint

from . import config, modules, utils
from .BZInfo import BZInfo
from .HGFileInfo import HGFileInfo


class FileStats(object):
    """Stats about a file in the repo."""

    def __init__(
        self, path, channel="nightly", node="default", utc_ts=None, max_days=None
    ):
        """Constructor

        Args:
            path (str): file path
            channel (str): channel version of firefox
            node (Optional[str]): the node, by default 'default'
            utc_ts (Optional[int]): UTC timestamp, file pushdate <= utc_ts
        """
        self.utc_ts = (
            utc_ts if isinstance(utc_ts, numbers.Number) and utc_ts > 0 else None
        )
        self.max_days = (
            max_days
            if isinstance(max_days, numbers.Number)
            else int(config.get("FileStats", "MaxDays", 3))
        )
        self.utc_ts_from = (
            utils.get_timestamp(
                datetime.fromtimestamp(utc_ts, tz=timezone.utc)
                + timedelta(-self.max_days)
            )
            if isinstance(utc_ts, numbers.Number) and utc_ts > 0
            else None
        )
        self.path = path
        self.hi = HGFileInfo(path, channel=channel, node=node)
        self.module = modules.module_from_path(path)

    def get_static_info(self):
        info = {
            "path": self.path,
            "guilty": None,
            "needinfo": None,
            "components": set(),
        }

        if self.module is not None:
            info["module"] = self.module["name"]
            info["components"].update(self.module["bugzillaComponents"])
            info["owners"] = self.module["owners"]
            info["peers"] = self.module["peers"]

        return info

    def get_last_patches(self):
        return self.hi.get(self.path, self.utc_ts_from, self.utc_ts)["patches"]

    def get_info(self, guilty_only=False):
        """Get info

        Args:
            guilty_only(Optional[bool]): if True then return only info if we have a guilty set of patches

        Returns:
            dict: info
        """

        last = self.get_last_patches()
        if guilty_only and not last:
            return None

        info = self.get_static_info()

        if last:  # we have a 'guilty' set of patches
            stats = {}
            last_author = None
            for patch in last:
                author = patch["user"]
                if not last_author:
                    last_author = author
                stats[author] = stats[author] + 1 if author in stats else 1

            info["guilty"] = {
                "main_author": utils.get_best(stats) if stats else None,
                "last_author": last_author,
                "patches": last,
            }

        bugs = self.hi.get(self.path)["bugs"]
        bi = BZInfo(bugs) if bugs else None
        if bi:
            # find out the good person to query for a needinfo
            info["needinfo"] = bi.get_best_collaborator()
            comp_prod = bi.get_best_component_product()
            if comp_prod:
                info["infered_component"] = comp_prod[1] + "::" + comp_prod[0]
            info["bugs"] = len(bugs)

        return info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="File Stats")
    parser.add_argument("-p", "--path", action="store", help="file path")
    parser.add_argument(
        "-n",
        "--node",
        action="store",
        default="default",
        help="Mercurial node, by default 'default'",
    )
    parser.add_argument(
        "-c", "--channel", action="store", default="nightly", help="release channel"
    )
    parser.add_argument(
        "-d",
        "--date",
        action="store",
        default="today",
        help="max date for pushdate, format YYYY-mm-dd",
    )

    args = parser.parse_args()

    if args.path:
        fs = FileStats(
            args.path, args.channel, args.node, utils.get_timestamp(args.date)
        )
        pprint(fs.get_info())
