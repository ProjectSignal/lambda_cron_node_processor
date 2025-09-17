import unittest
from copy import deepcopy

from bs.parseHtmlForDescription import has_significant_changes


class HasSignificantChangesTests(unittest.TestCase):
    def setUp(self):
        self.existing_node = {
            "descriptionGenerated": True,
            "about": "Experienced product manager building B2B SaaS platforms.",
            "bio": "Product Lead @ Brace",
            "linkedinHeadline": "Product Lead at Brace",
            "workExperience": [],
            "education": [],
            "currentLocation": "San Francisco Bay Area",
        }

        self.new_profile = deepcopy(self.existing_node)
        # new_profile mirrors the latest scrape payload structure
        self.new_profile["_id"] = "abc123"
        self.new_profile["userId"] = "user123"

    def test_about_change_triggers_detection(self):
        profile = deepcopy(self.new_profile)
        profile["about"] = "Experienced product manager building SaaS platforms."

        has_changes, fields = has_significant_changes(profile, self.existing_node)

        self.assertTrue(has_changes)
        self.assertIn("about", fields)

    def test_about_whitespace_is_ignored(self):
        profile = deepcopy(self.new_profile)
        profile["about"] = "Experienced product manager  building  B2B  SaaS platforms.\n"

        has_changes, fields = has_significant_changes(profile, self.existing_node)

        self.assertFalse(has_changes)
        self.assertEqual(fields, [])

    def test_headline_change_triggers_detection(self):
        profile = deepcopy(self.new_profile)
        profile["linkedinHeadline"] = "Director of Product at Brace"

        has_changes, fields = has_significant_changes(profile, self.existing_node)

        self.assertTrue(has_changes)
        self.assertIn("linkedinHeadline", fields)


if __name__ == "__main__":
    unittest.main()
