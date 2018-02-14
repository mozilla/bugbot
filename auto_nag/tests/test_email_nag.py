
import datetime

from auto_nag.bugzilla.utils import get_project_root_path, getVersions
from auto_nag.bugzilla.agents import BMOAgent
from auto_nag.bugzilla.models import Bug
from auto_nag.scripts.phonebook import PhonebookDirectory
from auto_nag.scripts.email_nag import (get_last_manager_comment,
                                        get_last_assignee_comment,
                                        generateEmailOutput)


class TestEmailNag:
    def setUp(self):
        bug_number = 489656
        bmo = BMOAgent()
        self.bug = bmo.get_bug(bug_number)
        self.people = PhonebookDirectory(dryrun=True, isTest=True)
        hidden_dict = {
                'id': 123456,
                'summary': 'hide me',
                'assigned_to_detail': {'real_name': 'nobody'},
                'groups': [{'name': 'security group'}]}
        hidden_dict.update({'cf_status_firefox' + version: '---'
                            for version in getVersions()})
        self.hidden_bug = Bug.from_dict(hidden_dict)
        assignee = 'email@example.com'
        self.manager = {'mozillaMail': 'test@mozilla.com',
                        'bugzillaEmail': 'demo@bugzilla.com'}
        self.person = {'mozillaMail': 'test@mozilla.com',
                        'bugzillaEmail': 'demo@bugzilla.com'}

    def test_get_last_manager_comment(self):
        self.bug.comments[-1].creator = 'test@mozilla.com'
        last_mgr_comnt = get_last_manager_comment(self.bug.comments,
                                                  self.manager,
                                                  self.person)
        assert isinstance(last_mgr_comnt, (datetime.datetime))

    def test_get_last_assignee_comment(self):
        self.bug.comments[-1].creator = 'test@mozilla.com'
        lac = get_last_assignee_comment(self.bug.comments, self.person)
        assert isinstance(lac, (datetime.datetime))

    def test_generateEmailOutput(self):
        query = {'Test': {'bugs': [self.bug]}}
        toaddrs, message = generateEmailOutput('Test', query, 'daily_email',
                                               self.people, False,
                                               'Test@test.com')
        contents = ('From', 'To', 'CC', 'Subject:', '= Next Actions =',
                    '= Queries =', 'Sincerely,', self.bug.summary)
        assert '@' in toaddrs[0]
        assert all(content in message for content in contents)
        query = {'Test': {'bugs': [self.hidden_bug]}}
        toaddrs, message = generateEmailOutput('Test', query, 'daily_email',
                                               self.people, False,
                                               'Test@test.com')
        contents = ('From', 'To', 'CC', 'Subject:', '= Next Actions =',
                    '= Queries =', 'Sincerely,')
        assert '@' in toaddrs[0]
        assert all(content in message for content in contents)
        assert self.hidden_bug.summary not in message
