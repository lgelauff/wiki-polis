import struct
import zlib

from parity.visual import raster_equivalent


def _write_rgb_png(path, *, width=10, height=10, changes=None):
    changes = changes or {}
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            row.extend(changes.get((x, y), (240, 240, 240)))
        rows.append(b'\x00' + bytes(row))

    def chunk(kind, payload):
        return (
            struct.pack('>I', len(payload))
            + kind
            + payload
            + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
        )

    path.write_bytes(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(b''.join(rows)))
        + chunk(b'IEND', b'')
    )


def test_raster_equivalence_accepts_one_bounded_antialias_pixel(tmp_path):
    expected = tmp_path / 'expected.png'
    actual = tmp_path / 'actual.png'
    _write_rgb_png(expected)
    _write_rgb_png(actual, changes={(2, 3): (230, 235, 240)})

    assert raster_equivalent(expected, actual) == (True, 1, 10)


def test_raster_equivalence_rejects_visible_color_change(tmp_path):
    expected = tmp_path / 'expected.png'
    actual = tmp_path / 'actual.png'
    _write_rgb_png(expected)
    _write_rgb_png(actual, changes={(2, 3): (0, 0, 0)})

    assert raster_equivalent(expected, actual) == (False, 1, 240)


def test_raster_equivalence_rejects_changed_geometry(tmp_path):
    expected = tmp_path / 'expected.png'
    actual = tmp_path / 'actual.png'
    _write_rgb_png(expected)
    _write_rgb_png(actual, width=11)

    equivalent, _, max_delta = raster_equivalent(expected, actual)
    assert equivalent is False
    assert max_delta == 255
