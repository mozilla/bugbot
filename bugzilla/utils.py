import base64
from ConfigParser import ConfigParser
import getpass
import os
import posixpath
import urllib


def urljoin(base, *args):
    """Remove any leading slashes so no subpaths look absolute."""
    return posixpath.join(base, *[str(s).lstrip('/') for s in args])


def qs(**kwargs):
    """Build a URL query string."""
    return '&'.join('%s=%s' % tuple(map(urllib.quote, map(str, pair)))
                    for pair in kwargs.items())


def get_credentials():
    username, password = None, None
    rcfile = os.path.expanduser('~/.bztoolsrc')
    config = ConfigParser()
    config.add_section('bugzilla')

    if os.path.exists(rcfile):
        try:
            config.read(rcfile)
            username = config.get('bugzilla', 'username')
            _password = config.get('bugzilla', 'password')
            if _password:
                password = base64.b64decode(_password)
        except Exception:
            pass

    if not (username and password):
        username = raw_input('Bugzilla username: ')
        password = getpass.getpass('Bugzilla password: ')
        config.set('bugzilla', 'username', username)
        config.set('bugzilla', 'password', base64.b64encode(password))

        with open(rcfile, 'wb') as configfile:
            config.write(configfile)

    return username, password


FILE_TYPES = {
    'text': 'text/plain',
    'html': 'text/html',
    'xml': 'application/xml',
    'gif': 'image/gif',
    'jpg': 'image/jpeg',
    'png': 'image/png',
    'svg': 'image/svg+xml',
    'binary': 'application/octet-stream',
    'xul': 'application/vnd.mozilla.xul+xml',
}
