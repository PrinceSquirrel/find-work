import struct
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGO_ROOT = PROJECT_ROOT / "outputs" / "squirrel-world-logo-20260903"
SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"


def png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", payload[16:24])


def test_final_logo_svg_is_editable_and_named_for_the_project() -> None:
    svg_path = LOGO_ROOT / "squirrel-world-logo-v2.svg"
    root = ET.parse(svg_path).getroot()

    assert root.attrib["viewBox"] == "0 0 1174 1340"
    assert root.find(f".//{SVG_NAMESPACE}image") is None
    assert root.find(".//*[@id='emblem-vector-layer']") is not None
    assert root.find(".//*[@id='wordmark-layer']") is not None
    assert root.find(".//*[@id='brand-name']").text == "松鼠世界"
    assert len(root.findall(f".//{SVG_NAMESPACE}path")) > 100


def test_final_logo_png_exports_match_the_vector_canvas() -> None:
    assert png_dimensions(LOGO_ROOT / "squirrel-world-logo-v2.png") == (1174, 1340)
    assert png_dimensions(LOGO_ROOT / "squirrel-world-logo-v2-512.png") == (512, 584)
