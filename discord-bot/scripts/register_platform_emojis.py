"""One-time registration of platform-colored plus application emojis.

Run in a container with DISCORD_BOT_TOKEN. Prints public emoji IDs only.
No secret values are logged or persisted.
"""
import base64
import io
import json
import os
import urllib.error
import urllib.request

from PIL import Image, ImageDraw

COLORS = {"pc": "#ED8B31", "xbox": "#26B64B", "playstation": "#4287EF"}
API = "https://discord.com/api/v10"


def request(method, path, payload=None):
    token = os.environ["DISCORD_BOT_TOKEN"]
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": "Bot " + token, "User-Agent": "BF4PS-Discord (https://github.com/mauirixxx/BF4-Player-Stats)"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def png_plus(color):
    im = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Wide rounded cross, readable even at Discord's 20-pixel emoji size.
    d.rounded_rectangle((51, 13, 77, 115), radius=7, fill=color)
    d.rounded_rectangle((13, 51, 115, 77), radius=7, fill=color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def main():
    app = request("GET", "/oauth2/applications/@me")
    app_id = app["id"]
    path = f"/applications/{app_id}/emojis"
    existing = {e["name"]: e["id"] for e in request("GET", path).get("items", [])}
    for platform, color in COLORS.items():
        name = "bf4ps_plus_" + platform
        if name in existing:
            emoji_id = existing[name]
        else:
            emoji = request("POST", path, {"name": name, "image": png_plus(color)})
            emoji_id = emoji["id"]
        print(platform, name, emoji_id)


if __name__ == "__main__":
    main()
