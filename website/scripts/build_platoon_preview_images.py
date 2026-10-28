#!/usr/bin/env python3
"""Build deterministic 1200x630 Discord cards for locally cached platoon emblems."""
import argparse
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

ROOT = Path('/var/www/bf4playerstats.com')

def render(source, dest):
    try:
        with Image.open(source) as raw:
            raw.load()
            if raw.format != 'PNG' or raw.width > 2048 or raw.height > 2048:
                return False
            emblem = raw.convert('RGBA')
    except (OSError, UnidentifiedImageError, ValueError):
        return False
    image = Image.new('RGB', (1200, 630), '#101b29')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1199, 9), fill='#f4a62a')
    draw.rounded_rectangle((42, 49, 1158, 578), radius=24, fill='#203247')
    draw.rounded_rectangle((55, 62, 615, 565), radius=20, fill='#142333')
    emblem.thumbnail((495, 495), Image.Resampling.LANCZOS)
    image.paste(emblem, (335 - emblem.width // 2, 315 - emblem.height // 2), emblem)
    regular='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    draw.text((654, 194), 'BATTLEFIELD 4', font=ImageFont.truetype(bold, 38), fill='#f4a62a')
    draw.text((654, 260), 'PLATOON', font=ImageFont.truetype(bold, 62), fill='#ffffff')
    draw.text((654, 338), 'STATS', font=ImageFont.truetype(bold, 62), fill='#ffffff')
    draw.text((655, 453), 'BF4PLAYERSTATS.COM', font=ImageFont.truetype(regular, 25), fill='#f4a62a')
    temp=dest.with_name('.'+dest.name+'.tmp.png')
    try:
        image.save(temp, 'PNG', optimize=True)
        os.chmod(temp, 0o644)
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--limit',type=int,default=50)
    ap.add_argument('--root',type=Path,default=ROOT)
    args=ap.parse_args()
    if not 1 <= args.limit <= 200: ap.error('limit must be 1..200')
    source_dir=args.root/'assets/platoon-emblems'
    dest_dir=args.root/'assets/platoon-previews'
    dest_dir.mkdir(parents=True,exist_ok=True)
    created=0
    for source in sorted(source_dir.glob('*.png')):
        if not source.name[:1].isdigit() or not source.stem.rsplit('-',1)[-1].isalnum():continue
        dest=dest_dir/(source.stem + '-v2.png')
        if dest.exists():continue
        if render(source,dest):created+=1
        if created>=args.limit:break
    print('created',created,'platoon preview cards',flush=True)

if __name__=='__main__':main()
