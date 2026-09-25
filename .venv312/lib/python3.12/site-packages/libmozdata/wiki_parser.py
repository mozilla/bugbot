# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

try:
    from HTMLParser import HTMLParser
except:  # NOQA
    from html.parser import HTMLParser


class InvalidWiki(Exception):
    def __init__(self, s):
        super(InvalidWiki, self).__init__(s)


class Td(object):
    def __init__(self, row_span):
        super(Td, self).__init__()
        self.data = ""
        self.row_span = int(row_span)

    def set(self, data):
        self.data = data


class Tr(object):
    def __init__(self):
        super(Tr, self).__init__()
        self.elems = []

    def add(self, row_span):
        self.elems.append(Td(row_span))

    def set(self, data):
        self.elems[-1].set(data)


class Table(object):
    def __init__(self):
        super(Table, self).__init__()
        self.rows = []

    def add_row(self):
        self.rows.append(Tr())

    def add_cell(self, row_span):
        self.rows[-1].add(row_span)

    def set(self, data):
        self.rows[-1].set(data)

    def get(self):
        res = []
        for tr in self.rows:
            res.append(tr.elems)
        for i, tr in enumerate(self.rows):
            res_i = res[i]
            for j, td in enumerate(tr.elems):
                if not isinstance(td, Td):
                    continue

                res_i[j] = td.data
                for k in range(1, td.row_span):
                    res[i + k].insert(j, td.data)

        C = len(res[0])
        for r in res:
            if len(r) < C:
                r.extend([""] * (C - len(r)))

        return res


class WikiParser(HTMLParser):
    def __init__(self, tables=[0]):
        HTMLParser.__init__(self)
        self.tables = []
        self.table = None
        self.td = None
        self.th = None
        self.table_counter = -1
        self.tables_number = set(tables)

    def feed(self, data):
        if not isinstance(data, str):
            data = str(data, "ascii")
        HTMLParser.feed(self, data)

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table_counter += 1
            if self.table_counter in self.tables_number:
                self.table = Table()
        if self.table is not None:
            if tag == "tr":
                self.table.add_row()
            elif tag == "td":
                attrs = dict(attrs)
                self.table.add_cell(attrs.get("rowspan", 1))
                self.td = ""
            elif tag == "th":
                attrs = dict(attrs)
                self.table.add_cell(attrs.get("rowspan", 1))
                self.th = ""

    def handle_endtag(self, tag):
        if self.table is not None:
            if tag == "table":
                self.tables.append(self.table)
                self.table = None
                if self.table_counter == max(self.tables_number):
                    raise StopIteration()
            elif tag == "td":
                self.table.set(self.td)
                self.td = None
            elif tag == "th":
                self.table.set(self.th)
                self.th = None
        if tag == "html":
            raise StopIteration()

    def handle_data(self, data):
        data = data.strip()
        if self.td is not None:
            self.td += data
        elif self.th is not None:
            self.th += data

    def get_tables(self):
        res = []
        for table in self.tables:
            res.append(table.get())
        return res
