
from auto_nag.bugzilla.utils import get_project_root_path
from auto_nag.bugzilla.agents import BMOAgent
from auto_nag.scripts.phonebook import PhonebookDirectory
from auto_nag.scripts.email_nag import (get_last_manager_comment,
                                        get_last_assignee_comment,
                                        generateEmailOutput)


class TestEmailNag:
    def setUp(self):
        bug_number = 656214
        bmo = BMOAgent()
        self.bug = bmo.get_bug(bug_number)
        self.people = PhonebookDirectory(TEST=True)
        assignee = self.bug.assigned_to.name
        if assignee in self.people.people_by_bzmail:
            self.person = dict(self.people.people_by_bzmail[assignee])
        else:
            self.person = None

    def test_get_last_manager_comment(self):
        last_mgr_comnt = get_last_manager_comment(self.bug.comments,
                                                  'example@mozilla-test.com',
                                                  self.person)
        print last_mgr_comnt

    def test_get_last_assignee_comment(self):
        lac = get_last_assignee_comment(self.bug.comments, self.person)
        print lac

    def test_generateEmailOutput(self):
        query = {'Test': {'bugs': [self.bug], 'show_summary': '0'}}
        toaddrs, message = generateEmailOutput('Test', query, 'daily_email',
                                               self.people, False,
                                               'Test@test.com')
        contents = ('From', 'To', 'CC', 'Subject:', '= Next Actions =',
                    '= Queries =', 'Sincerely,')
        assert '@' in toaddrs[0]
        assert all(content in message for content in contents)
