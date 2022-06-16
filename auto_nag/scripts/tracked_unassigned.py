# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils
from libmozdata.release_calendar import get_calendar

from auto_nag import utils
from auto_nag.bzcleaner import BzCleaner
from auto_nag.team_managers import TeamManagers

TARGET_CHANNELS = ["release", "beta", "nightly"]


class TrackedUnassigned(BzCleaner):
    def __init__(self):
        super().__init__()
        self.init_versions()
        self.version_flags = []
        self.team_managers = TeamManagers()

        soft_freeze_date = get_calendar()[0]["soft freeze"]
        today = lmdutils.get_date_ymd("today")
        self.soft_freeze_days = (soft_freeze_date - today).days
        self.extra_ni = {"soft_freeze_days": self.soft_freeze_days}

    def description(self):
        return "Tracked bugs with no assignee"

    def get_extra_for_needinfo_template(self):
        return self.extra_ni

    def columns(self):
        return ["id", "summary", "reasons", "is_regression"]

    def handle_bug(self, bug, data):
        bugid = str(bug["id"])

        bug_trackings = [
            flag
            for flag in self.version_flags
            if bug.get(flag["tracking_field"]) in ("blocking", "+")
            and bug.get(flag["status_field"]) in ("affected", "---")
        ]

        reasons = [
            "{tracking_type} firefox{version} ({channel})".format(
                tracking_type=(
                    "tracked for" if bug[flag["tracking_field"]] == "+" else "blocking"
                ),
                version=flag["version"],
                channel=flag["channel"],
            )
            for flag in bug_trackings
        ]

        is_regression = "regression" in bug["keywords"]
        show_soft_freeze_comment = self.soft_freeze_days <= 14 and is_regression

        data[bugid] = {
            "reasons": reasons,
            "is_regression": is_regression,
        }

        self.extra_ni[bugid] = {
            "reasons": utils.english_list(reasons),
            "show_soft_freeze_comment": show_soft_freeze_comment,
        }

        return bug

    def get_bz_params(self, date):
        fields = [
            "keywords",
            "component.team_name",
            "components.team_name",
            "triage_owner",
        ]

        params = {
            "include_fields": fields,
            "resolution": "---",
            "f1": "OP",
            "j1": "OR",
        }
        for channel in TARGET_CHANNELS:
            version = self.versions[channel]
            tracking_field = utils.get_flag(version, "tracking", channel)
            status_field = utils.get_flag(version, "status", channel)
            fields.extend((tracking_field, status_field))

            # We need this to explain the needinfo
            self.version_flags.append(
                {
                    "version": version,
                    "channel": channel,
                    "tracking_field": tracking_field,
                    "status_field": status_field,
                }
            )

            n = int(utils.get_last_field_num(params))
            params.update(
                {
                    f"f{n}": "OP",
                    f"f{n+1}": tracking_field,
                    f"o{n+1}": "anyexact",
                    f"v{n+1}": ["+", "blocking"],
                    f"f{n+2}": status_field,
                    f"o{n+2}": "anyexact",
                    f"v{n+2}": ["---", "affected"],
                    f"f{n+3}": "CP",
                }
            )
        n = int(utils.get_last_field_num(params))
        params[f"f{n}"] = "CP"
        utils.get_empty_assignees(params)

        return params

    def get_mail_to_auto_ni(self, bug):
        manager = self.team_managers.get_component_manager(bug["component"], False)
        if manager:
            return {
                "mail": manager["bz_email"],
                "nickname": manager["nick"],
            }

        if not bug["triage_owner"]:
            return None

        return {
            "mail": bug["triage_owner"],
            "nickname": bug["triage_owner_detail"]["nick"],
        }


if __name__ == "__main__":
    TrackedUnassigned().run()
