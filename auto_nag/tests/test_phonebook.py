
from auto_nag.scripts.phonebook import PhonebookDirectory


class TestPhonebook:
    def __init__(self):
        self.demo_dict = {u'email@example.com': {u'name': u'Sylvestre Ledru', u'title': u'Release mgmt lead / manager', u'mail': u'email@example.com', u'manager': {u'cn': u'Lawrence Mandel', u'dn': u'mail=foo2@mozilla.com,o=com'}, 'mozillaMail': u'email@example.com', u'bugzillaEmail': u'email@example.com'}, u'foo1@mozilla.com': {u'name': u'Calixte Denizet', u'title': u'Release engineer', u'mail': u'foo1@mozilla.com', u'manager': {u'cn': u'Sylvestre Ledru', u'dn': u'mail=email@example.com,o=com'}, 'mozillaMail': u'foo1@mozilla.com', u'bugzillaEmail': u'foo1@mozilla.com'}}


    def test_init(self):
        pd = PhonebookDirectory(dryrun=True, isTest=True)
        assert not len(set(self.demo_dict) ^ set(pd.people_by_bzmail))
#        assert not len(set(pd.managers['email@example.com']) ^ set(self.demo_dict['email@example.com']))
