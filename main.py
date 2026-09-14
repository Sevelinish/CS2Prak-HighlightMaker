from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from highlighter.api.runtime import ApiOptions, ApiRuntime
from highlighter.application import Application
from highlighter.cli import CommandLine


def main() -> int:
    arguments = CommandLine.parse(sys.argv[1:])
    if arguments.api:
        return ApiRuntime(
            ApiOptions(
                transport=arguments.api,
                host=arguments.api_host,
                port=arguments.api_port,
                token=arguments.api_token,
                endpoint_file=arguments.api_endpoint_file,
                stream_events=arguments.api_stream_events,
                verbose=arguments.verbose,
            )
        ).run()

    return Application(
        demo_argument=arguments.demo,
        player_query=arguments.player,
        mode_token=arguments.mode,
        one_file=arguments.one_file,
        verbose=arguments.verbose,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
