
import datetime

from auto_nag.bugzilla.utils import get_project_root_path
from auto_nag.bugzilla.agents import BMOAgent
from auto_nag.scripts.phonebook import PhonebookDirectory


class TestPhonebook:
    def test_init(self):
        pd = PhonebookDirectory(dryrun=True)
        assert pd.people_by_bzmail
        assert pd.managers
        assert pd.vices
