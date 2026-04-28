"""Tests for album_builder.domain.slug — see docs/specs/02-album-lifecycle.md
test contract for TC IDs."""

from pathlib import Path

from album_builder.domain.slug import slugify, unique_slug


# Spec: TC-02-04
def test_slugify_basic() -> None:
    assert slugify("Memoirs of a Sinner") == "memoirs-of-a-sinner"


# Spec: TC-02-04
def test_slugify_strips_punctuation() -> None:
    assert slugify("Hello, World!") == "hello-world"


# Spec: TC-02-04
def test_slugify_collapses_runs() -> None:
    assert slugify("a   b  -- c") == "a-b-c"


# Spec: TC-02-04
def test_slugify_non_ascii_falls_back_to_album() -> None:
    """A name with no representable ASCII content must not produce an empty
    slug — that would create `Albums//album.json`. CJK / emoji-only inputs
    fall back to the literal string 'album' (the user can rename later).
    Accented Latin characters are NFKD-normalised: "Émile" -> "emile" rather
    than "album", so users with Polish / French / Spanish / Czech / etc.
    names get a useful folder name."""
    assert slugify("---") == "album"
    assert slugify("") == "album"
    # CJK + emoji + symbol-only inputs have no ASCII fallback after NFKD.
    assert slugify("東京") == "album"
    assert slugify("\U0001f3b5\U0001f3b6") == "album"  # musical-note emoji


# Spec: TC-02-04 (extension: NFKD transliteration)
def test_slugify_strips_diacritics() -> None:
    """Accented Latin chars decompose to base + combining mark (NFKD); the
    combining marks live above U+007F and drop on ASCII-encode, leaving the
    base letter. This stops "Émile", "Café", "Naïve" from all colliding on
    the same fallback "album" slug."""
    assert slugify("Émile") == "emile"
    assert slugify("Café Tacvba") == "cafe-tacvba"
    assert slugify("Naïve") == "naive"
    assert slugify("Łódź") == "odz"  # Polish ł has no NFKD decomposition; drops
    # German ß casefolds to "ss" (Unicode-aware lower).
    assert slugify("Straße") == "strasse"


# Spec: TC-02-04, TC-02-08
def test_unique_slug_no_collision(tmp_path: Path) -> None:
    assert unique_slug(tmp_path, "memoirs-of-a-sinner") == "memoirs-of-a-sinner"


# Spec: TC-02-04, TC-02-08
def test_unique_slug_appends_2_then_3(tmp_path: Path) -> None:
    (tmp_path / "memoirs-of-a-sinner").mkdir()
    assert unique_slug(tmp_path, "memoirs-of-a-sinner") == "memoirs-of-a-sinner (2)"
    (tmp_path / "memoirs-of-a-sinner (2)").mkdir()
    assert unique_slug(tmp_path, "memoirs-of-a-sinner") == "memoirs-of-a-sinner (3)"


def test_unique_slug_handles_existing_file_not_dir(tmp_path: Path) -> None:
    """A file (not a folder) at the slug path also counts as collision —
    `Album.create` would fail mkdir if we treated it as free."""
    (tmp_path / "intro").write_text("not a folder")
    assert unique_slug(tmp_path, "intro") == "intro (2)"
