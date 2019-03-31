import os
import httplib2
import urlparse
from auto_nag.bugzilla.models import BugSearch
from auto_nag.bugzilla.utils import urljoin, qs, hide_personal_info


class Http(httplib2.Http):
    def __init__(self, api_key=None):
        super(Http, self).__init__()
        self.api_key = api_key
        self.proxy_info = None

    def request(self, uri, method='GET', body=None, headers=None, redirections=5, connection_type=None):
        if headers is None:
            headers = {}
        if 'user-agent' not in headers:
            headers['user-agent'] = 'relman-auto-nag'
        if self.api_key is not None:
            scheme, netloc, path, query, frag = urlparse.urlsplit(uri)
            if 'api_key' not in urlparse.parse_qs(query):
                query += '&api_key=%s' % self.api_key
                uri = urlparse.urlunsplit((scheme, netloc, path, query, frag))
        return super(Http, self).request(uri, method=method, body=body, headers=headers, redirections=redirections, connection_type=connection_type)


class InvalidAPI_ROOT(Exception):
    def __str__(self):
        return "Invalid API url specified. " + \
               "Please set BZ_API_ROOT in your environment " + \
               "or pass it to the agent constructor"


class BugzillaAgent(object):
    def __init__(self, api_root=None, api_key=None):
        if not api_root:
            api_root = os.environ.get('BZ_API_ROOT')
            if not api_root:
                raise InvalidAPI_ROOT
        self.API_ROOT = api_root
        self.http = Http(api_key)

    def get_bug(self, bug, include_fields='_default', exclude_fields=None, params={}):
        params['include_fields'] = [include_fields]
        params['exclude_fields'] = [exclude_fields]

        url = urljoin(self.API_ROOT, 'bug/%s?%s' % (bug, qs(**params)))
        try:
            return BugSearch.get(url, http=self.http).bugs[0]
        except Exception as e:
            raise Exception(hide_personal_info(str(e)))

    def get_bug_list(self, params={}):
        url = urljoin(self.API_ROOT, 'bug?%s' % (qs(**params)))
        try:
            return BugSearch.get(url, http=self.http).bugs
        except Exception as e:
            raise Exception(hide_personal_info(str(e)))


class BMOAgent(BugzillaAgent):
    def __init__(self, api_key=None):
        super(BMOAgent, self).__init__('https://bugzilla.mozilla.org/rest/', api_key)
