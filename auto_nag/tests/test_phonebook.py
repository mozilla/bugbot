
from auto_nag.scripts.phonebook import PhonebookDirectory


class TestPhonebook:
    def __init__(self):
        self.demo_dict = {u'email@example.com': {
                          u'bugzillaEmail': u'email@example.com',
                          u'name': u'name',
                          u'title': u'vice/director test',
                          u'phones': u'string of numbers & assignments',
                          u'ext': u'XXX',
                          u'manager': {
                                    u'dn': u'mail=manager@mozilla.com,o=com,dc=mozilla',
                                    u'cn': u'Manager Name'
                          },
                          u'ims': [],
                          u'mozillaMail': u'email'}}

    def test_init(self):
        pd = PhonebookDirectory(dryrun=True)
        assert not len(set(self.demo_dict) ^ set(pd.people_by_bzmail))
        assert not len(set(pd.managers['email']) ^
                       set(self.demo_dict['email@example.com']))
        assert not len(set(pd.vices['email']) ^
                       set(self.demo_dict['email@example.com']))
