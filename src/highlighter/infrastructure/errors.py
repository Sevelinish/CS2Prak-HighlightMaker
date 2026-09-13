class HighlighterError(Exception):
    pass


class ConfigurationError(HighlighterError):
    pass


class DemoNotFoundError(HighlighterError):
    pass


class DemoParsingError(HighlighterError):
    pass


class GameNotFoundError(HighlighterError):
    pass


class ToolchainError(HighlighterError):
    pass


class DownloadError(ToolchainError):
    pass


class RecordingError(HighlighterError):
    pass


class EncodingError(HighlighterError):
    pass


class SelectionAbortedError(HighlighterError):
    pass
