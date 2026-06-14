import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}

deck = sys.argv[1]
with zipfile.ZipFile(deck) as zf:
    slides = sorted(
        [n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)],
        key=lambda x: int(re.search(r"(\d+)", x).group()),
    )
    for index in [4, 5, 8, 9, 10, 12, 13]:
        root = ET.fromstring(zf.read(slides[index - 1]))
        print(f"\n### {index} {slides[index - 1]}")
        for shape in root.findall(".//p:sp", NS):
            nv = shape.find("p:nvSpPr/p:cNvPr", NS)
            sid = nv.get("id") if nv is not None else "?"
            name = nv.get("name") if nv is not None else ""
            text = "".join((node.text or "") for node in shape.findall(".//a:t", NS))
            xfrm = shape.find("p:spPr/a:xfrm", NS)
            geometry = ""
            if xfrm is not None:
                off = xfrm.find("a:off", NS)
                ext = xfrm.find("a:ext", NS)
                if off is not None and ext is not None:
                    geometry = (
                        f"x={int(off.get('x')) // 9525},y={int(off.get('y')) // 9525},"
                        f"w={int(ext.get('cx')) // 9525},h={int(ext.get('cy')) // 9525}"
                    )
            if text:
                print(sid, name, geometry, repr(text))
