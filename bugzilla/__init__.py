import httplib

from remoteobjects import http


# Monkey patch remoteobjects to accept 202 status codes.
http.HttpObject.response_has_content[httplib.ACCEPTED] = False


VERSION = (0, 0, 1)
__version__ = '.'.join(map(str, VERSION))
