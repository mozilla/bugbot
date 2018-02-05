from auto_nag.common import getCurrentVersion
from auto_nag.bugzilla.utils import get_project_root_path
from auto_nag.scripts.query_creator import (getTemplateValue, getReportURL,
                                            createQueriesList, cleanUp, urls,
                                            esr_version)
import shutil
import datetime

class TestQueryCreator:
    def setUp(self):
        self.queries_dir = get_project_root_path() + 'queries/'

    def test_1_getTemplateValue(self):
        """
        Tests for getTemplateValue,
        Expecting a VERSION number
        """
        versions = getCurrentVersion()
        beta_version = versions["beta"]
        assert type(int(beta_version)) is not type(int)

    def test_2_getReportURL(self):
        """
        Tests for getReportURL
        Expecting proper URL with Bug numbers
        """
        url = 'https://wiki.mozilla.org/Template:CURRENT_CYCLE'
        cycle_span = getTemplateValue(url)
        unlanded_beta_url = getReportURL("approval-mozilla-beta",
                                         cycle_span)
        unlanded_esr_url = getReportURL("approval-mozilla-esr" + esr_version,
                                          cycle_span)

        url = unlanded_beta_url.split('=')
        assert isinstance(int(url[1].split(',')[0]), (int))
        url = unlanded_esr_url.split('=')
        assert isinstance(int(url[1].split(',')[0]), (int))

    def test_3_createQueriesList(self):
        """
        Tests for createQueriesList, weekday < 5 and > 0
        Expecting list of queries
        """
        queries = createQueriesList(self.queries_dir, 4, urls, True)
        assert queries

    def test_4_createQueriesList(self):
        """
        Tests for createQueriesList, weekday=3
        Expecting list of queries
        """
        queries = createQueriesList(self.queries_dir, 3, urls, True)
        assert queries

    def test_5_createQueriesList(self):
        """
        Tests for createQueriesList, weekday=0
        Expecting list of queries
        """
        queries = createQueriesList(self.queries_dir, 0, urls, True)
        assert queries

    def test_6_cleanUp(self):
        """
        Tests for cleanUp
        Delete unnecessory folders
        """
        assert cleanUp(self.queries_dir)
