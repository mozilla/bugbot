# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import six

from . import config
from .connection import Connection, Query


class Mercurial(Connection):
    """Mozilla mercurial connection: http://hg.mozilla.org"""

    HG_URL = config.get("Mercurial", "URL", "https://hg.mozilla.org")
    remote = HG_URL == "https://hg.mozilla.org"

    def __init__(self, queries, channel="nightly", **kwargs):
        """Constructor

        Args:
            queries (List[Query]): queries to pass to mercurial server
            channel (Optional[str]): the channel, by default 'nightly'
        """
        super(Mercurial, self).__init__(self.HG_URL, queries, **kwargs)
        self.channel = channel

    @staticmethod
    def get_repo(channel):
        """Get the repo name

        Args:
            channel (str): channel version of firefox

        Returns:
            str: the repo name
        """
        if channel == "nightly" or channel == "central":
            return "mozilla-central"
        elif channel == "inbound":
            return "integration/mozilla-inbound"
        else:
            return "releases/mozilla-" + channel

    @staticmethod
    def get_repo_url(channel):
        """Get the repo url

        Args:
            channel (str): channel version of firefox

        Returns:
            str: the repo url
        """
        if Mercurial.remote:
            return Mercurial.HG_URL + "/" + Mercurial.get_repo(channel)
        else:
            return Mercurial.HG_URL


class Revision(Mercurial):
    """Connection to get a revision"""

    def __init__(
        self,
        channel="nightly",
        params=None,
        handler=None,
        handlerdata=None,
        queries=None,
        **kwargs
    ):
        """Constructor

        Args:
            channel (Optional[str]): the channel, by default 'nightly'
            params (Optional[dict]): the params for the query
            handler (Optional[function]): handler to use with the result of the query
            handlerdata (Optional): data used in second argument of the handler
            queries (List[Query]): queries to pass to mercurial server
        """
        if queries:
            super(Revision, self).__init__(queries, **kwargs)
        else:
            super(Revision, self).__init__(
                Query(Revision.get_url(channel), params, handler, handlerdata), **kwargs
            )

    @staticmethod
    def get_url(channel):
        """Get the api url

        Args:
            channel (str): channel version of firefox

        Returns:
            str: the api url
        """
        return Mercurial.get_repo_url(channel) + "/json-rev"

    @staticmethod
    def default_handler(json, data):
        """Default handler

        Args:
            json (dict): json
            data (dict): dictionary to update with data
        """
        data.update(json)

    @staticmethod
    def get_revision(channel="nightly", node="default"):
        """Get the revision for a node

        Args:
            channel (str): channel version of firefox
            node (Optional[str]): the node, by default 'default'

        Returns:
            dict: the revision corresponding to the node
        """
        data = {}
        Revision(channel, {"node": node}, Revision.default_handler, data).wait()
        return data


class RawRevision(Mercurial):
    """Connection to get a raw revision"""

    def __init__(
        self, channel="nightly", params=None, handler=None, queries=None, **kwargs
    ):
        """Constructor

        Args:
            channel (Optional[str]): the channel, by default 'nightly'
            params (Optional[dict]): the params for the query
            handler (Optional[function]): handler to use with the result of the query
            handlerdata (Optional): data used in second argument of the handler
            queries (List[Query]): queries to pass to mercurial server
        """
        if queries:
            super(RawRevision, self).__init__(queries, **kwargs)
        else:
            super(RawRevision, self).__init__(
                Query(RawRevision.get_url(channel), params, handler), **kwargs
            )

    @staticmethod
    def get_url(channel):
        """Get the api url

        Args:
            channel (str): channel version of firefox

        Returns:
            str: the api url
        """
        return Mercurial.get_repo_url(channel) + "/raw-rev"

    @staticmethod
    def get_revision(channel="nightly", node="default"):
        """Get the revision for a node

        Args:
            channel (str): channel version of firefox
            node (Optional[str]): the node, by default 'default'

        Returns:
            dict: the revision corresponding to the node
        """
        data = {}

        def handler(response):
            data["res"] = response

        RawRevision(channel, {"node": node}, handler).wait()

        return data["res"]


class FileInfo(Mercurial):
    """Connection to get file info"""

    def __init__(
        self,
        channel="nightly",
        params=None,
        handler=None,
        handlerdata=None,
        queries=None,
        **kwargs
    ):
        """Constructor

        Args:
            channel (Optional[str]): the channel, by default 'nightly'
            params (Optional[dict]): the params for the query
            handler (Optional[function]): handler to use with the result of the query
            handlerdata (Optional): data used in second argument of the handler
            queries (List[Query]): queries to pass to mercurial server
        """
        if queries:
            super(FileInfo, self).__init__(queries, **kwargs)
        else:
            super(FileInfo, self).__init__(
                Query(FileInfo.get_url(channel), params, handler, handlerdata), **kwargs
            )

    @staticmethod
    def get_url(channel):
        """Get the api url

        Args:
            channel (str): channel version of firefox

        Returns:
            str: the api url
        """
        return Mercurial.get_repo_url(channel) + "/json-filelog"

    @staticmethod
    def default_handler(json, data):
        """Default handler

        Args:
            json (dict): json
            data (dict): dictionary to update with data
        """
        data.update(json)

    @staticmethod
    def get(paths, channel="nightly", node="default"):
        """Get the file info for several paths

        Args:
            paths (List[str]): the paths
            channel (str): channel version of firefox
            node (Optional[str]): the node, by default 'default'

        Returns:
            dict: the files info
        """
        data = {}

        __base = {"node": node, "file": None}

        if isinstance(paths, six.string_types):
            __base["file"] = paths
            _dict = {}
            data[paths] = _dict
            FileInfo(
                channel=channel,
                params=__base,
                handler=FileInfo.default_handler,
                handlerdata=_dict,
            ).wait()
        else:
            url = FileInfo.get_url(channel)
            queries = []
            for path in paths:
                cparams = __base.copy()
                cparams["file"] = path
                _dict = {}
                data[path] = _dict
                queries.append(Query(url, cparams, FileInfo.default_handler, _dict))
            FileInfo(queries=queries).wait()

        return data


class Annotate(Mercurial):
    """Connection to get file annotation (blame)"""

    def __init__(
        self,
        channel="nightly",
        params=None,
        handler=None,
        handlerdata=None,
        queries=None,
        **kwargs
    ):
        """Constructor

        Args:
            channel (Optional[str]): the channel, by default 'nightly'
            params (Optional[dict]): the params for the query
            handler (Optional[function]): handler to use with the result of the query
            handlerdata (Optional): data used in second argument of the handler
            queries (List[Query]): queries to pass to mercurial server
        """
        if queries:
            super(Annotate, self).__init__(queries, **kwargs)
        else:
            super(Annotate, self).__init__(
                Query(Annotate.get_url(channel), params, handler, handlerdata), **kwargs
            )

    @staticmethod
    def get_url(channel):
        """Get the api url

        Args:
            channel (str): channel version of firefox

        Returns:
            str: the api url
        """
        return Mercurial.get_repo_url(channel) + "/json-annotate"

    @staticmethod
    def default_handler(json, data):
        """Default handler

        Args:
            json (dict): json
            data (dict): dictionary to update with data
        """
        data.update(json)

    @staticmethod
    def get(paths, channel="nightly", node="default"):
        """Get the annotated files for several paths

        Args:
            paths (List[str]): the paths
            channel (str): channel version of firefox
            node (Optional[str]): the node, by default 'default'

        Returns:
            dict: the files info
        """
        data = {}

        __base = {"node": node, "file": None}

        if isinstance(paths, six.string_types):
            __base["file"] = paths
            _dict = {}
            data[paths] = _dict
            Annotate(
                channel=channel,
                params=__base,
                handler=Annotate.default_handler,
                handlerdata=_dict,
            ).wait()
        else:
            url = Annotate.get_url(channel)
            queries = []
            for path in paths:
                cparams = __base.copy()
                cparams["file"] = path
                _dict = {}
                data[path] = _dict
                queries.append(Query(url, cparams, Annotate.default_handler, _dict))
            Annotate(queries=queries).wait()

        return data
