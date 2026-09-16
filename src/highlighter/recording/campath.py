from __future__ import annotations

from xml.etree import ElementTree

from ..domain.chase import ChasePath

ROOT_ELEMENT = "campath"
POINTS_ELEMENT = "points"
KEYFRAME_ELEMENT = "p"
POSITION_INTERPOLATION = "cubic"
ROTATION_INTERPOLATION = "sCubic"
FOV_INTERPOLATION = "cubic"
NO_ROLL = "0"
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'


class CampathDocument:
    @classmethod
    def render(cls, path: ChasePath) -> str:
        root = ElementTree.Element(
            ROOT_ELEMENT,
            {
                "positionInterp": POSITION_INTERPOLATION,
                "rotationInterp": ROTATION_INTERPOLATION,
                "fovInterp": FOV_INTERPOLATION,
                "hold": "true",
            },
        )
        points = ElementTree.SubElement(root, POINTS_ELEMENT)

        for keyframe in path.keyframes:
            placement = keyframe.placement
            ElementTree.SubElement(
                points,
                KEYFRAME_ELEMENT,
                {
                    "t": cls._number(keyframe.seconds),
                    "x": cls._number(placement.position.x),
                    "y": cls._number(placement.position.y),
                    "z": cls._number(placement.position.z),
                    "rx": NO_ROLL,
                    "ry": cls._number(placement.angles.pitch),
                    "rz": cls._number(placement.angles.yaw),
                    "fov": cls._number(keyframe.fov),
                },
            )

        body = ElementTree.tostring(root, encoding="unicode")
        return f"{XML_DECLARATION}\n{body}\n"

    @staticmethod
    def _number(value: float) -> str:
        return f"{value:.4f}"
