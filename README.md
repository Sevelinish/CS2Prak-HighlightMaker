# HighlighterCS2

Finds the good moments in Counter-Strike 2 demos and records them as ready `.mp4` files.

You hand it a `.dem`, pick the moments you want from a table, and collect the finished clips. No CSDM and no outdated plugins: demo parsing runs on `demoparser2` with a Rust core, recording goes through HLAE, muxing through ffmpeg.

```
demo.dem  ->  parse  ->  detect  ->  table in the console  ->  pick moments
                                                                   |
                                                                   v
                                             clip plan (JSON)  ->  mirv scripts
                                                                   |
                                                                   v
                                       HLAE starts CS2  ->  record  ->  ffmpeg  ->  Highlighter/
```

## Features

* Four groups of detection rules: multi kills, weapon feats, clutches, trick shots
* Clips are cut into segments that skip the dead time between kills
* Clean picture: the real in-game crosshair with nothing else on screen
* Automatic hardware encoder selection (NVENC, AMF, QuickSync) with a real capability probe
* Filter by a single player
* Downloads HLAE and ffmpeg on its own at first run

## Quick start

### From a release

Put your demos in the `demos` folder next to `HighlighterCS2.exe` and run:

```bash
HighlighterCS2.exe
```

HLAE and ffmpeg land in the `tools` folder by themselves. Close CS2 before the first run if it is open.

### From source

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

### Building a release

```bash
.venv\Scripts\pip install pyinstaller
.venv\Scripts\python build.py
```

The result lands in `dist/HighlighterCS2/`. Rebuilding leaves the downloaded toolchain, your `config.json`, the logs, the demos and the recorded clips alone.

## Commands

| Command | What it does |
| --- | --- |
| `HighlighterCS2.exe` | Lists the demos it found and lets you choose |
| `HighlighterCS2.exe match.dem` | That demo, every player |
| `HighlighterCS2.exe match.dem -p s1mple` | Only that player's moments |
| `HighlighterCS2.exe match.dem -p -n1clxe` | Names starting with a dash work as they are |
| `HighlighterCS2.exe match.dem -p 76561198000000000` | The same by SteamID64 |
| `HighlighterCS2.exe match.dem -v` | Verbose console output |

**About the demo name.** A full path is optional. The file next to the exe is checked first, then the search runs through the `demos` folder and the CS2 demo folders, nested ones included. The extension can be left out: `dust1309` is found just like `dust1309.dem`. If the file is missing, the program prints exactly where it looked.

**About `--player`.** Also spelled `-p` or `--player-name`. It takes an exact name, part of a name, or a SteamID64, and case does not matter. Names that start with a dash are handled properly: plain argument parsing would read `-n1clxe` as a flag, so the arguments are normalised beforehand. Real flags are still not swallowed, `-p -v` remains an error.

If part of a name matches several players, the program lists which ones. If it matches nobody, it prints the whole roster of the demo.

## What a run looks like

Every stage prints its own line with a number, an outcome and details:

```
1/8 Reading match.dem
      OK de_dust2, 19 rounds, 10 players
2/8 Looking up 'n1clxe'
      OK -n1clxe (slot 2)
3/8 Scanning for highlights for -n1clxe
      OK 5 found

            the table is printed here and the selection is asked for

4/8 Planning clips
      work/plans/match.json
      OK 2 clips, 3 segments, 24s of footage
5/8 Launching Counter-Strike 2
      encoder h264_nvenc (hardware)
      HLAE injects the hook, then hands the game over
      OK game is up
6/8 Recording 2 clip(s) in 3 segment(s)
      the game closes itself after the last clip
      2/2 clips, elapsed 03:30
      OK 2 of 2 clips captured
7/8 Saving videos
      OK 2 of 2 clips written
8/8 Opening the output folder
      OK D:\...\Highlighter\match
```

Without `--player` there are seven steps, the player lookup is skipped. While recording, progress is printed every 30 seconds. The output folder opens by itself, which the `recording.openOutputFolder` key turns off.

A failed step is marked separately, so it is immediately clear where things stopped.

### How long it takes

Most of the time goes to the engine, not to the recording:

| Stage | Order of magnitude | Why |
| --- | --- | --- |
| HLAE injection | 2 to 3 seconds | The loader injects the hook and hands the process over |
| CS2 cold start | 40 to 90 seconds | Engine init, shaders, map load |
| Seek to the first clip | depends on the tick | `demo_gototick` has to simulate every tick from the start of the demo |
| Recording | depends on length | Runs slower than real time |

The seek is the least obvious cost: a moment from round one starts almost right away, a moment from round eight means fast forwarding through a quarter of an hour of play.

## Picking moments

The table numbers the clips. Then:

| Input | What it does |
| --- | --- |
| `3` | Clip 3 only |
| `1,4,7` | Three clips |
| `2-6` | A range |
| `1,3-5,9` | Mixed |
| `all` | Everything |
| `none` or Enter | Cancel |

## Clip segmentation

A round with three kills twenty seconds apart is not a highlight. So a clip is not recorded in one piece, but in segments:

1. A segment opens `leadInSeconds` (2 s) before the first kill
2. After each kill the camera holds for another `gapHoldSeconds` (4 s) waiting for the next one
3. If the next kill lands inside that window, the segment continues with no cut
4. If it does not, the segment closes, the game seeks forward, and a new segment opens `resumeLeadSeconds` (1.5 s) before the next kill
5. The last segment closes `postRollSeconds` (2.5 s) after the final kill

A cut is only made when the seek is guaranteed to move forward. The threshold is `gapHoldSeconds + resumeLeadSeconds + seekLeadTicks`, which is 7.5 seconds by default.

> **Why it works that way.** The seek destination is the next segment's start minus `seekLeadTicks`. When the pause is shorter than the threshold, that destination sits before the end of the current segment: the game jumps back, reaches the end of the segment again, and jumps back again. That is an endless loop. So every seek is computed while the scripts are generated, and `demo_gototick` is not written at all unless the destination is strictly ahead.

On the test demo, segmentation removed 58% of the dead time: a 1v2 clutch that ran 72 seconds became 15.5 seconds across three segments.

Segments are recorded as separate files and joined by ffmpeg through the concat demuxer, with no re-encoding.

## Configuration

`config.json` is created next to the program on the first run. Missing keys are filled in, your values are left alone.

The `version` key is the schema version. When it grows, migrations run: only the keys whose format changed are rewritten, the rest of your settings survive. The repository carries a `config.example.json` template, while `config.json` itself stays out of git so your local paths do not leak.

### `debug`

| Key | Default | What it does |
| --- | --- | --- |
| `debug` | `false` | Print the verbose log to the console |

Set it to `true` when something goes wrong and you need the details: the HLAE command line, the environment variables, the chosen encoder, the resolved player slots, the segment boundaries. The `-v` flag does the same thing, and it wins: it turns the output on even when `debug` is `false`.

With `debug` off the console shows only the step output. Warnings and errors still come through, since those are things you need to see, but routine progress chatter stays out of the way.

The `logs/highlighter.log` file always receives everything down to `DEBUG`, whatever this flag says. It only controls what reaches the screen.

### `paths`

| Key | Default | What it does |
| --- | --- | --- |
| `cs2Directory` | `""` | The CS2 folder. Empty means it is found through the Steam registry key and `libraryfolders.vdf` |
| `hlaeExecutable` | `""` | Path to `HLAE.exe`. Empty means it is downloaded |
| `ffmpegExecutable` | `""` | Path to `ffmpeg.exe`. Empty means it is downloaded |
| `demoDirectory` | `demos` | Where to look for demos |
| `outputDirectory` | `Highlighter` | Where finished clips go |
| `toolsDirectory` | `tools` | Where HLAE and ffmpeg are installed |
| `workDirectory` | `work` | Plans, raw takes, copies of the generated scripts |

### `recording`

| Key | Default | What it does |
| --- | --- | --- |
| `fps` | `60` | Recording frame rate |
| `width` / `height` | `1920` / `1080` | Resolution |
| `fullscreen` | `false` | Fullscreen instead of a window |
| `leadInSeconds` | `2.0` | How many seconds before the first kill make it into the clip |
| `resumeLeadSeconds` | `1.5` | How many seconds before a kill that opens a segment after a skip |
| `gapHoldSeconds` | `4.0` | How long to hold the camera after a kill, waiting for the next one |
| `postRollSeconds` | `2.5` | How many seconds after the very last kill |
| `maxClipSeconds` | `90.0` | Hard cap on segment length |
| `captureMode` | `crosshair` | What ends up in frame, see below |
| `showKillfeed` | `false` | Keep the kill feed in `crosshair` mode |
| `spectatorMode` | `first_person` | `fixed`, `first_person`, `third_person`, `free` |
| `spectateCommands` | see below | The camera aiming sequence |
| `seekLeadTicks` | `128` | How many ticks before a segment the seek lands |
| `playbackSpeed` | `1.0` | `host_timescale` while recording |
| `skipDeadTime` | `true` | Seek past the empty stretches |
| `closeGameWhenDone` | `true` | Close CS2 after the last clip |
| `openOutputFolder` | `true` | Open the clip folder when finished |

### `encoding`

| Key | Default | What it does |
| --- | --- | --- |
| `videoCodec` | `auto` | `auto` picks the best available one, or name a codec explicitly |
| `preferredCodecs` | nvenc, amf, qsv, libx264 | The order tried under `auto` |
| `quality` | `20` | Quality, lower is better. CRF for x264, CQ for NVENC |
| `preset` | `faster` | Speed against compression, libx264 only |
| `pixelFormat` | `yuv420p` | For player compatibility |
| `audioCodec` / `audioBitrate` | `aac` / `192k` | Audio during muxing |
| `container` | `mp4` | Container |
| `extraOutputArguments` | `[]` | Extra ffmpeg arguments |

The encoder is not simply taken off the list: every candidate is checked with a real test encode, and if the graphics card refuses a session, the search moves on. The chosen codec is printed at the game launch step.

### `crosshair`

A crosshair painted onto the finished clip. Only needed for `clean` mode, where there is no interface at all. Off by default.

| Key | Default | What it does |
| --- | --- | --- |
| `enabled` | `false` | Draw the crosshair |
| `length` | `10` | Arm length in px |
| `gap` | `4` | Gap from the centre in px |
| `thickness` | `2` | Thickness in px |
| `color` | `0x00FF00` | Colour |
| `opacity` | `0.9` | Opacity |
| `outline` | `1` | Outline thickness, `0` turns it off |
| `outlineColor` | `black` | Outline colour |
| `dot` | `false` | Centre dot |

The crosshair is centred through `iw` and `ih`, so it does not depend on resolution. It has one inherent limitation: under AWP zoom it stays on top of the scope, because it knows nothing about zoom. For ordinary highlights use `crosshair` mode, where the crosshair is the real one.

### `detection`

| Key | Default | What it does |
| --- | --- | --- |
| `minimumScore` | `10.0` | Threshold for making it into the table |
| `minimumKills` | `2` | Minimum kills in a round |
| `maximumHighlights` | `40` | Cap on table rows |
| `enabledRules` | all four | `multi_kill`, `weapon_feat`, `clutch`, `trick_shot` |
| `tagWeights` | see below | Weight of each tag |

Default tags and weights:

| Tag | Weight | Tag | Weight |
| --- | --- | --- | --- |
| `kills_2` | 4 | `clutch_1v2` | 10 |
| `kills_3` | 12 | `clutch_1v3` | 20 |
| `kills_4` | 22 | `clutch_1v4` | 30 |
| `kills_5` (ace) | 40 | `clutch_1v5` | 45 |
| `awp_double` | 8 | `noscope` | 9 |
| `awp_multi` | 16 | `wallbang` | 7 |
| `sniper_noscope_multi` | 10 | `through_smoke` | 5 |
| `knife_kill` | 14 | `blind_kill` | 6 |
| `zeus_kill` | 12 | `airborne_kill` | 8 |
| `deagle_headshot` | 6 | `headshot_only` | 5 |
| `pistol_multi` | 9 | `pistol_round` | 3 |
| `grenade_kill` | 5 | | |

Want more clips, drop `minimumScore` to 6. Want only aces and clutches, raise it to 30.

### `game`

| Key | Default | What it does |
| --- | --- | --- |
| `tickRate` | `64` | Demo tick rate |
| `launchArguments` | `-steam -insecure -afxDisableSteamStorage -novid -console` | CS2 arguments |
| `hookDllRelativePath` | `x64/AfxHookSource2.dll` | Which HLAE library to inject |
| `steamEnvironment` | `SteamAppId` and friends | Environment variables, without them CS2 will not reach Steam |
| `consoleVariables` | see config | Cvars set before recording |
| `gameStartupTimeoutSeconds` | `300` | How long to wait for `cs2.exe` to appear after injection |
| `recordingTimeoutMinutes` | `120` | When to force the game closed |
| `applyHighGraphics` | `true` | Raise graphics to high before recording |
| `restoreGraphicsOnExit` | `true` | Put your settings back afterwards |
| `hlaeArgumentTemplate` | see config | HLAE arguments |

The `consoleVariables` and `steamEnvironment` maps **merge** with the defaults rather than replacing them. You can change a single `volume` without losing the other two dozen cvars.

### `toolchain`

| Key | Default | What it does |
| --- | --- | --- |
| `autoDownload` | `true` | Fetch HLAE and ffmpeg automatically |
| `hlaeDownloadUrl` | `""` | A direct link. Empty means the latest release is resolved through the API |
| `hlaeReleaseApiUrl` | advancedfx GitHub API | Where the latest release comes from |
| `hlaeAssetPattern` | `hlae_*.zip` | Which asset to download from that release |
| `ffmpegDownloadUrl` | gyan.dev build | Where ffmpeg comes from |
| `downloadTimeoutSeconds` | `600` | Download timeout |

The HLAE install is checked for integrity before every run. If `AfxHook.dat`, `injector.exe` or the hook library went missing (an interrupted download, antivirus, a bad extraction), the folder is wiped and HLAE is reinstalled, instead of throwing a cryptic `AfxError #1002`.

## Under the hood

Half the commands from CS:GO guides either do not exist in CS2 or behave differently. Everything below was verified by reading strings out of `client.dll`, `engine2.dll` and `AfxHookSource2.dll`.

### Starting CS2 through HLAE

HLAE has **no** command line launcher for CS2. The binary contains `ProcessArgsCsgoLauncher`, but no CS2 counterpart exists: the CS2 launch dialog is only reachable from the graphical interface. So the game is started through the generic custom loader:

```
HLAE.exe -noGui -autoStart -customLoader
         -programPath "<cs2>/game/bin/win64/cs2.exe"
         -cmdLine     "-steam -insecure -afxDisableSteamStorage -sw -w 1920 -h 1080 +exec ... +playdemo ..."
         -hookDllPath "<hlae>/x64/AfxHookSource2.dll"
```

The custom loader does not set the Steam environment itself, the application does that through `steamEnvironment`, otherwise `cs2.exe` will not start.

**HLAE is an injector, not a supervisor.** It injects the hook, starts the game and exits with code 0 right away, long before CS2 has finished loading. So the application waits on the `cs2.exe` process rather than on HLAE: it polls the process list once a second and only removes the temporary scripts and the graphics settings after the game has closed. Waiting on HLAE instead deletes the configs two seconds in, and the in game `exec` finds nothing.

While recording, CS2 must be the only instance. If the game is already running, the application refuses to start and asks you to close it.

HLAE looks for ffmpeg in its own folder rather than in `PATH`, so `<hlae>/ffmpeg/ffmpeg.ini` is written automatically. HLAE does not work from paths with non latin characters, which is checked before launch.

### CS2 commands that are easy to get wrong

| Task | CS:GO | CS2 |
| --- | --- | --- |
| Switch the camera to a player | `spec_player_by_accountid` | `spec_player <slot>`, where slot is `user_id + 1` |
| Hold the camera there | none | `spec_lock_to_accountid <accountid>`, it only holds an already chosen target |
| Turn off the auto director | `spec_autodirector 0` | `spec_autodirector 0` |
| First person view | `spec_mode 4` | `spec_mode 2`, the numbering differs |
| Remove the wallhack X-ray | none | `spec_show_xray 0` |
| Hide the demo scrub bar | `demoui` | `demo_ui_mode 0` |
| Hide the TrueView notice | none | `cl_trueview_show_status 0` |
| Keep audio when focus is lost | none | `snd_mute_losefocus 0` |

**Observer modes in CS2 are shifted relative to CS:GO.** CS2 has five of them:

```
0 OBS_MODE_NONE   1 OBS_MODE_FIXED   2 OBS_MODE_IN_EYE   3 OBS_MODE_CHASE   4 OBS_MODE_ROAMING
```

CS:GO also had `DEATHCAM` and `FREEZECAM` in slots 1 and 2, which pushed `IN_EYE` to fourth place. That makes `spec_mode 4` from any CS:GO guide mean a **free floating camera** in CS2, one that ignores the target and hangs wherever it likes.

### Aiming the camera

`spec_lock_to_accountid` only holds an already chosen target, it never moves the observer anywhere. The camera is switched by `spec_player`, described in game as "Spectate a player by name or slot". Order matters: setting the view mode after choosing the target drops the camera into free mode.

```
spec_autodirector 0
spec_mode 1              a mode change has to come first
spec_player <slot>       slot is user_id + 1
spec_lock_to_accountid <accountid>
spec_mode 2              IN_EYE
```

The slot is read from the demo. `spec_player` accepts a name as well, but a slot avoids every quoting and unicode problem with nicknames. The whole sequence can be overridden in `spectateCommands`.

### What ends up in frame

| `captureMode` | What you see |
| --- | --- |
| `crosshair` | The real in-game crosshair and nothing else. The default |
| `clean` | Nothing at all, the frame is captured before the interface is drawn |
| `full` | The normal in-game interface |

In `crosshair` mode the stock moviemaking cvars do the work:

```
cl_drawhud 1
cl_draw_only_deathnotices 1        crosshair and kill feed only
cl_drawhud_force_deathnotices -1   drop the kill feed too
```

The crosshair then behaves exactly as it does in game: it hides under the AWP scope when zoomed, spreads while moving, and disappears with a knife.

`clean` mode uses a dedicated stream captured before Panorama is drawn:

```
mirv_streams add normal highlighterClean
mirv_streams edit highlighterClean record 1
mirv_streams edit highlighterClean capture beforeUi
mirv_streams record screen enabled 0
```

Every two dimensional element in CS2 is drawn by Panorama, so nothing makes it into the frame: no interface, no radar, no kill feed, no avatars, no toasts, no MVP panel. The crosshair is gone as well, since it is part of the interface. This mode suits you if you plan to lay your own graphics over the footage while editing.

### How CS2 writes video

In CS:GO frames come from the `baseFx` stream through `mirv_streams edit`. **CS2 has no such stream at all**, it uses screen capture, and that is off by default:

```
mirv_streams settings add ffmpeg highlighterFfmpeg "... {QUOTE}{AFX_STREAM_PATH}/video.mp4{QUOTE}"
mirv_streams record screen enabled 1
mirv_streams record screen settings highlighterFfmpeg
mirv_streams record startMovieWav 1
```

Without `record screen enabled 1` HLAE happily creates the take and writes `audio.wav`, but no video appears at all. The `{AFX_STREAM_PATH}` variable is the stream **folder**, so the file has to be spelled `{AFX_STREAM_PATH}/video.mp4` and not `{AFX_STREAM_PATH}.mp4`.

### Graphics settings

With `applyHighGraphics: true` the application edits `cs2_video.txt` in the `userdata` folder:

* it makes a `cs2_video.txt.highlighter-backup` copy first
* it changes **only keys that already exist**, inventing none, so the file never breaks
* it sets `Autoconfig: 0` so CS2 does not overwrite the settings on startup
* it restores the original afterwards when `restoreGraphicsOnExit` is on

Turn `applyHighGraphics` off if you would rather record with your own settings. Note that CS2 rewrites this file while running, so the restore only wins once the game has closed.

### Warmup in demos

The `is_warmup_period` field the parser exposes came back as `False` in every CS2 demo tested, knife warmup round included. It cannot be trusted. The start of the match is taken from the `begin_new_match` event instead, and everything before it is discarded.

## Project layout

```
src/highlighter/
├── application.py       the whole scenario
├── cli.py               command line parsing
├── config/              config.json schema, loading, migrations
│   └── schema.py  repository.py  migrations.py
├── domain/              the domain model
│   ├── kill.py  round.py  match.py  player.py  team.py  weapon.py
│   └── highlight.py
├── demo/                reading .dem
│   ├── reader.py        demoparser2 into Match
│   ├── timeline.py      cutting off the warmup
│   └── locator.py       finding demos by folder and by name
├── detection/           finding moments
│   ├── engine.py  context.py  registry.py  rule.py  player_filter.py
│   └── rules/           multi_kill  weapon_feat  clutch  trick_shot
├── plan/                the clip plan, the contract between stages
│   └── models.py  builder.py  segmenter.py  writer.py
├── recording/           everything HLAE related
│   ├── mirv_script.py   cfg generation
│   └── script_writer.py graphics.py  launcher.py  game_process.py  session.py
├── media/               assembling the final mp4
│   └── assembler.py  encoders.py  crosshair.py  output_library.py  folder_opener.py
├── provisioning/        downloading HLAE and ffmpeg
│   └── toolchain.py  downloader.py  archive.py  release_resolver.py  hlae_installation.py
├── game/                locating Steam and CS2
│   └── steam.py  installation.py
└── presentation/        the console
    └── highlight_table.py  selector.py  selection_parser.py  demo_picker.py  steps.py
```

To add your own detection rule: subclass `HighlightRule`, set `name`, add the class to `AVAILABLE_RULES` in `detection/registry.py` and a weight to `tagWeights`.

## Tests

```bash
.venv\Scripts\python -m pytest
```

Over two hundred tests. They cover argument parsing, demo lookup, detection and scoring, segmentation, the guard against seek loops, mirv script generation, encoder selection, config migrations, HLAE install integrity and watching the game process.

## Requirements

* Windows
* Counter-Strike 2
* Python 3.11 or newer, only to run from source
* Free space for the raw takes in the `work` folder

HLAE needs CS2 started with `-insecure`. That is the normal mode for watching demos and it does not affect your account, but you cannot join an online match while in it.
