"""Tests for the screenshot-diff tool (task 20)."""

import pytest
from PIL import Image

from neow.tools.imgdiff import ImageDiffError, diff_images


def _save(path, size=(10, 10), color=(255, 255, 255)):
    Image.new("RGB", size, color).save(path)
    return str(path)


def test_identical_images_have_no_diff(tmp_path):
    before = _save(tmp_path / "before.png")
    after = _save(tmp_path / "after.png")
    out = tmp_path / "diff.png"

    result = diff_images(before, after, str(out))

    assert result.changed is False
    assert out.exists()


def test_different_images_are_flagged_and_highlighted(tmp_path):
    before = _save(tmp_path / "before.png", color=(255, 255, 255))
    after = _save(tmp_path / "after.png", color=(0, 0, 0))
    out = tmp_path / "diff.png"

    result = diff_images(before, after, str(out))

    assert result.changed is True
    saved = Image.open(out)
    # The whole canvas differs, so it's painted in the highlight color.
    assert saved.getpixel((0, 0)) == (255, 0, 0)


def test_differently_sized_images_are_padded_not_rejected(tmp_path):
    """Different-sized inputs don't raise; they're aligned on a shared canvas."""
    before = _save(tmp_path / "before.png", size=(10, 10), color=(0, 0, 0))
    after = _save(tmp_path / "after.png", size=(20, 15), color=(0, 0, 0))
    out = tmp_path / "diff.png"

    result = diff_images(before, after, str(out))

    assert result.size == (20, 15)
    assert out.exists()
    assert Image.open(out).size == (20, 15)


def test_missing_file_raises_image_diff_error(tmp_path):
    after = _save(tmp_path / "after.png")

    with pytest.raises(ImageDiffError):
        diff_images(str(tmp_path / "nope.png"), after, str(tmp_path / "diff.png"))


def test_creates_output_parent_directory(tmp_path):
    before = _save(tmp_path / "before.png")
    after = _save(tmp_path / "after.png")
    out = tmp_path / "nested" / "dir" / "diff.png"

    diff_images(before, after, str(out))

    assert out.exists()
