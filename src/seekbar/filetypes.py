import enum


class FileCategory(enum.Enum):
    FOLDER = "folder"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    ARCHIVE = "archive"
    CODE = "code"
    DOCUMENT = "document"
    PDF = "pdf"
    SHEET = "sheet"
    EXECUTABLE = "executable"
    GENERIC = "generic"


# Extensions are grouped by category and flattened into a lookup below. FOLDER and GENERIC have no
# extensions: folders are detected via the is-dir flag, GENERIC is the fallback for anything unmatched.
_CATEGORY_EXTENSIONS: dict[FileCategory, tuple[str, ...]] = {
    FileCategory.IMAGE: (
        "png",
        "jpg",
        "jpeg",
        "gif",
        "bmp",
        "webp",
        "svg",
        "ico",
        "tiff",
        "tif",
        "heic",
        "heif",
        "avif",
        "psd",
        "raw",
    ),
    FileCategory.VIDEO: ("mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "3gp"),
    FileCategory.AUDIO: ("mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus", "aiff", "mid", "midi"),
    FileCategory.ARCHIVE: ("zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz", "zst", "iso", "cab", "lz", "lzma"),
    FileCategory.CODE: (
        "py",
        "js",
        "ts",
        "tsx",
        "jsx",
        "java",
        "c",
        "h",
        "cpp",
        "hpp",
        "cc",
        "cs",
        "go",
        "rs",
        "rb",
        "php",
        "swift",
        "kt",
        "kts",
        "scala",
        "sh",
        "bash",
        "zsh",
        "ps1",
        "bat",
        "cmd",
        "sql",
        "html",
        "htm",
        "css",
        "scss",
        "sass",
        "less",
        "json",
        "xml",
        "yaml",
        "yml",
        "toml",
        "ini",
        "cfg",
        "lua",
        "r",
        "pl",
        "dart",
        "vue",
        "svelte",
    ),
    FileCategory.DOCUMENT: ("doc", "docx", "odt", "rtf", "txt", "md", "rst", "tex", "epub", "mobi", "pages", "djvu"),
    FileCategory.PDF: ("pdf",),
    FileCategory.SHEET: ("xls", "xlsx", "ods", "csv", "tsv", "numbers"),
    FileCategory.EXECUTABLE: ("exe", "msi", "dll", "app", "dmg", "deb", "rpm", "apk", "appimage", "bin", "com", "jar"),
}

_EXTENSION_CATEGORIES: dict[str, FileCategory] = {
    extension: category for category, extensions in _CATEGORY_EXTENSIONS.items() for extension in extensions
}


def categorize(name: str) -> FileCategory:
    _, separator, extension = name.rpartition(".")
    if not separator:
        return FileCategory.GENERIC
    return _EXTENSION_CATEGORIES.get(extension.lower(), FileCategory.GENERIC)
