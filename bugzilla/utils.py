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


def get_credentials(username=None):

    # Try to get it from the environment first
    if not username:
        username = os.environ.get('BZ_USERNAME', None)
    password = os.environ.get('BZ_PASSWORD', None)

    # Try to get it from the system keychain next 
    if not username and not password:
        try:
            import keyring
            if not username:
                # Grab the default username as we weren't passed in a specific one
                username = keyring.get_password("bugzilla", 'default_username')
            if username:
                # Get the password for the username
                password = keyring.get_password("bugzilla", username)
        except ImportError:
            # If they don't have the keyring lib, fall back to next method
            pass

    # Then try a config file in their home directory
    if not (username and password):
        rcfile = os.path.expanduser('~/.bztoolsrc')
        config = ConfigParser()
        config.add_section('bugzilla')
        if os.path.exists(rcfile):
            try:
                config.read(rcfile)
                username  = config.get('bugzilla', 'username')
                _password = config.get('bugzilla', 'password')
                if _password:
                    password = base64.b64decode(_password)
            except Exception:
                pass

    # Finally, prompt the user for the info if we didn't get it above
    if not (username and password):
        username = raw_input('Bugzilla username: ')
        password = getpass.getpass('Bugzilla password: ')
        try:
            # Save the data to the keyring if possible
            import keyring
            keyring.set_password("bugzilla", 'default_username', username)
            keyring.set_password("bugzilla", username, password)
        except ImportError:
            # Otherwise save it to a config file
            config.set('bugzilla', 'username', username)
            config.set('bugzilla', 'password', base64.b64encode(password))
            with open(rcfile, 'wb') as configfile:
                config.write(configfile)

    return username, password


FILE_TYPES = {
    'text':  'text/plain',
    'html':  'text/html',
    'xml':   'application/xml',
    'gif':   'image/gif',
    'jpg':   'image/jpeg',
    'png':   'image/png',
    'svg':   'image/svg+xml',
    'binary': 'application/octet-stream',
    'xul':    'application/vnd.mozilla.xul+xml',
}
