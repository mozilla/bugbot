# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from . import utils
from .bugzilla import Bugzilla


class BZInfo(Bugzilla):
    """Information relative to bugs data in bugzilla"""

    def __init__(self, bugids):
        """Constructor

        Args:
            bugids (List[str]): list of bug ids or search query
        """
        super(BZInfo, self).__init__(
            bugids,
            include_fields=[
                "id",
                "severity",
                "component",
                "product",
                "creator",
                "assigned_to",
            ],
            bughandler=self.__bug_handler,
            historyhandler=self.__history_handler,
        )
        #                             commenthandler=self.__comment_handler)
        self.info = {}
        for bugid in self.bugids:
            self.info[bugid] = {
                "ownership": [],
                "reviewers": set(),
                "commenters": {},
                "authorized": False,
            }
        self.reply_pattern = re.compile(r"^\(In reply to .* comment #([0-9]+)\)")
        self.dupbug_pattern = re.compile(
            r"\*\*\* Bug [0-9]+ has been marked as a duplicate of this bug. \*\*\*"
        )
        self.review_pattern = re.compile(r"review\?\(([^\)]+)\)")
        self.needinfo_pattern = re.compile(r"needinfo\?\(([^\)]+)\)")
        self.feedback_pattern = re.compile(r"feedback\?\(([^\)]+)\)")
        self.get_data()

    def get(self):
        """Get the information

        Returns:
            dict: dictionary containing information
        """
        self.wait()
        return self.info

    def get_best_collaborator(self):
        """Get the 'best' collaborator

        A collaboration between A & B is when A reviews a patch of B (or reciprocally)
        in term of graph:
           - each node represents a reviewer or a writer (owner)
           - each edge represents a collaboration
        here we count the degree of each node and find out who's the best collaborator

        it could be interesting to weight each contribution according to its date
        someone who made 20 contribs recently is probably better than someone 50 contribs
        two years ago...

        Returns:
            (str): a collaborator
        """
        # TODO: use this graph to get other metrics (??)
        # TODO: We could weight a contrib with a gaussian which depends to the time
        collaborations = {}
        for info in self.get().values():
            if info["authorized"]:
                owner = info["owner"]
                if owner not in collaborations:
                    collaborations[owner] = 0
                reviewers = info["reviewers"]
                feedbacks = info["feedbacks"]
                collabs = set()
                if reviewers and owner in reviewers:
                    collabs |= reviewers[owner]
                if feedbacks and owner in feedbacks:
                    collabs |= feedbacks[owner]
                if collabs:
                    collaborations[owner] += len(collabs)
                    for person in collabs:
                        collaborations[person] = (
                            collaborations[person] + 1
                            if person in collaborations
                            else 1
                        )

        # maybe we should compute the percentage of collaborations just to give an idea

        return utils.get_best(collaborations)

    def get_best_component_product(self):
        """Get stats on components and products

        The idea is to be able to get the component and the product where this file lives.
        Useful to prefile bug report

        Returns:
            (tuple): a pair containing 'best' component & product
        """
        comps_prods = {}

        for info in self.get().values():
            if info["authorized"]:
                comp_prod = (info["component"], info["product"])
                comps_prods[comp_prod] = (
                    comps_prods[comp_prod] + 1 if comp_prod in comps_prods else 1
                )

        return utils.get_best(comps_prods)

    def __bug_handler(self, bug):
        """Handler to use with the bug retrieved from bugzilla

        Args:
            bug (dict): json data
            data (dict): the container which will receive the data
        """
        self.info[str(bug["id"])].update(
            {
                "authorized": True,
                "severity": bug["severity"],
                "component": bug["component"],
                "product": bug["product"],
                "reporter": bug["creator"],
                "owner": bug["assigned_to_detail"]["email"],
            }
        )

    def __history_handler(self, bug):
        """Handler to use with the history retrieved from bugzilla

        Args:
            bug (dict): json data
            data (dict): the container which will receive the data
        """
        ownership = []
        reviewers = {}
        feedbacks = {}
        bugid = str(bug["id"])
        history = bug["history"]
        for h in history:
            who = h["who"]
            owner = None
            changes = h["changes"]
            for change in changes:
                field = change["field_name"]
                removed = change["removed"]
                added = change["added"]

                if field == "status":
                    if removed == "NEW" and added == "ASSIGNED":
                        owner = who
                elif field == "assigned_to":
                    owner = added
                elif field == "flagtypes.name":
                    # Get the reviewers
                    for m in self.review_pattern.finditer(added):
                        if who in reviewers:
                            reviewers[who].add(m.group(1))
                        else:
                            reviewers[who] = set([m.group(1)])

                    # Get people pinged for feedback
                    for m in self.feedback_pattern.finditer(added):
                        if who in feedbacks:
                            feedbacks[who].add(m.group(1))
                        else:
                            feedbacks[who] = set([m.group(1)])

            if owner and (not ownership or ownership[-1]["owner"] != owner):
                ownership.append(
                    {"owner": owner, "touch_by": who, "touch_when": h["when"]}
                )

        self.info[bugid].update(
            {"ownership": ownership, "reviewers": reviewers, "feedbacks": feedbacks}
        )

    def __comment_handler(self, bug, bugid):
        """Handler to use with the comment retrieved from bugzilla

        Args:
            bug (dict): json data
            data (dict): the container which will receive the data
        """
        assert "comments" in bug

        commenters = {}
        authors = []
        for comment in bug["comments"]:
            text = comment["text"]
            if not self.dupbug_pattern.match(text):
                author = comment["author"]
                authors.append(author)
                if author not in commenters:
                    commenters[author] = []

                for m in self.reply_pattern.finditer(comment["raw_text"]):
                    n = int(m.group(1))
                    if n >= 1 and n <= len(authors):
                        commenters[authors[n - 1]].append(author)

            self.info[bugid].update({"commenters": commenters})
