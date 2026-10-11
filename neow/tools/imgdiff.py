"""Screenshot diff: pixel-level before/after comparison for UI changes."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops


class ImageDiffError(Exception):
    """Screenshot diff could not be produced."""


@dataclass
class ImageDiffResult:
    out_path: str
    changed: bool
    size: tuple  # (width, height) of the (possibly padded) comparison canvas


def _pad_to(image: Image.Image, width: int, height: int) -> Image.Image:
    """Top-left-align *image* on a white canvas of width x height."""
    if image.size == (width, height):
        return image
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    canvas.paste(image, (0, 0))
    return canvas


def diff_images(
    before_path: str, after_path: str, out_path: str, threshold: int = 30
) -> ImageDiffResult:
    """Highlight pixels that differ between *before_path* and *after_path* in red.

    Images of different sizes are top-left-aligned on a shared white canvas
    (the bigger of each dimension) rather than rejected, since UI screenshots
    routinely change size across a change.

    Args:
        before_path: Path to the "before" screenshot.
        after_path: Path to the "after" screenshot.
        out_path: Where to write the diff image (PNG recommended).
        threshold: Per-channel absolute difference (0-255) to count as changed.

    Returns:
        ImageDiffResult with whether anything changed and the diff image path.

    Raises:
        ImageDiffError: Either input file is missing or unreadable as an image.
    """
    try:
        before = Image.open(before_path).convert("RGB")
        after = Image.open(after_path).convert("RGB")
    except (FileNotFoundError, OSError) as exc:
        raise ImageDiffError(str(exc)) from exc

    width = max(before.width, after.width)
    height = max(before.height, after.height)
    before = _pad_to(before, width, height)
    after = _pad_to(after, width, height)

    diff = ImageChops.difference(before, after).convert("L")
    mask = diff.point(lambda p: 255 if p > threshold else 0)
    changed = mask.getbbox() is not None

    highlight = Image.new("RGB", (width, height), (255, 0, 0))
    result = Image.composite(highlight, after, mask)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(out_path)
    return ImageDiffResult(
        out_path=str(out_path), changed=changed, size=(width, height)
    )
