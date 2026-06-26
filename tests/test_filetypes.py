import pytest
from assertpy2 import assert_that

from seekbar.filetypes import _CATEGORY_EXTENSIONS, FileCategory, categorize


class TestCategorize:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("photo.png", FileCategory.IMAGE),
            ("scan.JPEG", FileCategory.IMAGE),
            ("movie.mkv", FileCategory.VIDEO),
            ("track.flac", FileCategory.AUDIO),
            ("bundle.zip", FileCategory.ARCHIVE),
            ("module.py", FileCategory.CODE),
            ("config.yaml", FileCategory.CODE),
            ("readme.md", FileCategory.DOCUMENT),
            ("paper.pdf", FileCategory.PDF),
            ("data.csv", FileCategory.SHEET),
            ("installer.exe", FileCategory.EXECUTABLE),
        ],
    )
    def test_known_extension(self, name: str, expected: FileCategory):
        assert_that(categorize(name)).is_equal_to(expected)

    def test_case_insensitive(self):
        assert_that(categorize("ARCHIVE.ZIP")).is_equal_to(FileCategory.ARCHIVE)

    def test_compound_extension_uses_last_segment(self):
        assert_that(categorize("backup.tar.gz")).is_equal_to(FileCategory.ARCHIVE)

    def test_unknown_extension_falls_back_to_generic(self):
        assert_that(categorize("data.xyz")).is_equal_to(FileCategory.GENERIC)

    def test_no_extension_is_generic(self):
        assert_that(categorize("Makefile")).is_equal_to(FileCategory.GENERIC)

    def test_dotfile_without_extension_is_generic(self):
        assert_that(categorize(".gitignore")).is_equal_to(FileCategory.GENERIC)

    def test_trailing_dot_is_generic(self):
        assert_that(categorize("report.")).is_equal_to(FileCategory.GENERIC)


class TestExtensionMap:
    def test_folder_and_generic_have_no_extensions(self):
        assert_that(_CATEGORY_EXTENSIONS).does_not_contain_key(FileCategory.FOLDER)
        assert_that(_CATEGORY_EXTENSIONS).does_not_contain_key(FileCategory.GENERIC)

    def test_no_extension_belongs_to_two_categories(self):
        flattened = [extension for extensions in _CATEGORY_EXTENSIONS.values() for extension in extensions]
        assert_that(len(set(flattened))).is_equal_to(len(flattened))

    def test_every_extension_is_lowercase(self):
        for extensions in _CATEGORY_EXTENSIONS.values():
            for extension in extensions:
                assert_that(extension).is_equal_to(extension.lower())
