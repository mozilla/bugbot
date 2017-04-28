import json

from auto_nag.bugzilla.utils import get_project_root_path

# NOTE: You must create a file for CONFIG_JSON with your LDAP auth in it like:
# {
#   "username": "username",
#   "password": "password"
# }
#
# In order to access the phonebook data

BASE_URL = 'https://phonebook.mozilla.org'
PEOPLE_URL = '%s/search.php?query=*&format=fligtar' % BASE_URL

'''
a single phonebook entry data looks like this when you pull it from JSON:
'email' = {
            ims : [],
            name : 'name',
            title : 'title',
            phones : 'string of numbers & assignments',
            ext : XXX,
            manager : {u'dn': u'mail=manager@mozilla.com,o=com,dc=mozilla', u'cn': u'Manager Name'},
            bugzillaEmail : 'email@example.com'

            ## this script adds in:
            mozillaMail : 'email@mozilla.com'
        }
'''


class PhonebookDirectory():
    def __init__(self, dryrun=False, isTest=False):
        print "Fetching people from phonebook..."
        if False and dryrun:
            people_json = (get_project_root_path() +
                           '/auto_nag/tests/people.json')
            with open(people_json, 'r') as pj:
                self.people = json.load(pj)
        else:
            # when phonebook bug will be fixed: remove these lines and uncomment the following
            people_json = (get_project_root_path() +
                           '/auto_nag/scripts/configs/people.json')
            if isTest:
                people_json = (get_project_root_path() +
                               '/auto_nag/tests/people.json')
            with open(people_json, 'r') as pj:
                self.people = {}
                entries = json.load(pj)
                for entry in entries:
                    self.people[entry['mail']] = entry
                    if 'title' not in entry:
                        entry['title'] = ''
            # config = get_config_path()
            # config = json.load(open(config, 'r'))
            # self.people = json.loads(requests.get(PEOPLE_URL,
            #                                      auth=(config['ldap_username'],
            #                                            config['ldap_password'])).content)
        self.people_by_bzmail = self.get_people_by_bzmail()
        self.managers = self.get_managers()
        self.vices = self.get_vices()

    def get_managers(self):
        managers = {}
        for email, info in self.people.items():
            if self.people[email]['title'] is not None:
                if 'director' in self.people[email]['title'].lower() or 'manager' in self.people[email]['title'].lower():
                    managers[email] = info
            # HACK! don't have titles with manager/director or missing bugmail address
            if email in ('dtownsend@mozilla.com', 'dougt@mozilla.com',
                         'mfinkle@mozilla.com', 'bsmedberg@mozilla.com',
                         'blassey@mozilla.com') and email not in managers.keys():
                managers[email] = info
        return managers

    def get_vices(self):
        vices = {}
        for email, info in self.people.items():
            if self.people[email]['title'] is not None:
                if 'vice' in self.people[email]['title'].lower():
                    vices[email] = info
        return vices

    def get_people_by_bzmail(self):
        temp = {}
        for email, info in self.people.items():
            # if someone doesn't have a bugzillaEmail set, we'll try their mozilla mail instead
            if info.get('bugzillaEmail'):
                temp[info['bugzillaEmail']] = dict(info.items())
                temp[info['bugzillaEmail']].update({'mozillaMail': email})
            else:
                temp[email] = dict(info.items())
                temp[email].update({'mozillaMail': email})

        return temp
