import argparse
import csv
from datetime import date
from itertools import zip_longest
import re

from pymarc import Record, Field

from marcup.area_codes import area_codes


class MarcupRecord(Record):
    def __init__(self, metadata, avian=False, max=5):
        super().__init__()
        self.area_codes = area_codes
        self.metadata = metadata
        self.avian = avian

    def add(self, tag, indicators, subfields):
        self.add_field(Field(tag=tag, indicators=indicators, subfields=Field.convert_legacy_subfields(subfields)))

    def add_geographic_subjects(self, geonames=False):
        places = self.get_geographic_terms()[: self.max]
        self._add_terms("651", (" ", "7"), places, ("2", "fast"))

    def add_corporate_name_subjects(self):

        names_uris = self.get_corporate_name_subjects()[: self.max]

        self._add_terms_multiple_vocabularies(
            "610",
            names_uris,
            "2",
        )

    def add_personal_name_subjects(self):
        names_uris = self.get_personal_name_subjects()[: self.max]
        self._add_terms_multiple_vocabularies("600", names_uris, "1")

    def add_meeting_name_subjects(self):
        names = self.get_event_subjects()[: self.max]
        self._add_terms("611", ("2", "0"), names)

    def add_topic_subjects(self):
        topics = self.get_topic_subjects()[: self.max]
        self._add_terms("650", (" ", "7"), topics, ("2", "fast"))

    def add_genre_forms(self):
        genres = self.get_genre_forms()
        self._add_terms("655", (" ", "7"), genres, ("2", "aat"))

    def _add_terms(self, tag, indicators, terms, extra_subfields=tuple()):
        for term in terms:
            if term != "":
                self.add(tag, indicators, ("a", term, *extra_subfields))

    def _add_terms_multiple_vocabularies(
        self, tag, terms_uris, first_indicator, fallback_2nd_indicator=4
    ):
        for t, u in terms_uris:
            if t.strip() != "":
                if "id.loc.gov" in u:
                    self.add(tag, (first_indicator, "0"), ("a", t))
                elif "id.worldcat.org/fast" in u:
                    self.add(tag, (first_indicator, "7"), ("a", t, "2", "fast"))
                elif u == "":
                    self.add(tag, (first_indicator, "7"), ("a", t, "2", "local"))
                else:
                    self.add(tag, (first_indicator, fallback_2nd_indicator), ("a", t))

    def add_corperate_creators_contributors(self):
        names = self.get_corporate_creators_contributors()[: self.max]
        self._add_terms("710", ("2", " "), names)

    def add_personal_creators_contributors(self):
        names = self.get_personal_creators_contributors()[: self.max]
        self._add_terms("700", ("1", " "), names)

    def add_finding_aid_links(self):
        finding_aids = self.get_original_collections()[: self.max]
        finding_aid_arks = self.get_original_arks()[: self.max]
        for (
            finding_aid,
            ark,
        ) in zip(finding_aids, finding_aid_arks):
            self.add("856", ("4", "2"), ("3", f"Finding aid for {self.title_case(finding_aid)}", "u", ark))

    def add_geographic_area_codes(self):
        geographic_area_codes = []
        in_iowa = False

        for term in self.geographic_terms:
            if "Iowa" in term:
                in_iowa = True

            code = self.area_codes.get(term)
            if code is not None:
                geographic_area_codes.append(code)

        if in_iowa:
            geographic_area_codes.append(self.area_codes.get("Iowa"))

        if geographic_area_codes:
            subfields = self._repeat_subfields(geographic_area_codes)

            self.add("043", (" ", " "), subfields)

    def _repeat_subfields(self, terms, subfield="a"):
        subfields = [sf for pair in [[subfield, term] for term in terms] for sf in pair]

        return subfields

    # Would it make more sense to add 1 preferred citation with multiple
    # physical collections listed rather than multiple citations?
    # ^ This is the option I'm going with for now unless Chris suggests
    #   otherwise. Will be easy enough to do multiple fields if needed.
    def add_preferred_citation(self):
        digital_collection = self.digital_collection
        original_collections = self.get_original_collections()
        original_call_numbers = self.get_original_call_numbers()
        originals_string = " ".join(
            [
                f"{self.title_case(c[0])}, {c[1]}"
                for c in zip(
                    original_collections[: self.max], original_call_numbers[: self.max]
                )
            ]
        )
        citation_string = f"{digital_collection}, {originals_string}, Special Collections and University Archives, Iowa State University Library."

        self.add("524", (" ", " "), ("a", citation_string))

    def _get_terms(self, *args, sep=";"):
        terms_counter = {}

        for column in args:
            for row in self.metadata:
                t = row.get(column, "")
                if t != "":
                    if sep in t:
                        terms = t.split(sep)
                        for term in terms:
                            terms_counter = self._update_term_counting_dict(
                                terms_counter, term
                            )
                    else:
                        terms_counter = self._update_term_counting_dict(
                            terms_counter, t
                        )

        # Sort from most common to least common
        term_list = [
            i[0]
            for i in sorted(
                terms_counter.items(), key=lambda item: item[1], reverse=True
            )
        ]

        return term_list

    def _update_term_counting_dict(self, terms, term):
        if term in terms.keys():

            terms[term] += 1
        else:

            terms[term] = 1

        return terms

    def title_case(self, title):
        # Don't capitalize these words unless they are the first or last in
        # a title
        dont_capitalize = set([
            "A",
            "And",
            "As",
            "At",
            "But",
            "By",
            "Down",
            "For",
            "From",
            "If",
            "In",
            "Into",
            "Like",
            "Near",
            "Nor",
            "Of",
            "Off",
            "On",
            "Once",
            "Onto",
            "Or",
            "Over",
            "Past",
            "So",
            "Than",
            "That",
            "To",
            "Upon",
            "When",
            "With",
            "Yet",
        ])

        capped = title.title().split()
        len_capped = len(capped)
        final_title = []

        for i, word in enumerate(capped):
            parts = word.split("'")
            # Don't capitalize the letter after an apostrophe in a contraction
            # or possessive ("Wasn't" or "Smith's")
            if len(parts) > 1:
                word = "'".join([parts[0], parts[1].lower()])
            if 0 < i < len_capped - 1:
                if word in dont_capitalize:
                    word = word.lower()
            final_title.append(word)

        return " ".join(final_title)

class IslandoraRecord(MarcupRecord):
    def __init__(self, metadata, max=5):
        super().__init__(metadata)

        self.max = max
        self.disclaimer = self.get_disclaimer()
        self.collection_metadata = self.metadata[0]
        self.digital_collection = self.collection_metadata["digital_collection"]
        self.physical_collections = self.get_original_collections()
        self.physical_call_numbers = self.get_original_call_numbers()
        self.years = self.get_years()
        self.geographic_terms = self.get_geographic_terms()
        self.bio_hist, self.summary = self.get_collection_descriptions()

        # LEADER
        # Type of Record
        self.leader[6] = "P"
        # Bibliographic Level
        self.leader[7] = "c"
        # Type of Control
        self.leader[8] = "a"
        # Encoding Level
        self.leader[17] = "I"
        # Descriptive Cataloging Form
        self.leader[18] = "i"

        # 008 (Also adds 041 field as needed)
        self.add_field(Field(tag="008", data=self.generate_008_field()))

        # Cataloging source
        self.add(
            "040",
            (" ", " "),
            (
                "a",
                "IWA",
                "b",
                "eng",
                "e",
                "dacs",
                "e",
                "rda",
                "c",
                "IWA",
            ),
        )

        # Geographic area code (043)
        self.add_geographic_area_codes()

        # Title statement
        self.add(
            "245",
            (" ", " "),
            (
                *self.get_title(),
                "f",
                self.get_date_range(),
            ),
        )

        # Production and copyright notice
        self.add(
            "264",
            (" ", "1"),
            ("a", "Ames, Iowa :", "b", "Iowa State University Library,"),
        )

        # Physical description
        self.add(
            "300",
            (" ", " "),
            ("a", f"1 online resource ({self.get_object_count()} digital objects)"),
        )

        # Biographical or historical data
        # Not sure if there's a great way to automatically handle biographical
        # sketch vs administrative history, so leaving 1st indicator blank for
        # now, so Stacey can add in the right one
        self.add("545", (" ", " "), ("a", self.bio_hist))

        # Summary
        self.add("520", ("2", " "), ("a", self.summary))

        # Restriction on access note
        self.add(
            "506",
            (" ", " "),
            (
                "a",
                "For copyright and re-use status, please consult the individual objects record.",
            ),
        )

        # Preferred citation of described material note
        self.add_preferred_citation()

        # Original version note
        for c in zip(self.physical_collections, self.physical_call_numbers):
            self.add(
                "534",
                (" ", " "),
                (
                    "p",
                    "Originals can be found in:",
                    "t",
                    self.title_case(c[0]),
                    "o",
                    c[1],
                    "l",
                    "Special Collections and University Archives, Iowa State University Library.",
                ),
            )

        # Disclaimer
        if self.disclaimer:
            self.add("500", (" ", " "), ("a", self.disclaimer))

        # Subject added entry: personal name (600)
        self.add_personal_name_subjects()

        # Subject added entry: corporate name (610)
        self.add_corporate_name_subjects()

        # Subject added entry: meeting name
        # Skipping this one for now as we have no (or next to no) NAF meeting names
        # in our metadata, just a few local event terms

        # Subject added entry: topical term (650)
        self.add_topic_subjects()

        # Subject added entry: geographic name (651)
        self.add_geographic_subjects()

        # Index term: genre/form
        self.add_genre_forms()

        # Added entry: personal name (700)
        self.add_personal_creators_contributors()

        # Added entry: corporate name (710)
        self.add_corperate_creators_contributors()

        # Added entry: corporate name
        self.add(
            "710",
            ("2", " "),
            (
                "a",
                "Iowa State University.",
                "b",
                "Library",
                "b",
                "Digital Collections.",
            ),
        )

        # Electronic location and access (of digital collection)
        self.add(
            "856",
            ("4", "0"),
            (
                "3",
                self.collection_metadata["title"],
                "u",
                self.collection_metadata["ark"],
                # Per Chris' 2023-05-18 email "We are not sure if we should
                # add '$7 0' to the 856 for the online resources yet. Let's
                # omit it for now." Commenting out instead of deleting in
                # case this changes in the future.
                # "7",
                # "0",
            ),
        )

        # Electronic location and access (of finding aid)
        self.add_finding_aid_links()


    def get_personal_name_subjects(self):
        return self._get_terms_and_uris("personal_name_subject")

    def get_personal_name_uris(self):
        return self._get_terms("personal_name_subject_valueURI")

    def get_corporate_name_subjects(self):
        return self._get_terms_and_uris("corporate_name_subject")

    def get_corporate_name_uris(self):
        return self._get_terms("corporate_name_subject_valueURI")

    def get_event_subjects(self):
        return self._get_terms("event_subject")

    def get_topic_subjects(self):
        return self._get_terms("topical_subject_fast", "topical_subject_local")

    def get_geographic_terms(self):
        if self.avian:
            return self._get_terms("geographic_subject_geonames")

        return self._get_terms("geographic_subject_fast", "geographic_subject_local")

    def get_genre_forms(self):
        return self._get_terms("aat_genre")

    def get_personal_creators_contributors(self):
        return self._get_terms(
            "personal_creator", "interviewee", "interviewer", "personal_contributor"
        )

    def get_corporate_creators_contributors(self):
        return self._get_terms("corporate_creator", "corporate_contributor")

    def get_original_collections(self):
        return self._get_terms("archival_collection")

    def get_original_call_numbers(self):
        return self._get_terms("archival_call_number")

    def get_original_arks(self):
        return self._get_terms("finding_aid_ark")

    def get_languages(self):
        return self._get_terms("language")


    def _get_terms_and_uris(self, *args):

        terms_counter = {}
        for column in args:
            for row in self.metadata:

                t = row.get(column, " ")
                u = row.get(f"{column}_valueURI", " ")

                if t != "":

                    if ";" in t:

                        ts = t.split(";")
                        uris = u.split(";")

                        for term, uri in zip_longest(ts, uris, fillvalue=""):

                            terms_counter = self._update_term_counting_dict(
                                terms_counter, (term, uri)
                            )

                    else:

                        terms_counter = self._update_term_counting_dict(
                            terms_counter, (t, u)
                        )

        term_list = [
            i[0]
            for i in sorted(
                terms_counter.items(), key=lambda item: item[1], reverse=True
            )
        ]

        return term_list

    def get_collection_descriptions(self):
        bio_hist, _, summary = self.metadata[0]["description"].partition(
            "The collection"
        )
        if summary != "":
            summary = f"{self.metadata[0]['title']} {summary}"

        return (bio_hist, summary)

    def get_disclaimer(self):
        if self.metadata[0].get("disclaimer") is not None:
            for row in self.metadata:
                if row["disclaimer"] != "":
                    return row["disclaimer"]

        return ""

    def get_object_count(self):
        count = 0

        for obj in self.metadata[1:]:
            if obj["ark"] != "":
                count += 1

        return count

    def get_years(self):
        return sorted(
            [
                md["date_original"][0:4]
                for md in self.metadata
                if md["date_original"] != ""
            ]
        )

    def get_date_range(self):
        if len(self.years) > 1:
            return f"{self.years[0]}-{self.years[-1]}."

        if len(self.years) == 1:
            return f"{self.years[0]}"

        return ""

    def get_title(self):
        subfields = self.metadata[0]["title"].split(":")
        if len(subfields) == 2:
            return ("a", f"{subfields[0]} : ", "b", f"{subfields[1]}, ")

        return ("a", f"{subfields[0]}, ")

    def get_physical_collection_info(self):
        physical_collections = {}
        for obj in self.metadata:
            archival_collection = obj["archival_collection"]
            if archival_collection in physical_collections.keys():
                physical_collections[archival_collection]["count"] += 1
            else:
                physical_collections[archival_collection] = {
                    "count": 1,
                    "call_number": obj["archival_call_number"],
                }

        return sorted(
            physical_collections.items(), key=lambda c: c[1]["count"], reverse=True
        )

    def generate_008_field(self):
        # Position 6, Type of date/Publication status
        # date_type = ""
        # Positions 7-10, Date 1
        # date_start = ""
        # Position 11-14, Date 2
        # date_end = ""
        lang = self.get_languages()

        if len(lang) > 1:

            self.add_041_field(lang)

        # Leave 6 and 7-14 blank per Chris' recommendations
        return (
            f"{date.today().strftime('%y%m%d')}         iau     o           {lang[0]} d"
        )

    def add_041_field(self, lang=None):
        if lang is None:
            lang = self.get_languages()

        self.add("041", (" ", " "), self._repeat_subfields(lang))
class MarcupRecord(Record):
    def __init__(self, metadata, source="islandora", max=5, avian=False):
        super().__init__()

        self.metadata = metadata
        self.source = source
        self.max = max
        self.avian = avian
        self.area_codes = area_codes
        self.disclaimer = self.get_disclaimer()
        self.collection_metadata = self.metadata[0]
        self.digital_collection = self.collection_metadata["digital_collection"]
        self.physical_collections = self.get_original_collections()
        self.physical_call_numbers = self.get_original_call_numbers()
        self.years = self.get_years()
        self.geographic_terms = self.get_geographic_terms()
        self.bio_hist, self.summary = self.get_collection_descriptions()

        # LEADER
        # Type of Record
        self.leader[6] = "P"
        # Bibliographic Level
        self.leader[7] = "c"
        # Type of Control
        self.leader[8] = "a"
        # Encoding Level
        self.leader[17] = "I"
        # Descriptive Cataloging Form
        self.leader[18] = "i"

        # 008 (Also adds 041 field as needed)
        self.add_field(Field(tag="008", data=self.generate_008_field()))

        # Cataloging source
        self.add(
            "040",
            (" ", " "),
            (
                "a",
                "IWA",
                "b",
                "eng",
                "e",
                "dacs",
                "e",
                "rda",
                "c",
                "IWA",
            ),
        )

        # Geographic area code (043)
        self.add_geographic_area_codes()

        # Title statement
        self.add(
            "245",
            ("1", "0"),
            (
                *self.get_title(),
                "f",
                self.get_date_range(),
            ),
        )

        # Production and copyright notice
        self.add(
            "264",
            (" ", "1"),
            ("a", "Ames, Iowa :", "b", "Iowa State University Library,"),
        )

        # Physical description
        self.add(
            "300",
            (" ", " "),
            ("a", f"1 online resource ({self.get_object_count()} digital objects)"),
        )

        # Biographical or historical data
        # Not sure if there's a great way to automatically handle biographical
        # sketch vs administrative history, so leaving 1st indicator blank for
        # now, so Stacey can add in the right one
        self.add("545", (" ", " "), ("a", self.bio_hist))

        # Summary
        self.add("520", ("2", " "), ("a", self.summary))

        # Restriction on access note
        self.add(
            "506",
            (" ", " "),
            (
                "a",
                "For copyright and re-use status, please consult the individual objects record.",
            ),
        )

        # Preferred citation of described material note
        self.add_preferred_citation()

        # Original version note
        for c in zip(self.physical_collections, self.physical_call_numbers):
            self.add(
                "534",
                (" ", " "),
                (
                    "p",
                    "Originals can be found in:",
                    "t",
                    c[0],
                    "o",
                    c[1],
                    "l",
                    "Special Collections and University Archives, Iowa State University Library.",
                ),
            )

        # Disclaimer
        if self.disclaimer:
            self.add("500", (" ", " "), ("a", self.disclaimer))

        # Subject added entry: personal name (600)
        self.add_personal_name_subjects()

        # Subject added entry: corporate name (610)
        self.add_corporate_name_subjects()

        # Subject added entry: meeting name
        # Skipping this one for now as we have no (or next to no) NAF meeting names
        # in our metadata, just a few local event terms

        # Subject added entry: topical term (650)
        self.add_topic_subjects()

        # Subject added entry: geographic name (651)
        self.add_geographic_subjects()

        # Index term: genre/form
        self.add_genre_forms()

        # Added entry: personal name (700)
        self.add_personal_creators_contributors()

        # Added entry: corporate name (710)
        self.add_corperate_creators_contributors()

        # Added entry: corporate name
        self.add(
            "710",
            ("2", " "),
            (
                "a",
                "Iowa State University.",
                "b",
                "Library",
                "b",
                "Digital Collections.",
            ),
        )

        # Electronic location and access (of digital collection)
        self.add(
            "856",
            ("4", "0"),
            (
                "3",
                self.collection_metadata["title"],
                "u",
                self.collection_metadata["ark"],
                "7",
                "0",
            ),
        )

        # Electronic location and access (of finding aid)
        self.add_finding_aid_links()

    def add(self, tag, indicators, subfields):
        self.add_field(Field(tag=tag, indicators=indicators, subfields=subfields))

    def add_geographic_subjects(self, geonames=False):
        places = self.get_geographic_terms()[: self.max]
        self._add_terms("651", (" ", "7"), places, ("2", "fast"))
        # for place in places:
        #    self.add("651", (" ", "7"), ("a", place, "2", "fast"))

    def add_corporate_name_subjects(self):

        names_uris = self.get_corporate_name_subjects()[: self.max]
        # uris = self.get_corporate_name_uris()[: self.max]

        self._add_terms_multiple_vocabularies(
            "610",
            names_uris,
            "2",
        )
        # self._add_terms("610", ("2", "0"), names)

    def add_personal_name_subjects(self):

        names_uris = self.get_personal_name_subjects()[: self.max]
        # uris = self.get_personal_name_uris()[: self.max]
        self._add_terms_multiple_vocabularies("600", names_uris, "1")
        # self._add_terms("600", ("1", "0"), names)

    def add_meeting_name_subjects(self):
        names = self.get_event_subjects()[: self.max]
        self._add_terms("611", ("2", "0"), names)

    def add_topic_subjects(self):
        topics = self.get_topic_subjects()[: self.max]
        self._add_terms("650", (" ", "7"), topics, ("2", "fast"))

    def add_genre_forms(self):
        genres = self.get_genre_forms()
        self._add_terms("655", (" ", "7"), genres, ("2", "aat"))

    def _add_terms(self, tag, indicators, terms, extra_subfields=tuple()):
        for term in terms:
            self.add(tag, indicators, ("a", term, *extra_subfields))

    def _add_terms_multiple_vocabularies(
        self, tag, terms_uris, first_indicator, fallback_2nd_indicator=4
    ):

        for t, u in terms_uris:

            if "id.loc.gov" in u:
                self.add(tag, (first_indicator, "0"), ("a", t))
            elif "id.worldcat.org/fast" in u:
                self.add(tag, (first_indicator, "7"), ("a", t, "2", "fast"))
            elif u == "":
                self.add(tag, (first_indicator, "7"), ("a", t, "2", "local"))
            else:
                self.add(tag, (first_indicator, fallback_2nd_indicator), ("a", t))

    def add_corperate_creators_contributors(self):
        names = self.get_corporate_creators_contributors()[: self.max]
        self._add_terms("710", ("2", " "), names)

    def add_personal_creators_contributors(self):
        names = self.get_personal_creators_contributors()[: self.max]
        self._add_terms("700", ("1", " "), names)

    def add_finding_aid_links(self):
        finding_aids = self.get_original_collections()[: self.max]
        finding_aid_arks = self.get_original_arks()[: self.max]
        for (
            finding_aid,
            ark,
        ) in zip(finding_aids, finding_aid_arks):
            self.add("856", ("4", "0"), ("3", finding_aid, "u", ark))

    def add_geographic_area_codes(self):
        geographic_area_codes = []
        in_iowa = False

        for term in self.geographic_terms:
            if "Iowa" in term:
                in_iowa = True

            code = self.area_codes.get(term)
            if code is not None:
                geographic_area_codes.append(code)

        if in_iowa:
            geographic_area_codes.append(self.area_codes.get("Iowa"))

        if geographic_area_codes:
            subfields = self._repeat_subfields(geographic_area_codes)

            self.add("043", (" ", " "), subfields)

    def _repeat_subfields(self, terms, subfield="a"):
        subfields = [sf for pair in [[subfield, term] for term in terms] for sf in pair]

        return subfields

    # Would it make more sense to add 1 preferred citation with multiple
    # physical collections listed rather than multiple citations?
    # ^ This is the option I'm going with for now unless Chris suggests
    #   otherwise. Will be easy enough to do multiple fields if needed.
    def add_preferred_citation(self):
        digital_collection = self.digital_collection
        original_collections = self.get_original_collections()
        original_call_numbers = self.get_original_call_numbers()
        originals_string = " ".join(
            [
                f"{c[0]}, {c[1]},"
                for c in zip(
                    original_collections[: self.max], original_call_numbers[: self.max]
                )
            ]
        )
        citation_string = f"{digital_collection}, {originals_string}, Special Collections and University Archives, Iowa State University Library."

        self.add("524", (" ", " "), ("a", citation_string))

    def get_personal_name_subjects(self):
        return self._get_terms_and_uris("personal_name_subject")

    def get_personal_name_uris(self):
        return self._get_terms("personal_name_subject_valueURI")

    def get_corporate_name_subjects(self):
        return self._get_terms_and_uris("corporate_name_subject")

    def get_corporate_name_uris(self):
        return self._get_terms("corporate_name_subject_valueURI")

    def get_event_subjects(self):
        return self._get_terms("event_subject")

    def get_topic_subjects(self):
        return self._get_terms("topical_subject_fast", "topical_subject_local")

    def get_geographic_terms(self):
        if self.avian:
            return self._get_terms("geographic_subject_geonames")

        return self._get_terms("geographic_subject_fast", "geographic_subject_local")

    def get_genre_forms(self):
        return self._get_terms("aat_genre")

    def get_personal_creators_contributors(self):
        return self._get_terms(
            "personal_creator", "interviewee", "interviewer", "personal_contributor"
        )

    def get_corporate_creators_contributors(self):
        return self._get_terms("corporate_creator", "corporate_contributor")

    def get_original_collections(self):
        return self._get_terms("archival_collection")

    def get_original_call_numbers(self):
        return self._get_terms("archival_call_number")

    def get_original_arks(self):
        return self._get_terms("finding_aid_ark")

    def get_languages(self):
        return self._get_terms("language")

    def _get_terms(self, *args):
        terms_counter = {}

        for column in args:
            for row in self.metadata:
                t = row.get(column, " ")
                if t != "":
                    if ";" in t:
                        terms = t.split(";")
                        for term in terms:
                            terms_counter = self._update_term_counting_dict(
                                terms_counter, term
                            )
                    else:
                        terms_counter = self._update_term_counting_dict(
                            terms_counter, t
                        )

        # Sort from most common to least common
        #
        term_list = [
            i[0]
            for i in sorted(
                terms_counter.items(), key=lambda item: item[1], reverse=True
            )
        ]
        #

        return term_list

    def _get_terms_and_uris(self, *args):

        terms_counter = {}
        for column in args:
            for row in self.metadata:

                t = row.get(column, " ")
                u = row.get(f"{column}_valueURI", " ")

                if t != "":

                    if ";" in t:

                        ts = t.split(";")
                        uris = u.split(";")

                        for term, uri in zip_longest(ts, uris, fillvalue=""):

                            terms_counter = self._update_term_counting_dict(
                                terms_counter, (term, uri)
                            )

                    else:

                        terms_counter = self._update_term_counting_dict(
                            terms_counter, (t, u)
                        )

        term_list = [
            i[0]
            for i in sorted(
                terms_counter.items(), key=lambda item: item[1], reverse=True
            )
        ]

        return term_list

    def _update_term_counting_dict(self, terms, term):
        if term in terms.keys():

            terms[term] += 1
        else:

            terms[term] = 1

        return terms

    def get_collection_descriptions(self):
        bio_hist, _, summary = self.metadata[0]["description"].partition(
            "The collection"
        )
        if summary != "":
            summary = f"{self.metadata[0]['title']} {summary}"

        return (bio_hist, summary)

    def get_disclaimer(self):
        if self.metadata[0].get("disclaimer") is not None:
            for row in self.metadata:
                if row["disclaimer"] != "":
                    return row["disclaimer"]

        return ""

    def get_object_count(self):
        count = 0

        for obj in self.metadata[1:]:
            if obj["ark"] != "":
                count += 1

        return count

    def get_years(self):
        return sorted(
            [
                # date.fromisoformat(md["date_original"]).year
                md["date_original"][0:4]
                for md in self.metadata
                if md["date_original"] != ""
            ]
        )

    def get_date_range(self):
        if len(self.years) > 1:
            return f"{self.years[0]}-{self.years[-1]}."

        if len(self.years) == 1:
            return f"{self.years[0]}"

        return ""

    def get_title(self):
        subfields = self.metadata[0]["title"].split(":")
        if len(subfields) == 2:
            return ("a", f"{subfields[0]} : ", "b", f"{subfields[1]}, ")

        return ("a", f"{subfields[0]}, ")

    def get_physical_collection_info(self):
        physical_collections = {}
        for obj in self.metadata:
            archival_collection = obj["archival_collection"]
            if archival_collection in physical_collections.keys():
                physical_collections[archival_collection]["count"] += 1
            else:
                physical_collections[archival_collection] = {
                    "count": 1,
                    "call_number": obj["archival_call_number"],
                }

        return sorted(
            physical_collections.items(), key=lambda c: c[1]["count"], reverse=True
        )

    def generate_008_field(self):
        # Position 6, Type of date/Publication status
        # date_type = ""
        # Positions 7-10, Date 1
        # date_start = ""
        # Position 11-14, Date 2
        # date_end = ""
        lang = self.get_languages()

        if len(lang) > 1:

            self.add_041_field(lang)

        # Leave 6 and 7-14 blank per Chris' recommendations
        return (
            f"{date.today().strftime('%y%m%d')}         iau     o           {lang[0]} d"
        )

    def add_041_field(self, lang=None):
        if lang is None:
            lang = self.get_languages()

        self.add("041", (" ", " "), self._repeat_subfields(lang))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("out")
    parser.add_argument("--avian", action="store_true")

    args = parser.parse_args()

    with open(args.csv, "r", encoding="utf8") as fh:
        reader = csv.DictReader(fh)
        digital_collection_metadata = [row for row in reader]

    # Initialize the record
    if args.avian:
        record = IslandoraRecord(digital_collection_metadata, avian=True)
    else:
        record = IslandoraRecord(digital_collection_metadata)

    with open(args.out, "wb") as fh:
        fh.write(record.as_marc())


if __name__ == "__main__":
    main()
