import base64
try:
    from configparser import ConfigParser
except ImportError:
    from ConfigParser import ConfigParser
import getpass
import os
import re
import posixpath
try:
    from urllib.parse import quote
except ImportError:
    from urllib import quote
import datetime
import requests
from auto_nag.common import get_current_versions


def get_project_root_path():
    """
    Get project root path
    return:string: Project ROOT folder
    """
    pwd = os.getcwd()
    root_dir = pwd.split('auto_nag')[0]
    if root_dir[-1] != '/':
        # if the current dir is the ROOT, add /
        root_dir += '/'
    return root_dir


def get_config_path():
    """
    Get config path location
    return:string: config file location
    """
    return get_project_root_path() + 'auto_nag/scripts/configs/config.json'


def urljoin(base, *args):
    """Remove any leading slashes so no subpaths look absolute."""
    return posixpath.join(base, *[str(s).lstrip('/') for s in args])


def hide_personal_info(error):
    """ Hides bugzilla user information from remoteobject error"""
    pattern = re.compile(
        r"https://bugzilla.mozilla.org*.+&api_key=(.*?)&")
    try:
        api_key = pattern.findall(error)[0]
        error_msg = error.replace(api_key, '*' * len(api_key))
    except IndexError:
        error_msg = error
    return error_msg


def qs(**kwargs):
    """Build a URL query string."""
    url = ''
    for k, v in kwargs.iteritems():
        if k == 'username' or k == 'password':
            pass
        for value in v:
            url += '&%s=%s' % (quote(k), value)
    return url


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
                username = config.get('bugzilla', 'username')
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


def createQuery(queries_dir, title, short_title, url):
    file_name = queries_dir + str(datetime.date.today()) + '_' + short_title
    if not os.path.exists(queries_dir):
        os.makedirs(queries_dir)
    qf = open(file_name, 'w')
    qf.write("query_name = \'" + title + "\'\n")
    qf.write("query_url = \'" + url + "\'\n")
    return file_name


def createQueriesList(queries_dir, weekday, urls, print_all):
    queries = []
    for url in urls:
        if weekday >= 0 and weekday < 5 and url[0] == 5:
            queries.append(createQuery(queries_dir, title=url[1][0], short_title=url[1][1], url=url[1][2]))
        if weekday == 0 and url[0] == 0:
            queries.append(createQuery(queries_dir, title=url[1][0], short_title=url[1][1], url=url[1][2]))
        if weekday == 3 and url[0] == 3:
            queries.append(createQuery(queries_dir, title=url[1][0], short_title=url[1][1], url=url[1][2]))
    print(queries)
    return queries


def cleanUp(queries_dir):
    try:
        for file in os.listdir(queries_dir):
            if file.startswith(str(datetime.date.today())):
                os.remove(os.path.join(queries_dir, file))
        return True
    except Exception as error:
        print("Error: ", str(error))
        return False


def __getTemplateValue(url):
    version_regex = re.compile(".*<p>(.*)</p>.*")
    template_page = str(requests.get(url).text.encode('utf-8')).replace('\n', '')
    parsed_template = version_regex.match(template_page)
    return parsed_template.groups()[0]


versions = get_current_versions()
release_version = versions['release']
beta_version = versions['beta']
central_version = versions['central']
esr_version = versions['esr']


def getVersions(channel=None):
    if channel and isinstance(channel, basestring):
        channel = channel.lower()
        if channel == 'release':
            return release_version
        elif channel == 'beta':
            return beta_version
        elif channel == 'central':
            return central_version
        elif channel == 'esr':
            return esr_version

    return (release_version, beta_version, central_version, esr_version)
