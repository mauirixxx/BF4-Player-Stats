import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from battlelog_platoon_roster import parse

def fixture():
    club = {"id": "754443074295858477", "name": "Team Wired", "tag": "Wire",
            "created": 1408320344, "memberCount": 2,
            "founders": [{"userId": "100", "joinedDate": 1408324513, "user": {"username": "Alice"}}],
            "leaders": [], "members": [{"userId": "200", "joinedDate": 1408324513, "user": {"username": None}}]}
    boxes = {"100": [{"platform": 64, "game": 2048, "personaId": "55", "personaName": "Ace"},
                     {"platform": 2, "game": 2048, "personaId": "55", "personaName": "Ace"}],
             "200": [{"platform": 1, "game": 2048, "personaId": "77", "personaName": "PCGuy"}]}
    cards = """<div class="club-member expanded"><a class="avatar" rel="100"></a><a class="base-profile-link">Alice</a>
    <span data-tooltip="Ace"><i class="icon-game bright bf4"></i><i class="icon-platform-big xboxone"></i></span>
    <span data-tooltip="Ace"><i class="icon-game bright bf4"></i><i class="icon-platform-big xbox360"></i></span></div>
    <div class="club-member expanded"><a class="avatar" rel="200"></a><a class="base-profile-link">None</a>
    <span data-tooltip="PCGuy"><i class="icon-game bright bf4"></i><i class="icon-platform-big pc"></i></span></div>"""
    return '<script>var data={"club":' + json.dumps(club) + ',"personaBoxes":' + json.dumps(boxes) + '};</script>' + cards

class TestRoster(unittest.TestCase):
    def test_valid(self):
        r = parse(fixture())
        self.assertEqual(r["validation"]["account_count"], 2)
        self.assertEqual(r["validation"]["bf4_platform_records"], 3)
        self.assertEqual(r["validation"]["distinct_bf4_persona_ids"], 2)
        self.assertEqual(r["validation"]["missing_account_names"], 1)
    def test_incomplete(self):
        with self.assertRaisesRegex(ValueError, "member count"):
            parse(fixture().replace('"memberCount": 2', '"memberCount": 3'))
    def test_platform_mismatch(self):
        with self.assertRaisesRegex(ValueError, "platform evidence mismatch"):
            parse(fixture().replace("icon-platform-big xbox360", "icon-platform-big ps3"))
    def test_unknown_platform(self):
        with self.assertRaisesRegex(ValueError, "Unknown BF4 platform"):
            parse(fixture().replace('"platform": 1', '"platform": 128'))

if __name__ == "__main__":
    unittest.main()
