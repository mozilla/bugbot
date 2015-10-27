
try:
    # If relman-auto-nag is installed
    from auto_nag.bugzilla.agents import BMOAgent
except:
    # If relman-auto-nag not installed, add project root directory into
    # PYTHONPATH
    from auto_nag.bugzilla.utils import os
    import sys
    import inspect
    currentdir = os.path.dirname(os.path.abspath(
                                 inspect.getfile(inspect.currentframe())))
    parentdir = os.path.dirname(currentdir)
    sys.path.insert(0, parentdir)
    from auto_nag.bugzilla.agents import BMOAgent

from nose.tools import assert_equal

class TestModels:
    # Test bugzilla agent methods
    def test_BugSearch(self):
        # Set whatever REST API options we want
        options = {
            'changed_after':    ['2012-12-24'],
            'changed_before':   ['2012-12-27'],
            'changed_field':    ['status'],
            'changed_field_to': ['RESOLVED'],
            'product':          ['Firefox'],
            'resolution':       ['FIXED'],
            'include_fields':   ['attachments'],
        }
        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api
        buglist = bmo.get_bug_list(options)
        assert buglist != []

    def test_BugAttributes(self):
        bug_number = 656222
        attrs = ['summary', 'id', 'assigned_to', 'creator', 'target_milestone',
                 'attachments', 'comments', 'history', 'keywords', 'status',
                 'resolution', 'cf_blocking_20', 'cf_blocking_fennec',
                 'cf_crash_signature', 'creation_time', 'flags', 'blocks',
                 'depends_on', 'url', 'cc', 'keywords', 'whiteboard', 'op_sys',
                 'platform', 'priority', 'product', 'qa_contact', 'severity',
                 'see_also', 'version', 'alias', 'classification', 'component',
                 'is_cc_accessible', 'is_everconfirmed',
                 'is_creator_accessible', 'last_change_time', 'ref', 'token',
                 'actual_time', 'deadline', 'estimated_time',
                 'percentage_complete', 'remaining_time', 'work_time']

        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api and check all the atributes which are
        # defined in Class Bug
        bug = bmo.get_bug(bug_number)
        for attr in attrs:
            assert hasattr(bug, attr)

    def test_Bugrepr(self):
        bug_number = 656222
        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api and check all the atributes which are
        # defined in Class Bug
        bug = bmo.get_bug(bug_number)
        assert '<Bug ' in repr(bug)

    def test_Bugstr(self):
        bug_number = 656222
        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api and check all the atributes which are
        # defined in Class Bug
        bug = bmo.get_bug(bug_number)
        assert '[Bug ' in str(bug)

    def test_Bughash(self):
        bug_number = 656222
        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api and check all the atributes which are
        # defined in Class Bug
        bug = bmo.get_bug(bug_number)
        assert hash(bug) == bug_number

    def test_UserAttributes(self):
        attrs = ['name', 'real_name', 'ref']

        bug_number = 656222
        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api and check all the atributes which are
        # defined in Class Bug
        bug = bmo.get_bug(bug_number)
        for attr in attrs:
            assert hasattr(bug.creator, attr)

    def test_Userrepr(self):
        bug_number = 656222
        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api and check all the atributes which are
        # defined in Class Bug
        creator = bmo.get_bug(bug_number).creator
        assert '<User ' in repr(creator)

    def test_Userstr(self):
        bug_number = 656222
        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api and check all the atributes which are
        # defined in Class Bug
        creator = bmo.get_bug(bug_number).creator
        assert str(creator) in repr(creator) and 'instance at' not in \
               str(creator)

    def test_Bughash(self):
        bug_number = 656222
        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api and check all the atributes which are
        # defined in Class Bug
        creator = bmo.get_bug(bug_number).creator
        assert isinstance(hash(creator), (int, long))
