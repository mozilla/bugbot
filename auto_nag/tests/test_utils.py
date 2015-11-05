
from auto_nag.bugzilla.utils import os
from auto_nag.bugzilla.utils import (get_project_root_path,
                                     get_config_path,
                                     hide_personal_info,
                                     urljoin,
                                     get_credentials,
                                     qs)

from auto_nag.bugzilla.settings import BZ_API_ROOT
import pexpect
import shutil
from nose.tools import assert_equals


class TestUtils:
    # Test bugzilla util methods

    def test_get_project_root_path(self):
        rpath = get_project_root_path()
        assert os.path.isdir(rpath)

    def test_get_config_path(self):
        cpath = get_config_path()
        # remove 'not' when running locally
        # 'not' helps to pass CI checks while commiting
        assert not os.path.exists(cpath)

    def test_hide_personal_info(self):
        sample_exception = "Exception: 400 Bad Request requesting " + \
            "BugSearch https://bugzilla.mozilla.org/bzapi/bug/?&" + \
            "changed_before=2010-12-26&product=Core,Firefox&" + \
            "changed_field=status&changed_after=2010-12-24&" + \
            "include_fields=_default,attachments&changed_field_to=" + \
            "RESOLVED&api_key=xyzxyzxyz&resolution=FIXED"
        assert "xyzxyzxyz" not in hide_personal_info(sample_exception)

    def test_urljoin(self):
        url = urljoin(
            BZ_API_ROOT, 'bug/%s/attachment?%s' %
            (1233, '&changed_before=' +
                '2010-12-26&product=Core,Firefox&changed_field=status&' +
                'changed_after=2010-12-24&include_fields=_default,' +
                'attachments&changed_field_to=RESOLVED&resolution=FIXED'))

        expected_url = BZ_API_ROOT + 'bug/1233/' + \
            'attachment?&changed_before=2010-12-26&product=Core,Firefox&' + \
            'changed_field=status&changed_after=2010-12-24&include_fields=' + \
            '_default,attachments&changed_field_to=RESOLVED&resolution=FIXED'
        assert_equals(url, expected_url)

    def test_qs(self):
        param = {'product': ['Core,Firefox']}
        _qs = qs(**param)
        expected_qs = '&product=Core,Firefox'
        assert_equals(_qs, expected_qs)

    def test_get_credentials(self):
        # if already bztoolsrc is present, backup the existing '~/.bztoolsrc'
        rcfile = os.path.expanduser('~/.bztoolsrc')
        rcfile_backup = os.path.expanduser('~/.bztoolsrc_backup')
        if os.path.exists(rcfile):
            shutil.move(rcfile, rcfile_backup)
        cmd = 'python ' + get_project_root_path() + \
            'auto_nag/tests/_get_credential.py'
        child = pexpect.spawn(cmd, timeout=180)
        child.expect('username')
        child.sendline('test_username')
        child.expect('password')
        child.sendline('test_password')
        child.expect(pexpect.EOF)
        child.close()

        credentials = get_credentials()

        # Removing the ~/.bztoolsrc which generated for testing.
        os.remove(rcfile)

        # copy back bztoolsrc_backup to ~/.bztoolsrc
        if os.path.exists(rcfile_backup):
            shutil.move(rcfile_backup, rcfile)
        assert_equals(credentials, ('test_username', 'test_password'))
