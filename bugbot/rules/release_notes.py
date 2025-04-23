import requests
from jinja2 import Environment, FileSystemLoader

from bugbot import mail, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.nag_me import Nag


class ReleaseNotes(BzCleaner, Nag):
    def __init__(self, version=None):
        super().__init__()
        self.version = version

    def description(self):
        return "Weekly Release Notes Digest"

    def template(self):
        return "release_notes.html"

    def get_email_data(self, date: str):
        params = {"date": date}
        if self.version:
            params["version"] = self.version
        base_url = "http://localhost:8080/"
        resp = requests.get(base_url, params=params)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for row in data["commits"]:
            parts = row.split(",")
            if len(parts) >= 4:
                results.append(
                    {
                        "category": parts[0].strip("[] "),
                        "title": parts[1].strip(),
                        "bug": parts[2].strip(),
                        "desc": parts[3].strip(),
                    }
                )
        return results

    def send_email(self, date="today"):
        login_info = utils.get_login_info()
        data = self.get_email_data(date)
        if data:
            preamble = f"The following were the identified relevant commits for version {self.version or '(unknown)'}"
            title, body = self.get_email(date, data, preamble=preamble)
            receivers = utils.get_config(self.name(), "receivers")
            mail.send(
                login_info["ldap_username"],
                receivers,
                title,
                body,
                html=True,
                login=login_info,
                dryrun=self.dryrun,
            )

    def get_email(self, date: str, data: dict, preamble: str = ""):
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template(self.template())
        message = template.render(date=date, data=data)
        common = env.get_template("common.html")
        body = common.render(
            preamble=preamble,
            message=message,
            query_url=None,
        )
        return self.get_email_subject(date), body


if __name__ == "__main__":
    ReleaseNotes(version="FIREFOX_BETA_136_BASE").run()
