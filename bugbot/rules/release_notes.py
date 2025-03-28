from jinja2 import Environment, FileSystemLoader

from bugbot import mail, utils
from bugbot.bzcleaner import BzCleaner
from bugbot.nag_me import Nag


class ReleaseNotes(BzCleaner, Nag):
    def __init__(self):
        super().__init__()

    def description(self):
        return "Weekly Release Notes Digest"

    def template(self):
        return "release_notes.html"

    def get_email_data(self, date: str):
        # Simulate API call to fetch release notes
        return [
            {"title": "New Dark Mode in Settings", "link": "https://example.com/1"},
            {
                "title": "Performance Improvements in Rendering",
                "link": "https://example.com/2",
            },
            {"title": "Security Fixes", "link": "https://example.com/3"},
        ]

    def send_email(self, date="today"):
        login_info = utils.get_login_info()
        data = self.get_email_data(date)
        if data:
            title, body = self.get_email(date, data)
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
    ReleaseNotes().run()
