"""Minimal import shim for ppt-master's OOXML template-fill workflow.

The template-fill code does not instantiate python-pptx objects, but an unrelated
SVG export module imports these names during package initialization.
"""


class Presentation:  # pragma: no cover - must never be instantiated here
    def __init__(self, *args, **kwargs):
        raise RuntimeError("python-pptx is unavailable; template-fill must use OOXML only")
