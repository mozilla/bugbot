try:
    import httplib
    from remoteobjects import http

    # Printing throws an error if we are printing using ascii
    import sys
    __all__ = ['models', 'utils', 'agents']
    reload(sys)
    sys.setdefaultencoding('utf-8')

    # Monkey patch remoteobjects to accept 202 status codes.
    http.HttpObject.response_has_content[httplib.ACCEPTED] = False
except ImportError:
    # Python 3
    pass


VERSION = (0, 0, 1)
__version__ = '.'.join(map(str, VERSION))
