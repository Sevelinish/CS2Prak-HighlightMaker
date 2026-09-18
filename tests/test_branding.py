from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from branding.dib import DibWriter
from branding.icon import IconBuilder, IconWriter
from branding.png import PngWriter
from branding.raster import Bitmap, Rasterizer
from branding.svg import Drawing, PathParser, Shape, SvgReader, UnsupportedPathError

GREEN = (44, 139, 47)
NAVY = (4, 30, 53)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SQUARE = "M 0,0 L 100,0 L 100,100 L 0,100 Z"
HOLE = "M 25,25 L 75,25 L 75,75 L 25,75 Z"


def write_svg(root: Path, body: str) -> Path:
    path = root / "logo.svg"
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        f"{body}</svg>",
        encoding="utf-8",
    )
    return path


def square_drawing(body: str = SQUARE, color: tuple[int, int, int] = GREEN) -> Drawing:
    return Drawing(shapes=(Shape(contours=PathParser().parse(body), color=color),))


def test_a_closed_path_becomes_one_contour():
    contours = PathParser().parse(SQUARE)

    assert len(contours) == 1
    assert contours[0] == ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))


def test_two_closed_paths_become_two_contours():
    assert len(PathParser().parse(f"{SQUARE} {HOLE}")) == 2


def test_coordinates_after_a_move_are_treated_as_lines():
    contours = PathParser().parse("M 0,0 10,0 10,10 Z")

    assert contours[0] == ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0))


def test_relative_commands_walk_from_the_cursor():
    contours = PathParser().parse("M 10,10 l 10,0 l 0,10 z")

    assert contours[0] == ((10.0, 10.0), (20.0, 10.0), (20.0, 20.0))


def test_horizontal_and_vertical_commands_keep_the_other_axis():
    contours = PathParser().parse("M 5,5 H 15 V 25 Z")

    assert contours[0] == ((5.0, 5.0), (15.0, 5.0), (15.0, 25.0))


def test_a_curve_is_refused_by_name():
    with pytest.raises(UnsupportedPathError) as error:
        PathParser().parse("M 0,0 C 1,1 2,2 3,3 Z")

    assert "'C'" in str(error.value)


def test_a_stray_point_is_not_a_contour():
    assert PathParser().parse("M 0,0 L 1,1 Z") == ()


def test_the_reader_keeps_the_fill_of_every_path(tmp_path: Path):
    source = write_svg(
        tmp_path,
        f'<path d="{SQUARE}" fill="#2C8B2F"/><path d="{HOLE}" fill="#041E35"/>',
    )

    drawing = SvgReader().read(source)

    assert [shape.color for shape in drawing.shapes] == [GREEN, NAVY]


def test_a_short_colour_is_expanded(tmp_path: Path):
    source = write_svg(tmp_path, f'<path d="{SQUARE}" fill="#0f0"/>')

    assert SvgReader().read(source).shapes[0].color == (0, 255, 0)


def test_the_bounds_come_from_the_drawing_not_the_canvas(tmp_path: Path):
    source = write_svg(tmp_path, f'<path d="{HOLE}" fill="#2C8B2F"/>')

    bounds = SvgReader().read(source).bounds

    assert (bounds.left, bounds.top, bounds.right, bounds.bottom) == (25.0, 25.0, 75.0, 75.0)


def test_an_svg_without_paths_is_refused(tmp_path: Path):
    source = write_svg(tmp_path, "<rect width='10' height='10'/>")

    with pytest.raises(UnsupportedPathError):
        SvgReader().read(source)


def test_broken_xml_is_refused(tmp_path: Path):
    source = tmp_path / "logo.svg"
    source.write_text("<svg><path", encoding="utf-8")

    with pytest.raises(UnsupportedPathError):
        SvgReader().read(source)


def test_a_filled_square_is_opaque_in_the_middle():
    bitmap = Rasterizer().render(square_drawing(), 64)

    assert bitmap.pixel(32, 32) == (*GREEN, 255)


def test_nothing_is_painted_outside_the_shape():
    bitmap = Rasterizer().render(square_drawing(), 64)

    assert bitmap.pixel(0, 0) == (0, 0, 0, 0)


def test_an_inner_contour_is_cut_out():
    bitmap = Rasterizer().render(square_drawing(f"{SQUARE} {HOLE}"), 64)

    assert bitmap.pixel(32, 32)[3] == 0
    assert bitmap.pixel(32, 6)[3] == 255


def test_a_shape_painted_later_covers_the_one_before():
    drawing = Drawing(
        shapes=(
            Shape(contours=PathParser().parse(SQUARE), color=GREEN),
            Shape(contours=PathParser().parse(HOLE), color=NAVY),
        )
    )

    assert Rasterizer().render(drawing, 64).pixel(32, 32) == (*NAVY, 255)


def test_the_drawing_is_centred_in_a_square_canvas():
    tall = square_drawing("M 0,0 L 20,0 L 20,100 L 0,100 Z")

    bitmap = Rasterizer().render(tall, 64)

    assert bitmap.pixel(4, 32)[3] == 0
    assert bitmap.pixel(32, 32)[3] == 255


def test_resizing_averages_the_pixels():
    pixels = bytearray()
    for index in range(4):
        pixels += bytes((0, 0, 0, 0)) if index % 2 else bytes((*GREEN, 255))
    bitmap = Bitmap(width=2, height=2, pixels=bytes(pixels))

    assert bitmap.resized(1).pixel(0, 0) == (*GREEN, 128)


def test_resizing_to_the_same_size_changes_nothing():
    bitmap = Rasterizer().render(square_drawing(), 32)

    assert bitmap.resized(32) is bitmap


def test_the_png_says_what_it_holds():
    bitmap = Rasterizer().render(square_drawing(), 16)

    encoded = PngWriter.encode(bitmap)
    width, height, depth, colors = struct.unpack(">IIBB", encoded[16:26])

    assert encoded[:8] == PNG_SIGNATURE
    assert (width, height, depth, colors) == (16, 16, 8, 6)


def test_the_png_carries_the_pixels_back():
    bitmap = Rasterizer().render(square_drawing(), 8)
    encoded = PngWriter.encode(bitmap)

    length = struct.unpack(">I", encoded[33:37])[0]
    raw = zlib.decompress(encoded[41 : 41 + length])
    rows = [raw[index * 33 + 1 : (index + 1) * 33] for index in range(8)]

    assert b"".join(rows) == bitmap.pixels


def test_the_dib_doubles_its_height_for_the_mask():
    bitmap = Rasterizer().render(square_drawing(), 16)

    header = struct.unpack("<Iii", DibWriter.encode(bitmap)[:12])

    assert header == (40, 16, 32)


def test_the_dib_is_stored_bottom_up_in_blue_green_red_order():
    bitmap = Rasterizer().render(square_drawing(), 16)
    encoded = DibWriter.encode(bitmap)

    bottom_left = encoded[40:44]

    assert tuple(bottom_left) == (*reversed(bitmap.pixel(0, 15)[:3]), bitmap.pixel(0, 15)[3])


def test_the_icon_holds_every_size():
    master = Rasterizer().render(square_drawing(), 256)

    encoded = IconWriter().encode(master)
    reserved, kind, count = struct.unpack("<HHH", encoded[:6])

    assert (reserved, kind) == (0, 1)
    assert count == 7


def test_every_icon_entry_points_at_its_own_bytes():
    master = Rasterizer().render(square_drawing(), 256)
    encoded = IconWriter().encode(master)
    count = struct.unpack("<H", encoded[4:6])[0]

    reach = 6 + 16 * count
    for index in range(count):
        entry = encoded[6 + index * 16 : 6 + (index + 1) * 16]
        size, offset = struct.unpack("<II", entry[8:16])
        assert offset == reach
        reach += size

    assert reach == len(encoded)


def test_small_sizes_are_bitmaps_and_large_ones_are_compressed():
    master = Rasterizer().render(square_drawing(), 256)
    encoded = IconWriter().encode(master)

    shapes = {}
    for index in range(struct.unpack("<H", encoded[4:6])[0]):
        entry = encoded[6 + index * 16 : 6 + (index + 1) * 16]
        size, offset = struct.unpack("<II", entry[8:16])
        declared = entry[0] or 256
        shapes[declared] = encoded[offset : offset + 8] == PNG_SIGNATURE

    assert shapes == {
        16: False,
        24: False,
        32: False,
        48: False,
        64: False,
        128: True,
        256: True,
    }


def test_the_largest_entry_declares_itself_as_zero():
    master = Rasterizer().render(square_drawing(), 256)
    encoded = IconWriter().encode(master)
    count = struct.unpack("<H", encoded[4:6])[0]
    last = encoded[6 + (count - 1) * 16 : 6 + count * 16]

    assert (last[0], last[1]) == (0, 0)


def test_the_project_logo_becomes_an_icon_file(tmp_path: Path):
    logo = Path(__file__).resolve().parents[1] / "logo.svg"
    if not logo.is_file():
        pytest.skip("the project has no logo.svg")

    written = IconBuilder().build(logo, tmp_path / "icon.ico")

    assert written.is_file()
    assert struct.unpack("<HHH", written.read_bytes()[:6]) == (0, 1, 7)
