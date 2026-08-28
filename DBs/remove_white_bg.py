"""
remove_white_bg.py
------------------
Removes white (and near-white) backgrounds from PNG logo files.
Run this from anywhere — just set LOGOS_DIR to your logos folder.

Usage:
    python remove_white_bg.py

Requires Pillow:
    pip install Pillow
"""

from PIL import Image
import os

# ── Config ────────────────────────────────────────────────────────────────────

# Path to your logos folder. The script processes both subfolders.
# Update this to match your machine, e.g.:
# Windows: r"C:\Users\tjsut\tracersports-app\public\logos"
LOGOS_DIR = r"C:\Users\tjsut\TRACERsports\public\logos"

# How close to white a pixel needs to be to get removed.
# 255 = only pure white. 230 = catches off-white/light grey too.
# Raise this if edges look jagged; lower it if too much color is removed.
THRESHOLD = 240

# The script now walks LOGOS_DIR recursively, so every PNG in every
# subfolder (and sub-subfolder, no matter how deeply nested) gets processed.
# No folder list to maintain anymore.

# ── Core function ─────────────────────────────────────────────────────────────

def remove_white_background(path, threshold=240):
    """
    Opens a PNG and removes white/near-white background using an edge-connected
    flood fill. Only pixels reachable from the image border are made transparent,
    so interior white (e.g. text inside a logo like the Rockets wordmark) is
    left completely untouched.
    Returns True if the file was modified, False if it was skipped.
    """
    img = Image.open(path).convert("RGBA")
    pixels = img.load()
    width, height = img.size

    def is_near_white(r, g, b, a):
        return a > 0 and r >= threshold and g >= threshold and b >= threshold

    # BFS flood fill starting from all four edges
    visited = set()
    queue = []

    for x in range(width):
        for y in [0, height - 1]:
            if (x, y) not in visited:
                r, g, b, a = pixels[x, y]
                if is_near_white(r, g, b, a):
                    queue.append((x, y))
                    visited.add((x, y))

    for y in range(height):
        for x in [0, width - 1]:
            if (x, y) not in visited:
                r, g, b, a = pixels[x, y]
                if is_near_white(r, g, b, a):
                    queue.append((x, y))
                    visited.add((x, y))

    # Expand outward to all connected near-white pixels
    while queue:
        x, y = queue.pop()
        for nx, ny in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)]:
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                r, g, b, a = pixels[nx, ny]
                if is_near_white(r, g, b, a):
                    visited.add((nx, ny))
                    queue.append((nx, ny))

    if not visited:
        return False  # nothing to remove

    # Make all flood-filled pixels transparent
    for x, y in visited:
        r, g, b, a = pixels[x, y]
        pixels[x, y] = (r, g, b, 0)

    img.save(path, "PNG")
    return True


# ── Runner ────────────────────────────────────────────────────────────────────

def process_folder(folder_path, threshold):
    """
    Recursively walks folder_path and processes every PNG found,
    no matter how deeply nested in subfolders.
    """
    modified = 0
    skipped = 0
    errors = 0

    for root, dirs, files in os.walk(folder_path):
        png_files = [f for f in files if f.lower().endswith(".png")]
        if not png_files:
            continue

        print(f"\n  {len(png_files)} PNG files found in {root}")

        for filename in sorted(png_files):
            filepath = os.path.join(root, filename)
            try:
                was_changed = remove_white_background(filepath, threshold)
                if was_changed:
                    print(f"    ✓ Fixed: {filename}")
                    modified += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"    ✗ Error on {filename}: {e}")
                errors += 1

    return modified, skipped, errors


def main():
    print(f"remove_white_bg.py — threshold: {THRESHOLD}")
    print(f"Logos directory: {LOGOS_DIR}")

    if not os.path.isdir(LOGOS_DIR):
        print(f"\nERROR: Directory not found: {LOGOS_DIR}")
        print("Update the LOGOS_DIR variable at the top of the script.")
        return

    total_modified, total_skipped, total_errors = process_folder(LOGOS_DIR, THRESHOLD)

    print(f"\n{'─'*40}")
    print(f"Done. Modified: {total_modified} | Already transparent: {total_skipped} | Errors: {total_errors}")
    print("All changes are in-place — originals overwritten.")


if __name__ == "__main__":
    main()
