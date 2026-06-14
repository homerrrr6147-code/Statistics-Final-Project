from __future__ import annotations

import io
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def natural_key(value: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", value)]


def main() -> None:
    deck = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    report = []
    thumbs = []

    with zipfile.ZipFile(deck) as zf:
        media = sorted([n for n in zf.namelist() if n.startswith("ppt/media/")], key=natural_key)
        for name in media:
            try:
                image = Image.open(io.BytesIO(zf.read(name))).convert("RGB")
                image.thumbnail((240, 150))
                tile = Image.new("RGB", (260, 190), "white")
                tile.paste(image, ((260 - image.width) // 2, 8))
                ImageDraw.Draw(tile).text((8, 165), Path(name).name, fill="black")
                thumbs.append(tile)
                image.save(out / Path(name).name)
            except Exception:
                continue

        slide_paths = sorted(
            [n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)],
            key=natural_key,
        )
        for index, slide_path in enumerate(slide_paths, start=1):
            slide_file = posixpath.basename(slide_path)
            rel_path = f"ppt/slides/_rels/{slide_file}.rels"
            slide = ET.fromstring(zf.read(slide_path))
            rels = ET.fromstring(zf.read(rel_path))
            rel_map = {
                rel.attrib["Id"]: posixpath.normpath(posixpath.join("ppt/slides", rel.attrib["Target"]))
                for rel in rels.findall("pr:Relationship", NS)
            }
            images = []
            for pic in slide.findall(".//p:pic", NS):
                blip = pic.find(".//a:blip", NS)
                xfrm = pic.find(".//a:xfrm", NS)
                if blip is None:
                    continue
                rid = blip.attrib.get(f"{{{NS['r']}}}embed")
                off = xfrm.find("a:off", NS) if xfrm is not None else None
                ext = xfrm.find("a:ext", NS) if xfrm is not None else None
                images.append({
                    "relationship": rid,
                    "target": rel_map.get(rid),
                    "x": int(off.attrib.get("x", 0)) if off is not None else None,
                    "y": int(off.attrib.get("y", 0)) if off is not None else None,
                    "cx": int(ext.attrib.get("cx", 0)) if ext is not None else None,
                    "cy": int(ext.attrib.get("cy", 0)) if ext is not None else None,
                })
            report.append({"slide": index, "images": images})

    if thumbs:
        cols = 3
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 260, rows * 190), "#dddddd")
        for i, thumb in enumerate(thumbs):
            sheet.paste(thumb, ((i % cols) * 260, (i // cols) * 190))
        sheet.save(out / "media_contact_sheet.png")

    (out / "image_usage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
