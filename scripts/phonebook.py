import requests
import os
import json

# NOTE: You must create a file for CONFIG_JSON with your LDAP auth in it like:
# {
#   "username": "username",
#   "password": "password"
# }
#
# In order to access the phonebook data


MY_DIR = os.path.abspath(os.path.dirname(__file__))
PEOPLE_FILENAME = os.path.join(MY_DIR, 'people.json')
CONFIG_JSON = os.path.join(os.path.dirname(__file__),"configs/config.json")
BASE_URL = 'https://ldap.mozilla.org/phonebook'
PEOPLE_URL = '%s/directory.php' % BASE_URL

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

    def __init__(self, config=CONFIG_JSON):
        config = json.load(open(config, 'r'))
        print "Fetching people from phonebook..." 
        self.people = json.loads(requests.get(PEOPLE_URL, auth=(config['username'], config['password'])).content)
        self.people_by_bzmail = self.get_people_by_bzmail()
        self.managers = self.get_managers()
        self.vices = self.get_vices()
    
    def get_managers(self):
        managers = {}
        for email, info in self.people.items():
            if self.people[email]['title'] != None:
                if 'director' in self.people[email]['title'].lower() or 'manager' in self.people[email]['title'].lower():
                    managers[email] = info
            # HACK! don't have titles with manager/director
            if email in ('rocallahan@mozilla.com', 'ladamski@mozilla.com', 'dtownsend@mozilla.com', 'dougt@mozilla.com', 'mfinkle@mozilla.com', 'bsmedberg@mozilla.com', 'blassey@mozilla.com', 'gsharp@mozilla.com' ) and email not in managers.keys():
                managers[email] = info
        return managers

    def get_vices(self):
        vices = {}
        for email, info in self.people.items():
            if self.people[email]['title'] != None:
                if 'vice' in self.people[email]['title'].lower():
                    vices[email] = info
        return vices
    
    def get_people_by_bzmail(self):
        temp = {}
        for email, info in self.people.items():
            # if someone doesn't have a bugzillaEmail set, we'll try their mozilla mail instead
            if info.get('bugzillaEmail'):
                temp[info['bugzillaEmail']] = dict(info.items())
                temp[info['bugzillaEmail']].update({'mozillaMail':email})
            else:
                temp[email] = dict(info.items())
                temp[email].update({'mozillaMail':email})
            
        return temp
