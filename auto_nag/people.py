# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json


class People:
    def __init__(self):
        with open('./auto_nag/scripts/configs/people.json', 'r') as In:
            self.data = json.load(In)
            self.people = {}
            self.people_by_bzmail = {}
            self.managers = set()
            self.people_with_bzmail = set()
            self.release_managers = set()
            self.rm_or_directors = set()
            self.directors = set()
            self._amend()

    def _get_people(self):
        if not self.people:
            for person in self.data:
                mail = person['mail']
                self.people[mail] = person
        return self.people

    def _get_people_by_bzmail(self):
        if not self.people_by_bzmail:
            for person in self.data:
                bzmail = person['bugzillaEmail']
                if not bzmail:
                    bzmail = person['mail']
                self.people_by_bzmail[bzmail] = person
        return self.people_by_bzmail

    def get_managers(self):
        """Get all the managers"""
        if not self.managers:
            for person in self.data:
                manager = person['manager']
                if manager:
                    self.managers.add(manager['dn'])
        return self.managers

    def get_people_with_bzmail(self):
        """Get all the people who have a bugzilla email"""
        if not self.people_with_bzmail:
            people = self._get_people()
            for person, info in people.items():
                mail = info['bugzillaEmail']
                if mail:
                    self.people_with_bzmail.add(mail)
        return self.people_with_bzmail

    def get_rm(self):
        """Get the release managers as defined in configs/rm.json"""
        if not self.release_managers:
            with open('./auto_nag/scripts/configs/rm.json', 'r') as In:
                self.release_managers = set(json.load(In))
        return self.release_managers

    def get_directors(self):
        """Get the directors: people who 'director' in their job title"""
        if not self.directors:
            people = self._get_people()
            for person, info in people.items():
                title = info.get('title', '').lower()
                if 'director' in title:
                    self.directors.add(person)
        return self.directors

    def get_rm_or_directors(self):
        """Get a set of release managers and directors who've a bugzilla email"""
        if not self.rm_or_directors:
            ms = self.get_directors() | self.get_rm()
            people = self._get_people()
            for m in ms:
                info = people[m]
                mail = info['bugzillaEmail']
                if mail:
                    self.rm_or_directors.add(mail)
        return self.rm_or_directors

    def _get_mail_from_dn(self, dn):
        dn = dn.split(',')
        assert len(dn) >= 2
        dn = dn[0].split('=')
        assert len(dn) == 2
        return dn[1]

    def _amend(self):
        for person in self.data:
            if 'manager' not in person:
                person['manager'] = {}
            if 'title' not in person:
                person['title'] = ''
            manager = person['manager']
            if manager:
                manager['dn'] = self._get_mail_from_dn(manager['dn'])
            if 'bugzillaEmail' in person:
                person['bugzillaEmail'] = person['bugzillaEmail'].lower()
            elif 'bugzillaemail' in person:
                person['bugzillaEmail'] = person['bugzillaemail'].lower()
                del person['bugzillaemail']
            else:
                person['bugzillaEmail'] = ''

    def is_mozilla(self, mail):
        """Check if the mail is the one from a mozilla employee"""
        return mail in self._get_people_by_bzmail() or mail in self._get_people()

    def is_manager(self, mail):
        """Check if the mail is the one from a mozilla manager"""
        if mail in self._get_people_by_bzmail():
            person = self._get_people_by_bzmail()[mail]
            return person['mail'] in self._get_managers()
        elif mail in self._get_people():
            return mail in self._get_managers()

        return False

    def get_manager_mail(self, mail):
        """Get the manager of the person with this mail"""
        person = self._get_people_by_bzmail().get(mail, None)
        if not person:
            person = self._get_people().get(mail, None)
        if not person:
            return None

        manager = person['manager']
        if manager:
            return manager['dn']

        return None

    def get_moz_mail(self, mail):
        """Get the manager of the person with this mail"""
        person = self._get_people_by_bzmail().get(mail, None)
        if person:
            return person['mail']
        return mail

    def get_moz_name(self, mail):
        """Get the manager of the person with this mail"""
        person = self._get_people_by_bzmail().get(mail, None)
        return person['cn']

    def get_info(self, mail):
        """Get info on person with this mail"""
        person = self._get_people_by_bzmail().get(mail, None)
        if not person:
            person = self._get_people().get(mail, None)
        return person

    def is_under(self, mail, manager):
        """Check if someone is under manager in the hierarchy"""
        m = mail
        while True:
            m = self.get_manager_mail(m)
            if m is None:
                return False
            if m == manager:
                return True
