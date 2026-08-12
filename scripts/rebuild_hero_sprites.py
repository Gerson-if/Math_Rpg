"""
Regenerates the hero sprite strips (app/static/images/characters/hero/*.png)
straight from their .aseprite sources.

Why this exists: Aseprite's sprite-sheet PNG export trims each frame to its
own content bounding box by default, so exported frames end up different
widths. The previous idle-spritesheet.png was read by CSS as if it were a
uniform grid (fixed frame width, steps(N)) — since the frames weren't
actually uniform, the animation looked like it was sliding/smearing between
poses instead of snapping cleanly frame to frame. This script reads each
frame's authoritative (x, y, width, height) cel placement plus the file's
own canvas size directly from the .aseprite chunks, and repaints every
frame onto a canvas-sized tile — so the output strip is a real uniform grid
that a simple steps() animation can index into safely.

Usage (needs Pillow — a tooling dependency, not in requirements.txt since
the running app never imports it: pip install pillow):
    python scripts/rebuild_hero_sprites.py
"""
import os
import struct
import sys
import zlib

from PIL import Image

HERO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "images", "characters", "hero",
)
SOURCES = ["idle.aseprite", "walk.aseprite"]


def _read_header(f):
    data = f.read(128)
    frames, width, height, color_depth = struct.unpack_from("<HHHH", data, 6)
    return {"frames": frames, "width": width, "height": height, "color_depth": color_depth}


def _read_frames(f, header):
    if header["color_depth"] != 32:
        raise ValueError("only RGBA (32-bit) Aseprite sprites are supported")

    frames = []
    for _ in range(header["frames"]):
        frame_start = f.tell()
        frame_header = f.read(16)
        bytes_in_frame, _magic, old_chunks, duration, _res, new_chunks = struct.unpack_from(
            "<IHHHHI", frame_header, 0
        )
        n_chunks = new_chunks if new_chunks != 0 else old_chunks

        cel = None
        for _ in range(n_chunks):
            chunk_start = f.tell()
            chunk_size, chunk_type = struct.unpack_from("<IH", f.read(6), 0)
            chunk_data = f.read(chunk_size - 6)
            if chunk_type == 0x2005:  # Cel Chunk
                _layer, x, y, _opacity, cel_type, _z = struct.unpack_from("<HhhBHh", chunk_data, 0)
                offset = 2 + 2 + 2 + 1 + 2 + 2 + 5  # fixed cel header fields + reserved bytes
                if cel_type == 2:  # compressed image
                    w, h = struct.unpack_from("<HH", chunk_data, offset)
                    pixels = zlib.decompress(chunk_data[offset + 4:])
                    cel = {"x": x, "y": y, "w": w, "h": h, "pixels": pixels}
                elif cel_type == 0:  # raw image
                    w, h = struct.unpack_from("<HH", chunk_data, offset)
                    pixels = chunk_data[offset + 4: offset + 4 + w * h * 4]
                    cel = {"x": x, "y": y, "w": w, "h": h, "pixels": pixels}
            f.seek(chunk_start + chunk_size)

        frames.append({"duration_ms": duration, "cel": cel})
        f.seek(frame_start + bytes_in_frame)
    return frames


def build_strip(ase_path: str, out_path: str) -> None:
    with open(ase_path, "rb") as f:
        header = _read_header(f)
        frames = _read_frames(f, header)

    cw, ch = header["width"], header["height"]
    strip = Image.new("RGBA", (cw * len(frames), ch), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        tile = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        cel = frame["cel"]
        if cel is not None:
            cel_img = Image.frombytes("RGBA", (cel["w"], cel["h"]), cel["pixels"])
            tile.paste(cel_img, (cel["x"], cel["y"]), cel_img)
        strip.paste(tile, (i * cw, 0))

    strip.save(out_path)
    print(f"{os.path.basename(out_path)}: {strip.width}x{strip.height}, "
          f"{len(frames)} frames of {cw}x{ch}")


def main():
    for source in SOURCES:
        ase_path = os.path.join(HERO_DIR, source)
        if not os.path.exists(ase_path):
            print(f"skipping {source} (not found)")
            continue
        out_name = source.replace(".aseprite", "-spritesheet.png")
        build_strip(ase_path, os.path.join(HERO_DIR, out_name))


if __name__ == "__main__":
    main()
