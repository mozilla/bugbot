
import os
import datetime
from auto_nag.scripts.b2g_query_creator import (createQueriesList, createQuery,
                                                cleanUp)
from auto_nag.scripts.query_creator import createQueriesList as CQ
from auto_nag.bugzilla.utils import get_project_root_path
from auto_nag.bugzilla import settings


class TestB2GQueryCreator:
    def __init__(self):
        self.queries_dir = get_project_root_path() + "queries/"
        self.url = (settings.API_ROOT +
                    '/buglist.cgi?o5=nowordssubstr'
                    '&f1=OP&f0=OP&f8=owner_idle_time&o2=equals&f4=OP&'
                    'v5=fixed%20verified%20unaffected%20wontfix&'
                    'j1=OR&f3=CP&f2=cf_blocking_b2g&bug_status=UNCONFIRMED&'
                    'bug_status=NEW&bug_status=ASSIGNED&bug_status=REOPENED&'
                    'j4=OR&f5=cf_status_b2g_1_2&v8=-3d&f6=CP&'
                    'v2=koi%2B&f7=CP&o8=greaterthan')

    def test_createQueriesList(self):
        queries = createQueriesList(True, self.queries_dir)
        assert queries

    def test_createQuery(self):
        query = createQuery('Koi Blocker Bugs, Regressions',
                             'koi_regressions_unfixed', self.url,
                             '1', None, self.queries_dir)
        assert 'koi_regressions_unfixed' in query

    def test_querycleanUp(self):
        assert cleanUp(self.queries_dir)
