# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import json
import os

import requests

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

    new_data = {}
    for person in data["users"]:
        person = person["profile"]
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
        if "bugzilla_mozilla_org_primary_email" in person["identities"]:
            bugzillaEmail = person["identities"]["bugzilla_mozilla_org_primary_email"][
                "value"
            ]
        if not bugzillaEmail and "HACK#BMOMAIL" in person["usernames"]["values"]:
            bugzillaEmail = person["usernames"]["values"]["HACK#BMOMAIL"]

        if bugzillaEmail is None:
            bugzillaEmail = ""

        del person["usernames"]["values"]["LDAP-posix_id"]
        del person["usernames"]["values"]["LDAP-posix_uid"]
        im = list(person["usernames"]["values"].values())

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
            "title": title,
        }

        if im:
            new["im"] = im

        new_data[mail] = new

    for person in new_data.values():
        manager_mail = person["manager"]["dn"]
        manager_cn = all_cns[manager_mail]
        manager_dn = all_dns[manager_mail]
        person["manager"]["cn"] = manager_cn
        person["manager"]["dn"] = manager_dn

    new_data = list(new_data.values())

    with open("./auto_nag/scripts/configs/people.json", "w") as Out:
        json.dump(new_data, Out, sort_keys=True, indent=4, separators=(",", ": "))


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
