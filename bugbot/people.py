# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import re
from math import sqrt
from typing import Set

import numpy as np

WORDS = re.compile(r"(\w+)")
MAIL = re.compile(r"^([^@]+@[^ ]+)")
IMs = [
    "irc",
    "slack",
    "skype",
    "xmpp",
    "github",
    "aim",
    "telegram",
    "irc.mozilla.org",
    "google talk",
    "gtalk",
    "blog",
    "twitter",
]
IM_NICK = re.compile(r"([\w\.@]+)")


class People:

    _instance = None

    def __init__(self, p=None):
        if p is None:
            with open("./bugbot/scripts/configs/people.json", "r") as In:
                self.data = json.load(In)
        else:
            self.data = p

        self.people = self._get_people()
        self.people_by_bzmail = {}
        self.managers = set()
        self.people_with_bzmail = set()
        self.release_managers = set()
        self.rm_or_directors = set()
        self.nicks = {}
        self.directors = set()
        self.vps = set()
        self.names = {}
        self._amend()
        self.matrix = None

    @staticmethod
    def get_instance():
        if People._instance is None:
            People._instance = People()
        return People._instance

    def _get_name_parts(self, name):
        """Get names from name"""
        return set(s.lower() for s in WORDS.findall(name))

    def _get_people(self):
        people = {}
        for person in self.data:
            mail = self.get_preferred_mail(person)
            person["mail"] = mail
            people[mail] = person
        return people

    def _get_names(self):
        if not self.names:
            for person in self.data:
                cn = person["cn"]
                parts = self._get_name_parts(cn)
                parts = tuple(sorted(parts))
                self.names[parts] = person
        return self.names

    def _get_bigrams(self, text):
        text = "".join(s.lower() for s in WORDS.findall(text))
        return [text[i : (i + 2)] for i in range(len(text) - 1)]

    def _get_bigrams_stats(self, text):
        stats = {}
        for bi in self._get_bigrams(text):
            stats[bi] = stats.get(bi, 0) + 1

        return stats

    def _get_matrix_names(self):
        if self.matrix is None:
            res = {}
            bigrams = set()
            cns = {}
            for person in self.data:
                cn = person["cn"]
                cns[cn] = person
                res[cn] = stats = self._get_bigrams_stats(cn)
                L = sqrt(sum(v * v for v in stats.values()))
                for k, v in stats.items():
                    stats[k] = float(v) / L
                    bigrams.add(k)

            bigrams = sorted(bigrams)
            self.bigrams = {x: i for i, x in enumerate(bigrams)}
            self.matrix = np.zeros((len(res), len(self.bigrams)))
            self.matrix_map = [None] * len(res.items())
            for i, (name, stats) in enumerate(res.items()):
                for b, n in stats.items():
                    self.matrix[i][self.bigrams[b]] = n
                self.matrix_map[i] = cns[name]

    def search_by_name(self, name):
        # Try to find name in using cosine similarity
        self._get_matrix_names()
        stats = self._get_bigrams_stats(name)
        for k in set(stats.keys()) - set(self.bigrams.keys()):
            del stats[k]
        L = sqrt(sum(v * v for v in stats.values()))
        x = np.zeros((len(self.bigrams), 1))
        for k, v in stats.items():
            x[self.bigrams[k]][0] = float(v) / L
        res = np.matmul(self.matrix, x)
        for cos in [0.99, 0.9, 0.8, 0.7]:
            index = np.argwhere(res > cos)
            if index.shape[0] == 1:
                return self.matrix_map[index[0][0]]

        found = None
        name_parts = self._get_name_parts(name)
        for parts, info in self._get_names().items():
            if name_parts <= set(parts):
                if found is None:
                    found = info
                else:
                    found = None
                    break
        return found

    def _get_people_by_bzmail(self):
        if not self.people_by_bzmail:
            for person in self.data:
                bzmail = person["bugzillaEmail"]
                if not bzmail:
                    bzmail = person["mail"]
                self.people_by_bzmail[bzmail] = person
        return self.people_by_bzmail

    def get_managers(self):
        """Get all the managers"""
        if not self.managers:
            for person in self.data:
                manager = person["manager"]
                if manager:
                    self.managers.add(manager["dn"])
        return self.managers

    def get_people_with_bzmail(self):
        """Get all the people who have a bugzilla email"""
        if not self.people_with_bzmail:
            for person, info in self.people.items():
                mail = info["bugzillaEmail"]
                if mail:
                    self.people_with_bzmail.add(mail)
        return self.people_with_bzmail

    def get_info_by_nick(self, nick):
        """Get info for a nickname"""
        if not self.nicks:
            doubloons = set()
            for person, info in self.people.items():
                bz_mail = info["bugzillaEmail"]
                if not bz_mail:
                    continue
                nicks = self.get_nicks_from_im(info)
                nicks |= {person, bz_mail, info["mail"], info.get("githubprofile")}
                nicks |= set(self.get_aliases(info))
                nicks = {self.get_mail_prefix(n) for n in nicks if n}
                for n in nicks:
                    if n not in self.nicks:
                        self.nicks[n] = info
                    else:
                        doubloons.add(n)
            # doubloons are not identifiable so remove them
            for n in doubloons:
                del self.nicks[n]
        return self.nicks.get(nick)

    def get_rm(self):
        """Get the release managers as defined in configs/rm.json"""
        if not self.release_managers:
            with open("./bugbot/scripts/configs/rm.json", "r") as In:
                self.release_managers = set(json.load(In))
        return self.release_managers

    def get_directors(self):
        """Get the directors: people who 'director' in their job title"""
        if not self.directors:
            for person, info in self.people.items():
                title = info.get("title", "").lower()
                if "director" in title:
                    self.directors.add(person)
        return self.directors

    def get_vps(self):
        """Get the vp: people who've 'vp' in their job title"""
        if not self.vps:
            for person, info in self.people.items():
                title = info.get("title", "").lower()
                if (
                    title.startswith("vp") or title.startswith("vice president")
                ) and self.get_distance(person) <= 3:
                    self.vps.add(person)
        return self.vps

    def get_distance(self, mail):
        rank = -1
        while mail:
            rank += 1
            prev = mail
            mail = self.get_manager_mail(mail)
            if mail == prev:
                break
        return rank

    def get_rm_or_directors(self):
        """Get a set of release managers and directors who've a bugzilla email"""
        if not self.rm_or_directors:
            ms = self.get_directors() | self.get_rm()
            for m in ms:
                info = self.people[m]
                mail = info["bugzillaEmail"]
                if mail:
                    self.rm_or_directors.add(mail)
        return self.rm_or_directors

    def _get_mail_from_dn(self, dn):
        dn = dn.split(",")
        assert len(dn) >= 2
        dn = dn[0].split("=")
        assert len(dn) == 2
        return dn[1]

    def _amend(self):
        for person in self.data:
            if "manager" not in person:
                person["manager"] = {}
            if "title" not in person:
                person["title"] = ""
            manager = person["manager"]
            if manager:
                manager["dn"] = self._get_mail_from_dn(manager["dn"])
            if "bugzillaEmail" in person:
                person["bugzillaEmail"] = person["bugzillaEmail"].lower()
            elif "bugzillaemail" in person:
                person["bugzillaEmail"] = person["bugzillaemail"].lower()
                del person["bugzillaemail"]
            else:
                person["bugzillaEmail"] = ""

    def is_mozilla(self, mail):
        """Check if the mail is the one from a mozilla employee"""
        return mail in self._get_people_by_bzmail() or mail in self.people

    def is_manager(self, mail):
        """Check if the mail is the one from a mozilla manager"""
        if mail in self._get_people_by_bzmail():
            person = self._get_people_by_bzmail()[mail]
            return person["mail"] in self._get_managers()
        elif mail in self.people:
            return mail in self._get_managers()

        return False

    def get_manager_mail(self, mail):
        """Get the manager of the person with this mail"""
        person = self._get_people_by_bzmail().get(mail, None)
        if not person:
            person = self.people.get(mail, None)
        if not person:
            return None

        manager = person["manager"]
        if not manager:
            return None

        manager_mail = manager["dn"]
        if manager_mail == mail:
            return None

        return manager_mail

    def get_nth_manager_mail(self, mail, rank):
        """Get the nth manager of the person with this mail"""
        for _ in range(rank):
            prev = mail
            mail = self.get_manager_mail(mail)
            if not mail or mail == prev:
                return prev
        return mail

    def get_management_chain_mails(
        self, person: str, superior: str, raise_on_missing: bool = True
    ) -> Set[str]:
        """Get the mails of people in the management chain between a person and
        their superior.

        Args:
            person: the moz email of an employee.
            superior: the moz email of one of the employee's superiors.
            raise_on_missing: If True, an exception will be raised when the
                superior is not in the management hierarchy of the employee. If
                False, an empty set will be returned instead of raising an
                exception.

        Returns:
            A set of moz emails for people in the management chain between
            `person` and `superior`. Emails for `person` and `superior` will not
            be returned with the result.
        """
        result: Set[str] = set()

        assert person in self.people
        assert superior in self.people
        if person == superior:
            return result

        manager = self.get_manager_mail(person)
        while manager != superior:
            result.add(manager)
            manager = self.get_manager_mail(manager)

            if not manager:
                if not raise_on_missing:
                    return set()
                raise Exception(f"Cannot identify {superior} as a superior of {person}")

            if manager in result:
                raise Exception("Circular management chain")

        return result

    def get_director_mail(self, mail):
        """Get the director of the person with this mail"""
        directors = self.get_directors()
        while True:
            prev = mail
            mail = self.get_manager_mail(mail)
            if not mail:
                break
            if mail in directors:
                return mail
            if mail == prev:
                break
        return None

    def get_vp_mail(self, mail):
        """Get the VP of the person with this mail"""
        vps = self.get_vps()
        while True:
            prev = mail
            mail = self.get_manager_mail(mail)
            if not mail:
                break
            if mail in vps:
                return mail
            if mail == prev:
                break
        return None

    def get_mail_prefix(self, mail):
        return mail.split("@", 1)[0].lower()

    def get_im(self, person):
        im = person.get("im", "")
        if not im:
            return []
        if isinstance(im, str):
            return [im]
        return im

    def get_nicks_from_im(self, person):
        im = self.get_im(person)
        nicks = set()
        for info in im:
            info = info.lower()
            for i in IMs:
                info = info.replace(i, "")
            for nick in IM_NICK.findall(info):
                if nick.startswith("@"):
                    nick = nick[1:]
                nicks.add(nick)
        return nicks

    def get_aliases(self, person):
        aliases = person.get("emailalias", "")
        if not aliases:
            return []
        if isinstance(aliases, str):
            return [aliases]
        return aliases

    def get_preferred_mail(self, person):
        aliases = self.get_aliases(person)
        for alias in aliases:
            alias = alias.strip()
            if "preferred" in alias:
                m = MAIL.search(alias)
                if m:
                    return m.group(1)
        return person["mail"]

    def get_moz_mail(self, mail):
        """Get the Mozilla email of the person with this Bugzilla email"""
        person = self._get_people_by_bzmail().get(mail, None)
        if person:
            return person["mail"]
        return mail

    def get_moz_name(self, mail):
        """Get the name of the person with this Bugzilla email"""
        person = self._get_people_by_bzmail().get(mail, None)
        if person is None:
            return None
        return person["cn"]

    def get_info(self, mail):
        """Get info on person with this mail"""
        person = self._get_people_by_bzmail().get(mail, None)
        if not person:
            person = self.people.get(mail, None)
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

    def get_bzmail_from_name(self, name):
        """Search bz mail for a given name"""

        if "@" in name:
            info = self.get_info(name)
        else:
            info = self.get_info_by_nick(name)
            if not info:
                info = self.search_by_name(name)

        if info:
            mail = info["bugzillaEmail"]
            return mail if mail else info["mail"]

        return None

    def get_mozmail_from_name(self, name):
        """Search moz mail for a given name"""

        if "@" in name:
            info = self.get_info(name)
        else:
            info = self.get_info_by_nick(name)
            if not info:
                info = self.search_by_name(name)

        if info:
            return info["mail"]

        return None
