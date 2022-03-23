# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from jinja2 import Environment, FileSystemLoader
from libmozdata.bugzilla import BugzillaProduct

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.nag_me import Nag
from auto_nag.team_managers import TeamManagers
from auto_nag.user_activity import UserActivity


class TriageOwnerVacant(BzCleaner, Nag):
    def __init__(self):
        super(TriageOwnerVacant, self).__init__()
        self.query_url = None

    def description(self):
        return "Components with triage owner need to be assigned"

    def fetch_products(self):
        data = []
        include_fields = [
            "name",
            "is_active",
            "components.id",
            "components.name",
            "components.team_name",
            "components.triage_owner",
            "components.is_active",
        ]

        def product_handler(product, data):
            data.append(product)

        BugzillaProduct(
            product_names=self.get_products(),
            include_fields=include_fields,
            product_types=["accessible", "selectable", "enterable"],
            product_handler=product_handler,
            product_data=data,
        ).wait()

        return data

    def nag_template(self):
        return self.template()

    def identify_vacant_components(self):
        products = self.fetch_products()
        triage_owners = set()
        for product in products:
            if not product["is_active"]:
                continue
            for component in product["components"]:
                if not component["is_active"]:
                    continue
                triage_owners.add(component["triage_owner"])

        inactive_users = UserActivity().check_users(triage_owners)
        team_managers = TeamManagers()
        vacant_components = []

        for product in products:
            if not product["is_active"]:
                continue
            for component in product["components"]:
                if not component["is_active"]:
                    continue
                triage_owner = component["triage_owner"]
                if triage_owner not in inactive_users:
                    continue

                manager = team_managers.get_team_manager(component["team_name"])

                info = {
                    "id": component["id"],
                    "manager": manager["name"],
                    "team": component["team_name"],
                    "product": product["name"],
                    "component": component["name"],
                    "triage_owner": triage_owner,
                    "status": inactive_users[triage_owner],
                }

                vacant_components.append(info)
                self.add(manager["mozilla_email"], info)

        return vacant_components

    def get_email(self, date, bug_ids=[]):
        data = self.identify_vacant_components()
        if not data:
            return None, None

        extra = self.get_extra_for_template()
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template(self.template())
        message = template.render(
            date=date,
            data=data,
            extra=extra,
            str=str,
            enumerate=enumerate,
            plural=utils.plural,
            no_manager=self.no_manager,
            table_attrs=self.get_config("table_attrs"),
            preamble=self.preamble(),
        )
        common = env.get_template("common.html")
        body = common.render(
            message=message, query_url=utils.split_long_url(self.query_url)
        )

        return self.get_email_subject(date), body

    def prepare_mails(self):
        """Prepare nag emails"""

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
            for person in To:
                data += [
                    bug_data
                    for bug_data in info[person]
                    if bug_data["id"] not in added_bug_ids
                ]
                added_bug_ids.update(bug_data["id"] for bug_data in info[person])

            body = template.render(
                date=self.nag_date,
                extra=extra,
                plural=utils.plural,
                enumerate=enumerate,
                data=data,
                nag=True,
                table_attrs=self.get_config("table_attrs"),
                nag_preamble=self.nag_preamble(),
            )

            m = {"manager": manager, "to": set(To), "body": body}
            mails.append(m)

        return mails


if __name__ == "__main__":
    TriageOwnerVacant().run()
