# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy

from jinja2 import Environment, FileSystemLoader

from auto_nag import db, logger, mail, utils
from auto_nag.escalation import Escalation
from auto_nag.people import People


class Nag(object):
    def __init__(self):
        super(Nag, self).__init__()
        self.people = People.get_instance()
        self.send_nag_mail = True
        self.data = {}
        self.nag_date = None
        self.white_list = []
        self.black_list = []
        self.escalation = Escalation(self.people)
        self.triage_owners_components = {}
        self.all_owners = None
        self.query_params = {}
        self.round_robin = None

    @staticmethod
    def get_from():
        return utils.get_config("auto_nag", "from", "release-mgmt@mozilla.com")

    def get_cc(self):
        cc = self.get_config("cc", None)
        if cc is None:
            cc = utils.get_config("auto_nag", "cc", [])

        return set(cc)

    def get_priority(self, bug):
        tracking = bug[self.tracking]
        if tracking == "blocking":
            return "high"
        return "normal"

    def filter_bug(self, priority):
        days = (utils.get_next_release_date() - self.nag_date).days
        weekday = self.nag_date.weekday()
        return self.escalation.filter(priority, days, weekday)

    def get_people(self):
        return self.people

    def set_people_to_nag(self, bug, buginfo):
        return bug

    def escalate(self, person, priority, **kwargs):
        days = (utils.get_next_release_date() - self.nag_date).days
        return self.escalation.get_supervisor(priority, days, person, **kwargs)

    def add(self, persons, bug_data, priority="default", **kwargs):
        if not isinstance(persons, list):
            persons = [persons]

        persons = [p for p in persons if self.people.is_mozilla(p)]
        if not persons:
            return False

        managers = {p: self.escalate(p, priority, **kwargs) for p in persons}
        return self.add_couples(managers, bug_data)

    def add_couples(self, managers, bug_data):
        for person, manager in managers.items():
            person = self.people.get_moz_mail(person)

            if manager in self.data:
                data = self.data[manager]
            else:
                self.data[manager] = data = {}

            if person in data:
                data[person].append(bug_data)
            else:
                data[person] = [bug_data]

        return True

    def nag_template(self):
        return self.name() + "_nag.html"

    def nag_preamble(self):
        return None

    def get_extra_for_nag_template(self):
        return {}

    def columns_nag(self):
        return None

    def sort_columns_nag(self):
        return None

    def _is_in_list(self, mail, _list):
        for manager in _list:
            if self.people.is_under(mail, manager):
                return True
        return False

    def is_under(self, mail):
        if not self.white_list:
            if not self.black_list:
                return True
            return not self._is_in_list(mail, self.black_list)
        if not self.black_list:
            return self._is_in_list(mail, self.white_list)
        return self._is_in_list(mail, self.white_list) and not self._is_in_list(
            mail, self.black_list
        )

    def add_triage_owner(self, owners, real_owner):
        if self.round_robin is None:
            return

        if not isinstance(owners, list):
            owners = [owners]
        for owner in owners:
            person = self.people.get_moz_mail(owner)
            if person not in self.triage_owners_components:
                self.triage_owners_components[person] = set(
                    self.round_robin.get_components_for_triager(owner)
                )
            else:
                self.triage_owners_components[
                    person
                ] |= self.round_robin.get_components_for_triager(owner)

    def get_query_url_for_components(self, components):
        params = copy.deepcopy(self.query_params)
        for f in ["include_fields", "product", "component", "bug_id"]:
            if f in params:
                del params[f]

        utils.add_prod_comp_to_query(params, components)
        url = utils.get_bz_search_url(params)

        return url

    def organize_nag(self, bugs):
        columns = self.columns_nag()
        if columns is None:
            columns = self.columns()
        key = self.sort_columns_nag()
        if key is None:
            key = self.sort_columns()

        return utils.organize(bugs, columns, key=key)

    def send_mails(self, title, dryrun=False):
        if not self.send_nag_mail:
            return

        env = Environment(loader=FileSystemLoader("templates"))
        common = env.get_template("common.html")
        login_info = utils.get_login_info()
        From = Nag.get_from()
        Default_Cc = self.get_cc()
        mails = self.prepare_mails()

        for m in mails:
            Cc = Default_Cc.copy()
            if m["manager"]:
                Cc.add(m["manager"])
            body = common.render(message=m["body"], query_url=None)
            receivers = set(m["to"]) | set(Cc)
            status = "Success"
            try:
                mail.send(
                    From,
                    sorted(m["to"]),
                    title,
                    body,
                    Cc=sorted(Cc),
                    html=True,
                    login=login_info,
                    dryrun=dryrun,
                )
            except Exception:
                logger.exception("Tool {}".format(self.name()))
                status = "Failure"

            db.Email.add(self.name(), receivers, "individual", status)

    def prepare_mails(self):
        if not self.data:
            return []

        template = self.nag_template()
        if not template:
            return []

        extra = self.get_extra_for_nag_template()
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template(template)
        mails = []
        for manager, info in self.data.items():
            # The same bug can be several times in the list
            # because we send an email to a team.
            added_bug_ids = set()

            data = []
            To = sorted(info.keys())
            components = set()
            for person in To:
                data += [
                    bug_data
                    for bug_data in info[person]
                    if bug_data["id"] not in added_bug_ids
                ]
                added_bug_ids.update(bug_data["id"] for bug_data in info[person])
                if person in self.triage_owners_components:
                    components |= self.triage_owners_components[person]

            if components:
                query_url = self.get_query_url_for_components(sorted(components))
            else:
                query_url = None

            body = template.render(
                date=self.nag_date,
                extra=extra,
                plural=utils.plural,
                enumerate=enumerate,
                data=self.organize_nag(data),
                nag=True,
                query_url_nag=query_url,
                table_attrs=self.get_config("table_attrs"),
                nag_preamble=self.nag_preamble(),
            )

            m = {"manager": manager, "to": set(To), "body": body}
            mails.append(m)

        return mails

    def reorganize_to_bag(self, data):
        return data
