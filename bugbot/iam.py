# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import json
import os
from typing import Dict

import requests
from libmozdata.bugzilla import BugzillaUser

from . import logger, utils


def get_access_token():
    scope = {
        "classification": [
            "mozilla_confidential",
            "workgroup:staff_only",
            "public",
            "workgroup",
        ],
        "display": ["staff", "ndaed", "vouched", "authenticated", "public", "none"],
        "search": ["all"],
    }
    scope = " ".join(
        f"{key}:{value}" for key, values in scope.items() for value in values
    )

    payload = {
        "client_id": utils.get_login_info()["iam_client_id"],
        "client_secret": utils.get_login_info()["iam_client_secret"],
        "audience": "api.sso.mozilla.com",
        "scope": scope,
        "grant_type": "client_credentials",
    }

    resp = requests.post("https://auth.mozilla.auth0.com/oauth/token", json=payload)
    access = resp.json()

    assert "access_token" in access.keys()

    return access["access_token"]


def clean_data(d):
    if isinstance(d, dict):
        for k in ["metadata", "signature"]:
            if k in d:
                del d[k]

        for v in d.values():
            clean_data(v)
    elif isinstance(d, list):
        for v in d:
            clean_data(v)


def get_email_info(email):
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    resp = requests.get(
        f"https://person.api.sso.mozilla.com/v2/user/primary_email/{email}",
        headers=headers,
    )
    data = resp.json()
    clean_data(data)

    return data


def get_all_info(output_dir=""):
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    resp = requests.get(
        "https://person.api.sso.mozilla.com/v2/users/id/all/by_attribute_contains?staff_information.staff=True&active=True&fullProfiles=True",
        headers=headers,
    )
    data = resp.json()
    clean_data(data)

    next_page = data["nextPage"]

    while next_page is not None:
        print(f"{next_page}")
        resp = requests.get(
            f"https://person.api.sso.mozilla.com/v2/users/id/all/by_attribute_contains?staff_information.staff=True&active=True&fullProfiles=True&nextPage={next_page}",
            headers=headers,
        )
        d = resp.json()
        clean_data(d)
        data["users"] += d["users"]
        next_page = d["nextPage"]

    del data["nextPage"]

    if output_dir:
        with open(os.path.join(output_dir, "iam_dump.json"), "w") as Out:
            json.dump(data, Out, sort_keys=True, indent=4, separators=(",", ": "))

    return data


def get_phonebook_dump(output_dir=""):
    data = None
    if output_dir:
        path = os.path.join(output_dir, "iam_dump.json")
        if os.path.isfile(path):
            with open(path, "r") as In:
                data = json.load(In)
    if not data:
        data = get_all_info(output_dir=output_dir)

    all_cns = {}
    all_dns = {}

    must_have = {
        "first_name",
        "last_name",
        "identities",
        "access_information",
        "staff_information",
    }
    new_data = {}
    for person in data["users"]:
        person = person["profile"]

        if not (must_have < set(person.keys())):
            continue

        if not person["access_information"]["hris"]["values"]:
            continue
        mail = person["access_information"]["hris"]["values"]["primary_work_email"]
        dn = person["identities"]["mozilla_ldap_id"]["value"]
        manager_mail = person["access_information"]["hris"]["values"][
            "managers_primary_work_email"
        ]
        if not manager_mail:
            manager_mail = mail

        _mail = person["identities"]["mozilla_ldap_primary_email"]["value"]
        assert mail == _mail

        ismanager = person["staff_information"]["manager"]["value"]
        isdirector = person["staff_information"]["director"]["value"]
        cn = "{} {}".format(person["first_name"]["value"], person["last_name"]["value"])
        bugzillaEmail = ""
        bugzillaID = None
        if "bugzilla_mozilla_org_primary_email" in person["identities"]:
            bugzillaEmail = person["identities"]["bugzilla_mozilla_org_primary_email"][
                "value"
            ]
            bugzillaID = person["identities"]["bugzilla_mozilla_org_id"]["value"]

        im = None

        values = person.get("usernames", {}).get("values", None)
        if values is not None:
            if not bugzillaEmail and "HACK#BMOMAIL" in values:
                bugzillaEmail = values["HACK#BMOMAIL"]

            values.pop("LDAP-posix_id", None)
            values.pop("LDAP-posix_uid", None)
            im = list(values.values())

        if bugzillaEmail is None:
            bugzillaEmail = ""

        title = person["staff_information"]["title"]["value"]
        all_cns[mail] = cn
        all_dns[mail] = dn

        new = {
            "mail": mail,
            "manager": {"cn": "", "dn": manager_mail},
            "ismanager": "TRUE" if ismanager else "FALSE",
            "isdirector": "TRUE" if isdirector else "FALSE",
            "cn": cn,
            "dn": dn,
            "bugzillaEmail": bugzillaEmail,
            "bugzillaID": bugzillaID,
            "title": title,
        }

        if im:
            new["im"] = im

        new_data[mail] = new

    to_remove = []
    for mail, person in new_data.items():
        manager_mail = person["manager"]["dn"]
        if manager_mail not in all_cns:
            # no manager
            to_remove.append(mail)
            continue
        manager_cn = all_cns[manager_mail]
        manager_dn = all_dns[manager_mail]
        person["manager"]["cn"] = manager_cn
        person["manager"]["dn"] = manager_dn

    for mail in to_remove:
        del new_data[mail]

    update_bugzilla_emails(new_data)
    new_data = list(new_data.values())

    with open("./bugbot/scripts/configs/people.json", "w") as Out:
        json.dump(new_data, Out, sort_keys=True, indent=4, separators=(",", ": "))


def update_bugzilla_emails(data: Dict[str, dict]) -> None:
    """Update the bugzilla emails based on the Bugzilla ID and the Mozilla LDAP email.

    Args:
        data: The data to update.
    """

    users_by_bugzilla_id = {
        int(person["bugzillaID"]): person
        for person in data.values()
        if person["bugzillaID"]
    }

    # Currently employees can have permissions if they use their Mozilla email
    # without the need to link their Bugzilla accounts to PMO. Thus we check here
    # if employees already have a Bugzilla account using their Mozilla emails.
    #
    # Once BMO and PMO are fully integrated (plan in progress), this will be
    # changed and employees will not have permissions unless they link their
    # Bugzilla account to PMO.
    users_to_check = [*data, *users_by_bugzilla_id]

    def handler(bz_user, data):
        if bz_user["id"] in users_by_bugzilla_id:
            person = users_by_bugzilla_id[bz_user["id"]]
        elif bz_user["name"] in data:
            person = data[bz_user["name"]]
        else:
            raise Exception(f"Can't find {bz_user['name']} in the data")

        if (
            person.get("found_on_bugzilla")
            and str(bz_user["id"]) != person["bugzillaID"]
        ):
            # If the linked Bugzilla account is still active, we should not
            # overwrite it with the other account.
            return

        person["found_on_bugzilla"] = True
        if person["bugzillaEmail"] != bz_user["name"]:
            logger.info(
                "Update bugzilla email for %s from '%s' to '%s'",
                person["cn"],
                person["bugzillaEmail"],
                bz_user["name"],
            )
            person["bugzillaEmail"] = bz_user["name"]

    def fault_user_handler(bz_user, data):
        logger.debug("Can't find %s on bugzilla", bz_user["name"])

    BugzillaUser(
        users_to_check,
        include_fields=["id", "name"],
        user_handler=handler,
        user_data=data,
        fault_user_handler=fault_user_handler,
    ).wait()

    for person in data.values():
        if "found_on_bugzilla" not in person:
            person["found_on_bugzilla"] = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate an old phonebook dump using IAM api"
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        action="store",
        default="",
        help="Output directory where to dump temporary IAM data",
    )
    args = parser.parse_args()
    try:
        get_phonebook_dump(output_dir=args.output)
    except Exception:
        logger.exception("Tool iam")
