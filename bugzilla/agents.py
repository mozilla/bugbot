import os
import re
from bugzilla.models import BugSearch, Bug
from bugzilla.utils import urljoin, qs


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

        self.api_key = api_key

    def get_bug(self, bug, include_fields='_default,token,cc,keywords,whiteboard,comments', exclude_fields=None, params={}):
        params['include_fields'] = [include_fields]
        params['exclude_fields'] = [exclude_fields]

        url = urljoin(self.API_ROOT, 'bug/%s?%s' % (bug, self.qs(**params)))
        try:
            return Bug.get(url)
        except Exception, e:
            pattern = re.compile(
                    r"https://bugzilla.mozilla.org*.+&api_key=(.*?)&"
            )
            api_key = pattern.findall(e.message)[0]
            error = e.message.replace(api_key, '*'*len(api_key))
            raise Exception(error)    

    def get_bug_list(self, params={}):
        url = urljoin(self.API_ROOT, 'bug/?%s' % (self.qs(**params)))
        try:
            return BugSearch.get(url).bugs
        except Exception, e:
            pattern = re.compile(
                    r"https://bugzilla.mozilla.org*.+&api_key=(.*?)&"
            )
            api_key = pattern.findall(e.message)[0]
            error = e.message.replace(api_key, '*'*len(api_key))
            raise Exception(error)

    def qs(self, **params):
        if self.api_key:
            params['api_key'] = [self.api_key]
        return qs(**params)


class BMOAgent(BugzillaAgent):
    def __init__(self, api_key=None):
        super(BMOAgent, self).__init__('https://bugzilla.mozilla.org/bzapi/', api_key)
