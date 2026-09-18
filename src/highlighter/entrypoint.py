from __future__ import annotations

import argparse

from .api.runtime import ApiOptions, ApiRuntime
from .application import Application
from .cli import CommandLine
from .importing.command import DemoGetCommand
from .update.command import UpdateCommand


class EntryPoint:
    @classmethod
    def run(cls, argv: list[str]) -> int:
        return cls.execute(CommandLine.parse(argv))

    @classmethod
    def execute(
        cls, arguments: argparse.Namespace, show_banner: bool = True
    ) -> int:
        if arguments.update:
            return UpdateCommand(verbose=arguments.verbose).run()

        if arguments.demo_get:
            return DemoGetCommand(verbose=arguments.verbose).run()

        if arguments.api:
            return cls._serve(arguments)

        return Application(
            demo_argument=arguments.demo,
            player_query=arguments.player,
            mode_token=arguments.mode,
            one_file=arguments.one_file,
            keep_game_open=arguments.keep_game_open,
            fly=arguments.fly,
            enemy=arguments.enemy,
            verbose=arguments.verbose,
            show_banner=show_banner,
        ).run()

    @staticmethod
    def _serve(arguments: argparse.Namespace) -> int:
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
