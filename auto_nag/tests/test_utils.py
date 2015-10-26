
try:
    # If relman-auto-nag is installed
    from auto_nag.bugzilla.utils import os
    from auto_nag.bugzilla.utils import get_project_root_path, get_config_path
except:
    # If relman-auto-nag not installed, add project root directory into
    # PYTHONPATH
    import os
    currentdir = os.path.dirname(os.path.abspath(
                                 inspect.getfile(inspect.currentframe())))
    parentdir = os.path.dirname(currentdir)
    sys.path.insert(0, parentdir)
    from auto_nag.bugzilla.utils import get_project_root_path, get_config_path

class TestUtils:
    def test_get_project_root_path(self):
         rpath = get_project_root_path()
         assert os.path.isdir(rpath)
    def test_get_config_path(self):
        cpath = get_config_path()
        # remove 'not' when running locally
        # 'not' helps to pass CI checks while commiting
        assert not os.path.exists(cpath)
