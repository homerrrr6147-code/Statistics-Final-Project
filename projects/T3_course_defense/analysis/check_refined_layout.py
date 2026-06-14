import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}

with zipfile.ZipFile(sys.argv[1]) as zf:
    slides = sorted(
        [n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)],
        key=lambda n: int(re.search(r"(\d+)", n).group()),
    )
    report = []
    for index in [4, 5, 8, 9, 10, 12, 13]:
        root = ET.fromstring(zf.read(slides[index - 1]))
        items = []
        for shape in root.findall(".//p:sp", NS):
            text = "".join(node.text or "" for node in shape.findall(".//a:t", NS)).strip()
            xfrm = shape.find("p:spPr/a:xfrm", NS)
            if xfrm is None:
                continue
            off = xfrm.find("a:off", NS)
            ext = xfrm.find("a:ext", NS)
            if off is None or ext is None:
                continue
            x, y = int(off.get("x")) / 9525, int(off.get("y")) / 9525
            w, h = int(ext.get("cx")) / 9525, int(ext.get("cy")) / 9525
            if text and (x < -1 or y < -1 or x + w > 1281 or y + h > 721):
                items.append({"text": text[:60], "x": x, "y": y, "w": w, "h": h})
        report.append({"slide": index, "out_of_bounds_text_shapes": items})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if any(item["out_of_bounds_text_shapes"] for item in report):
        raise SystemExit(1)
