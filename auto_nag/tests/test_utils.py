
# If relman-auto-nag is installed
from auto_nag.bugzilla.utils import os
from auto_nag.bugzilla.utils import (get_project_root_path,
                                     get_config_path,
                                     hide_personal_info)

class TestUtils:
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
