# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from typing import List

from libmozdata.bugzilla import Bugzilla, BugzillaProduct

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.nag_me import Nag
from auto_nag.team_managers import TeamManagers
from auto_nag.user_activity import UserActivity


class TriageOwnerVacant(BzCleaner, Nag):
    def __init__(
        self,
        activity_weeks_count: int = 8,
        absent_weeks_count: int = 4,
    ):
        """Components with triage owner need to be assigned.

        Args:
            activity_weeks_count: the number of weeks of not doing any activity
                on Bugzilla before considering a triage owner as inactive.
            absent_weeks_count: number of weeks of not visiting Bugzilla before
                considering a triage owner as inactive.
        """
        super(TriageOwnerVacant, self).__init__()
        self.query_url = None
        self.activity_weeks_count = activity_weeks_count
        self.absent_weeks_count = absent_weeks_count

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
            product_handler=product_handler,
            product_data=data,
        ).wait()

        return data

    def nag_template(self):
        return self.template()

    def identify_vacant_components(self):
        # Filter out products and components that are not active
        products = [
            {
                **product,
                "components": [
                    component
                    for component in product["components"]
                    if component["is_active"]
                ],
            }
            for product in self.fetch_products()
            if product["is_active"]
        ]

        triage_owners = set()
        for product in products:
            for component in product["components"]:
                triage_owners.add(component["triage_owner"])

        user_activity = UserActivity(self.activity_weeks_count, self.absent_weeks_count)
        inactive_users = user_activity.check_users(triage_owners)

        team_managers = TeamManagers()
        vacant_components = []
        for product in products:
            for component in product["components"]:
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
                    "status": user_activity.get_string_status(
                        inactive_users[triage_owner]["status"]
                    ),
                }

                vacant_components.append(info)
                self.add(manager["mozilla_email"], info)

        return vacant_components

    def populate_num_untriaged_bugs(self, components: List[dict]) -> None:
        """Add the number of untriaged bugs and the URL to its search query to
        the provided components.

        The method will mutate the provided dictionaries to add the results.
        """

        def handler(bug, data):
            data["untriaged_bugs"] += 1

        queries = [None] * len(components)
        for i, component in enumerate(components):
            params = {
                "resolution": "---",
                "severity": "--",
                "bug_type": "defect",
                "product": component["product"],
                "component": component["component"],
            }
            component["untriaged_bugs"] = 0
            component["untriaged_bugs_url"] = utils.get_bz_search_url(params)
            query = Bugzilla(
                params,
                bughandler=handler,
                include_fields="-",
                bugdata=component,
            ).get_data()

            queries[i] = query

        # Since we query Bugzilla concurrently, we need to wait for the results
        # form all queries.
        for query in queries:
            query.wait()

    def get_email_data(self, date: str) -> List[dict]:
        components = self.identify_vacant_components()
        self.populate_num_untriaged_bugs(components)
        return components

    def organize_nag(self, data):
        return data

    def get_cc(self):
        return set()


if __name__ == "__main__":
    TriageOwnerVacant().run()
