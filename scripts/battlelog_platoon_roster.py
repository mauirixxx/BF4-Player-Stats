#!/usr/bin/env python3
"""Read-only parser for official BF4 Battlelog platoon members HTML."""
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

PLATFORMS = {1: "pc", 2: "xbox360", 4: "ps3", 32: "ps4", 64: "xboxone"}
FAMILIES = {"pc": "pc", "xbox360": "xbox", "xboxone": "xbox",
            "ps3": "playstation", "ps4": "playstation"}
GAME_BF4 = 2048


def embedded_object(source, name):
    marker = '"' + name + '":'
    start = source.find(marker)
    if start < 0:
        raise ValueError("Missing Battlelog field: " + name)
    return json.JSONDecoder().raw_decode(source[start + len(marker):])[0]


class Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards = {}
        self.current = None
        self.depth = 0
        self.tooltip = None
        self.game = None
        self.platform = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get("class", "").split())
        if tag == "div" and "club-member" in classes and "expanded" in classes:
            if self.current is not None:
                raise ValueError("Nested member cards")
            self.current = {"account_id": None, "account_name": None, "personas": []}
            self.depth = 1
        elif self.current is not None:
            if tag == "div":
                self.depth += 1
            if tag == "a" and "avatar" in classes and a.get("rel"):
                self.current["account_id"] = a["rel"]
            if tag == "a" and "base-profile-link" in classes:
                self.current["capture_name"] = True
            if tag == "span" and "data-tooltip" in a:
                self.tooltip = a["data-tooltip"]
                self.game = None
                self.platform = None
            if tag == "i" and "icon-game" in classes:
                self.game = next((x for x in ("bf4", "bfh") if x in classes), None)
            if tag == "i" and "icon-platform-big" in classes:
                self.platform = next((x for x in FAMILIES if x in classes), None)
                if self.tooltip and self.game and self.platform:
                    self.current["personas"].append((self.tooltip, self.game, self.platform))

    def handle_data(self, data):
        if self.current is not None and self.current.get("capture_name"):
            self.current["account_name"] = (self.current["account_name"] or "") + data

    def handle_endtag(self, tag):
        if self.current is None:
            return
        if tag == "a":
            self.current.pop("capture_name", None)
        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                uid = self.current["account_id"]
                if not uid or uid in self.cards:
                    raise ValueError("Invalid/duplicate HTML account ID")
                self.cards[uid] = self.current
                self.current = None
                self.tooltip = None


def parse(source):
    club = embedded_object(source, "club")
    boxes = embedded_object(source, "personaBoxes")
    cards = Cards()
    cards.feed(source)
    if not isinstance(club, dict) or not isinstance(boxes, dict):
        raise ValueError("Unexpected Battlelog JSON structure")
    members = [(role, m) for role in ("founders", "leaders", "members")
               for m in club.get(role, [])]
    ids = [str(m["userId"]) for _, m in members]
    if len(ids) != len(set(ids)) or not set(boxes).issubset(set(ids)) or set(ids) != set(cards.cards):
        raise ValueError("Roster, personaBoxes and HTML card account IDs do not reconcile")
    if len(ids) != int(club["memberCount"]):
        raise ValueError("Official member count does not match full roster")
    result = []
    platform_conflicts = []
    for role, m in members:
        uid = str(m["userId"])
        card = cards.cards[uid]
        name = (m["user"].get("username") or (card["account_name"] or "").strip()) or None
        if name == "None":
            name = None
        personas = []
        if uid not in boxes and card["personas"]:
            raise ValueError("Missing personaBoxes for account with HTML persona evidence: " + uid)
        for p in boxes.get(uid, []):
            if p["game"] != GAME_BF4:
                continue
            code = int(p["platform"])
            if code not in PLATFORMS:
                raise ValueError("Unknown BF4 platform code: " + str(code))
            platform = PLATFORMS[code]
            # A card can have duplicate labels; require at least one exact match.
            if (p["personaName"], "bf4", platform) not in card["personas"]:
                platform_conflicts.append((uid, p["personaId"], platform))
            personas.append({"persona_id": str(p["personaId"]),
                             "persona_name": p["personaName"],
                             "battlelog_platform_code": code,
                             "battlelog_platform": platform,
                             "platform_family": FAMILIES[platform]})
        result.append({"battlelog_account_id": uid, "account_name": name,
                       "account_name_status": "available" if name else "unavailable",
                       "role": role[:-1] if role != "members" else "member",
                       "joined_at": datetime.fromtimestamp(m["joinedDate"], timezone.utc).isoformat(),
                       "bf4_personas": personas})
    if platform_conflicts:
        raise ValueError("HTML/JSON platform evidence mismatch: " + repr(platform_conflicts[:5]))
    return {"platoon": {"platoon_id": str(club["id"]), "name": club["name"],
                         "tag": club["tag"], "official_member_count": int(club["memberCount"]),
                         "created_at": datetime.fromtimestamp(club["created"], timezone.utc).isoformat(),
                         "emblem_path": club.get("emblemPath"), "website_url": club.get("webSite")},
            "accounts": result, "validation": {
                "account_count": len(result),
                "role_counts": dict(Counter(x["role"] for x in result)),
                "bf4_platform_records": sum(len(x["bf4_personas"]) for x in result),
                "distinct_bf4_persona_ids": len({p["persona_id"] for x in result for p in x["bf4_personas"]}),
                "missing_account_names": sum(x["account_name"] is None for x in result),
                "complete": True}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("html_file", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = parse(args.html_file.read_text(encoding="utf-8"))
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["validation"], indent=2))


if __name__ == "__main__":
    main()
