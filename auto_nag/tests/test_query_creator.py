
try:
    # If relman-auto-nag is installed
    from auto_nag.bugzilla.utils import os
    from auto_nag.scripts.query_creator import (getTemplateValue, getReportURL,
                                                createQueriesList)
    import shutil
except:
    # If relman-auto-nag not installed, add project root directory into
    # PYTHONPATH
    import os
    import sys
    import inspect
    import shutil
    currentdir = os.path.dirname(os.path.abspath(
                                 inspect.getfile(inspect.currentframe())))
    parentdir = os.path.dirname(currentdir)
    sys.path.insert(0, parentdir)
    from auto_nag.scripts.query_creator import (getTemplateValue, getReportURL,
                                                createQueriesList)

class TestQueryCreator:
    def test_getTemplateValue(self):
        """
        Expecting a VERSION number
        """
        url = "https://wiki.mozilla.org/Template:BETA_VERSION"
        beta_version = getTemplateValue(url)
        assert type(int(beta_version)) is not type(int)

    def test_getReportURL(self):
        """
        Expecting proper URL with Bug numbers
        """
        url = 'https://wiki.mozilla.org/Template:CURRENT_CYCLE'
        cycle_span = getTemplateValue(url)
        unlanded_beta_url = getReportURL("approval-mozilla-beta",
                                         cycle_span)
        unlanded_aurora_url = getReportURL("approval-mozilla-aurora",
                                           cycle_span)
        unlanded_esr38_url = getReportURL("approval-mozilla-esr38",
                                          cycle_span)

        unlanded_beta_url = unlanded_beta_url.split('=')
        assert ',' in unlanded_beta_url[1]
        unlanded_aurora_url = unlanded_aurora_url.split('=')
        assert ',' in unlanded_aurora_url[1]
        unlanded_esr38_url = unlanded_esr38_url.split('=')
        assert ',' in unlanded_esr38_url[1]

    def test_createQueriesList(self):
        """
        Expecting list of queries
        """
        queries_dir = os.path.dirname(os.path.realpath(__file__)) + '/queries/'
        queries = createQueriesList(queries_dir, True)
        assert queries

    def tearDown(self):
        """
        Delete unnecessory folders
        """
        # createQueriesList creating this folder
        queries_dir = os.path.dirname(os.path.realpath(__file__)) + '/queries/'
        if os.path.isdir(queries_dir):
            shutil.rmtree(queries_dir)
