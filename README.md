<img src="logo.svg" alt="HighlighterCS2" width="120" align="right">

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
* A grenade mode that lists every throw with its landing callout and replays it with a zoom hold
* Downloads HLAE and ffmpeg on its own at first run
* `-exit0` keeps the game open so a second batch skips the CS2 startup
* `-update` installs the newest release on its own and keeps your clips and settings
* `-demoget` finds new demos in Downloads, unpacks them and files them under a name you choose
* `-fly` puts the camera behind the grenade and follows it from the throw to the detonation
* `-enemy` adds the same moment from each victim's eyes to the end of the clip
* A prompt inside the program: start the exe, type the arguments there, with grey suggestions as you type
* Every new demo is read once and remembered: its map and its roster, so `-p` completes real nicknames
* A full screen editor for `config.json` inside the console, with JSON colouring and a check before it saves
* A JSON plugin API, written for CS2Prak-Launcher, that drives the whole pipeline from another program

## Quick start

### From a release

Put your demos in the `demos` folder next to `HighlighterCS2.exe` and run:

```bash
HighlighterCS2.exe
```

Started with no arguments it opens its own prompt, where you type the same arguments one run
at a time. See [The prompt](#the-prompt).

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
| `HighlighterCS2.exe` | Opens the prompt and takes the rest of the arguments there |
| `HighlighterCS2.exe -no-shell` | Skips the prompt, lists the demos it found and lets you choose |
| `HighlighterCS2.exe match.dem` | That demo, every player |
| `HighlighterCS2.exe match.dem -p s1mple` | Only that player's moments |
| `HighlighterCS2.exe match.dem -p -n1clxe` | Names starting with a dash work as they are |
| `HighlighterCS2.exe match.dem -p 76561198000000000` | The same by SteamID64 |
| `HighlighterCS2.exe match.dem -m nades_smoke` | Every smoke that was thrown, instead of highlights |
| `HighlighterCS2.exe match.dem -m nades` | Every grenade of every kind |
| `HighlighterCS2.exe match.dem -m nades_smoke -fly` | Fly behind each smoke until it opens |
| `HighlighterCS2.exe match.dem -enemy` | Then replay every kill from the victim's eyes |
| `HighlighterCS2.exe match.dem -one-file` | Join the picked moments into a single video |
| `HighlighterCS2.exe match.dem -exit0` | Leave the game running so the next batch skips the startup |
| `HighlighterCS2.exe -update` | Install the newest release, keeping clips and settings |
| `HighlighterCS2.exe -demoget` | Import new demos from Downloads and the game folders |
| `HighlighterCS2.exe match.dem -shell` | Opens the prompt instead of running straight away |
| `HighlighterCS2.exe match.dem -v` | Verbose console output |
| `HighlighterCS2.exe --api http` | Serve the plugin API on loopback instead of running the app |
| `HighlighterCS2.exe --api stdio` | Speak the plugin API over stdin and stdout |

**About the demo name.** A full path is optional. The file next to the exe is checked first, then the search runs through the `demos` folder and the CS2 demo folders, nested ones included. The extension can be left out: `dust1309` is found just like `dust1309.dem`. If the file is missing, the program prints exactly where it looked.

**About `--player`.** Also spelled `-p` or `--player-name`. It takes an exact name, part of a name, or a SteamID64, and case does not matter. Names that start with a dash are handled properly: plain argument parsing would read `-n1clxe` as a flag, so the arguments are normalised beforehand. Real flags are still not swallowed, `-p -v` remains an error.

If part of a name matches several players, the program lists which ones. If it matches nobody, it prints the whole roster of the demo.

**About `-one-file`.** Also spelled `--one-file`. Normally every picked moment becomes its own `.mp4`. With this flag they are joined, in the order they happen in the demo, into `<demo>_highlights.mp4`, and the individual clips move into a `parts` subfolder so the result stays obvious:

```
Highlighter/match/
├── match_highlights.mp4     the joined result
└── parts/
    ├── 01_round08_n1clxe_awp_double.mp4
    ├── 02_round09_n1clxe_awp_double.mp4
    └── 03_round10_n1clxe_awp_double.mp4
```

Nothing is deleted, so the separate clips stay available for editing. Joining runs through the ffmpeg concat demuxer with no re-encoding, so it costs seconds and loses no quality. The same behaviour can be made permanent with `recording.singleFile` in the config; the flag simply forces it on for one run.

**About `-exit0`.** Also spelled `--exit0` or `--keep-game-open`. See
[Keeping the game open](#keeping-the-game-open).

**About `-demoget`.** Also spelled `--demoget`. See [Importing demos](#importing-demos).
Imported demos are picked up by the prompt like any other, so their maps and nicknames are read
on the next start.

**About `-update`.** Also spelled `--update`. See [Updating](#updating).

**About `--api`.** It replaces the interactive run with the JSON API described in
[docs/API.md](docs/API.md). `--api-port 0` picks a free port, `--api-token` sets the bearer
token instead of generating one, and `--api-endpoint-file` writes the base URL and token to a
JSON file for a launcher that starts the plugin detached.

## The prompt

Started with no arguments in a console, the program does not begin a run. It opens a prompt and
waits:

```
> 
```

Everything that used to be typed after `HighlighterCS2.exe` is typed here instead, one run per
line. When a run finishes the prompt comes back, so a session of several demos costs one startup
instead of one per demo.

```
> mirage17.dem -p s1mple -exit0
> mirage17.dem -m nades_smoke -fly -exit0
> nuke04.dem -enemy -one-file
> exit
```

Paired with `-exit0` this is the fastest way to work through a demo: CS2 stays open between
lines, so only the first run pays for the game startup.

### Suggestions

While you type, the rest of what you are likely to write appears in grey after the cursor. What
is offered depends on where the cursor is:

| What you typed | What appears | Why |
| --- | --- | --- |
| nothing | `<demo>` | the line starts with a demo name |
| `mir` | `age17.dem` | a demo of that name is in the search folders |
| `-f` | `ly` | only `-fly` starts like that |
| `-e` | `nemy` | `-enemy` and `-exit0` both match, the first one is shown |
| `-p` | `<nickname>` | the flag takes a value, and a nickname cannot be guessed |
| `-m ` | `<mode>` | the same, with the seven modes listed on the right |
| `-m nades_` | `smoke` | the value is completed from the real mode list |
| `mirage17.dem ` | `<flag>` | the demo is set, what follows is a flag |
| `mirage17.dem -p cro` | `na999` | that nickname is in that demo's roster |

The text on the right of the line is a short explanation: the description of the flag when one
matches, or the list of matches when several do. A flag that is already on the line is not
offered a second time.

A grey value in angle brackets is a hint, not text. It is never inserted, it only says what the
program is waiting for. Grey text that is not in brackets is a real completion and can be taken.

When nothing in the grammar matches, the last line you typed that starts the same way is offered
instead, so a long command is retyped by its first few characters.

### Nicknames

Looking a nickname up in the scoreboard and typing it by hand is the slowest part of a run, so
the program keeps a small book of what it has read.

The first time a demo is seen, its header and its player table are read once. That takes well
under a second and gives two things: the map, and the roster with SteamID64 and starting side.
It is kept in `work/demo_index.json` against the file name and size, so a demo is never read
twice, and a file that changed counts as new.

That book is filled in three places. The prompt reads whatever is new when it starts, and says
so:

```
Reading 3 new demo(s) for the map and the nicknames
[+] 3 demo(s) read, 30 nickname(s)  1.9s
```

`demos` reads anything still missing before it prints the table. And every recording run writes
down the demo it just parsed, since the roster is already in hand by then.

After that, `-p` completes real names:

```
> mirage17.dem -p cro
                  na999      started CT
```

Type nothing after `-p` and the hint lists the whole roster, with Tab walking through it. Type
part of a name and it is completed. Names that start with a dash, which CS2 players are fond of,
are found without typing the dash: `n1c` finds `-n1clxe`, and since a suggestion like that cannot
continue what you typed, the hint says `tab for -n1clxe` instead of showing grey text.

Which roster is offered depends on the line. Name a demo and you get that demo's players, with
the side each of them started on. Do not name one and you get every player the program has ever
read, each one noted with the demo it came from. If the demo on the line has never been read, it
is read right then, once.

`players` prints the same list as a table with SteamID64 next to each name, for when you want to
look before you type.

### Editing the config

`config` opens `config.json` in a full screen editor without leaving the console:

```
 D:\HighlighterCS2\config.json                                          modified
  1 | {
  2 |   "version": 18,
  3 |   "debug": false,
  4 |   "paths": {
  5 |     "cs2Directory": "",
 ...
 Ctrl+S saves, Ctrl+X leaves                                  line 3, column 12
 Ctrl+S save   Ctrl+X leave   Ctrl+Z undo   Ctrl+Y redo   Ctrl+K cut to end
```

Keys, numbers, `true`, `false` and `null` are coloured apart, the line the cursor is on is
marked in the gutter, and long lines scroll sideways. Arrows, Home, End, Page Up, Page Down,
Ctrl+Left and Ctrl+Right move around, Ctrl+Home and Ctrl+End jump to the ends of the file,
Ctrl+W deletes a word, Ctrl+K cuts to the end of the line, Tab inserts two spaces, and Enter
keeps the indentation of the line it split.

Nothing reaches the disk until it is known to be good. Ctrl+S first parses the text as JSON,
and then hands the result to the same schema the program loads at startup. A missing comma
stops the save, the message says what is wrong and on which line, and the cursor jumps there:

```
 Expecting ',' delimiter at line 9                              line 9, column 5
```

A value of the wrong kind, `"fps": "sixty"` for instance, is caught the same way. Only when
both checks pass is the file written, and it is written to a temporary file next to it and then
swapped in, so a half written `config.json` cannot happen. Line endings are kept as they were.

Leaving with unsaved changes asks first: `y` saves, `n` throws the changes away, anything else
goes back to editing. Ctrl+Z and Ctrl+Y walk through what you did.

Settings the schema does not know are not an error, but they are pointed out after saving,
because the next run rewrites the file from the schema and drops them:

```
1 setting(s) are not part of the schema and the next run will drop them: madeUp
```

### Keys

| Key | What it does |
| --- | --- |
| Tab | takes the grey suggestion, pressing again moves to the next match |
| Right, End | takes the grey suggestion when the cursor is at the end of the line |
| Left, Right, Home, End | move inside the line |
| Ctrl+Left, Ctrl+Right | move by words |
| Up, Down | walk through the lines you typed before |
| Ctrl+W | delete the word before the cursor |
| Ctrl+U | delete to the start of the line |
| Ctrl+L | wipe the screen |
| Esc | clear the line |
| Ctrl+C | clear the line, or leave when the line is already empty |
| Ctrl+D | leave |

### Words it understands on its own

| Word | What it does |
| --- | --- |
| `run` | records with the arguments that follow, or with none at all |
| `help`, `?` | prints every argument, key and example |
| `demos` | reads any new demos, then lists them with map and player count |
| `players [demo]` | lists the nicknames read out of a demo, or out of all of them |
| `config` | opens `config.json` in an editor inside this console |
| `clear`, `cls` | wipes the screen |
| `version` | prints the installed version |
| `exit`, `quit` | leaves |

An empty line does nothing. To start a run with no arguments at all, which is the old behaviour
of double clicking the exe, type `run`.

`-update` behaves differently here than the other arguments. The installer replaces the exe that
is running, so it cannot run while the prompt is open. When an update is downloaded the prompt
closes itself and the swap happens a few seconds later, exactly as it does from the command line.

### When the prompt does not open

The prompt is for a person at a keyboard, so it stays out of the way everywhere else:

* Any argument on the command line runs straight away, as before. Only a bare `HighlighterCS2.exe`
  opens the prompt.
* `-no-shell` never opens it, for a shortcut or a script that expects the old behaviour.
* `-shell` opens it even when other arguments were given.
* `--api` never opens it. A launcher speaking the plugin API is not affected in any way.
* Redirected input never opens it, so `echo ... | HighlighterCS2.exe` keeps working.

In a console that cannot do inline colour the prompt still runs and still takes the same
arguments, only without the grey suggestions. It says so on the first line.

The lines you type are kept in `work/shell_history.txt`, the last 200 of them, so Up still
reaches yesterday's commands. What was read out of your demos is kept next to it in
`work/demo_index.json`. Deleting either file costs nothing: the history starts over, and the
demos are read again the next time they are needed.

## What a run looks like

Every stage prints its own line with a number, an outcome and details:

```
╭───────────────────────────────╮
│  HighlighterCS2 1.5.1         │
│  CS2 demo highlight recorder  │
╰───────────────────────────────╯

  1/8  Reading match.dem
       [+] de_dust2, 19 rounds, 10 players  2.4s
  2/8  Looking up 'n1clxe'
       [+] -n1clxe (slot 2)  0.0s
  3/8  Scanning for highlights for -n1clxe
       [+] 5 found  0.1s

            the table is printed here and the selection is asked for

  4/8  Planning clips
        ·  work/plans/match.json
       [+] 2 clips, 3 segments, 24s of footage  0.0s
  5/8  Starting Counter-Strike 2
        ·  encoder h264_nvenc (hardware)
        ·  HLAE injects the hook, then hands the game over
       [+] game is up  1m 34s
  6/8  Recording 2 clip(s) in 3 segment(s)
        ·  the game closes itself once the takes are written
        ·  2/3 segments, elapsed 03:30
        ·  closing the game
       [+] 3 of 3 segment(s) captured  4m 12s
  7/8  Saving videos
       [+] 2 of 2 clips written  3.8s
  8/8  Opening the output folder
       [+] D:\...\Highlighter\match  0.0s

Clips written
╭─────┬──────────────────────────────────┬──────────┬───────────┬───────╮
│   # │ File                             │   Length │      Size │ Audio │
├─────┼──────────────────────────────────┼──────────┼───────────┼───────┤
│   1 │ 01_round08_n1clxe_awp_double.mp4 │      12s │   23.0 MB │  yes  │
│   2 │ 02_round09_n1clxe_awp_double.mp4 │     9.8s │   19.9 MB │  yes  │
╰─────┴──────────────────────────────────┴──────────┴───────────┴───────╯
2/2 clips saved to D:\...\Highlighter\match
```

Every step carries how long it took, so a slow run shows where the time actually went. Without `--player` there are seven steps, the player lookup is skipped. While recording, progress is printed every 30 seconds. The output folder opens by itself, which the `recording.openOutputFolder` key turns off.

A failed step is marked in red with the reason, so it is immediately clear where things stopped.

### How long it takes

Most of the time goes to the engine, not to the recording:

| Stage | Order of magnitude | Why |
| --- | --- | --- |
| HLAE injection | 2 to 3 seconds | The loader injects the hook and hands the process over |
| CS2 cold start | 40 to 90 seconds | Engine init, shaders, map load |
| Seek to the first clip | depends on the tick | `demo_gototick` has to simulate every tick from the start of the demo |
| Recording | depends on length | Runs slower than real time |
| Writing the takes | a few seconds | HLAE feeds ffmpeg through a pipe, which keeps encoding after the last frame |

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

## Grenade mode

Without `-m` the program looks for kills and never mentions grenades. With `-m nades_<kind>` it does the opposite: it lists every grenade of that kind, and records the ones you pick.

```bash
HighlighterCS2.exe match.dem -m nades_smoke
```

| Mode | What it lists |
| --- | --- |
| `nades_smoke` | Smokes |
| `nades_flash` | Flashbangs |
| `nades_he` | HE grenades |
| `nades_molotov` | Molotovs and incendiaries |
| `nades_decoy` | Decoys |
| `nades` | All of the above |

The listing gives the round, the round clock, the thrower, the grenade kind, where it landed, the flight time, and the thrower's position and view angles:

```
  # | Rnd |  Time | Player       | Side | Kind  | Landed         | Flight | Position / Angles
  1 |   1 |  0:28 | kulbergenn12 |  T   | smoke | BombsiteB      |   6.5s | -160 888 -104 | -50.6 -146.6
  2 |   1 |  0:28 | -m0rph_      |  CT  | smoke | PalaceInterior |   1.9s | 143 -1969 -95 | -12.0 -119.2
  3 |   2 |  0:08 | -m0rph_      |  CT  | smoke | TRamp          |   1.7s | -209 -1912 -168 | 0.2 46.1
```

The full `setpos` and `setang` commands for reproducing a throw are written into the plan JSON under each clip's `note`.

`--player` narrows the list to one thrower, and `-one-file` joins the picked throws into a single video, exactly as in highlight mode.

### Where it landed

Landing spots are named from the game's own callouts, not from a hand written table. Every CS2 player carries a networked `last_place_name` field taken from the map's nav mesh, so the reader samples player positions across the demo, builds a cloud of `coordinate -> callout` points, and labels each landing by the nearest sample. On the test demo that produced 23 distinct Mirage callouts with the nearest sample typically 3 to 40 units away, which is closer than a player is wide.

The benefit is that this works on every map, including workshop ones, with no per map data to maintain. When no sample lies within 600 units the spot is reported as `unknown`.

### Throws that share a moment

Two smokes a second apart used to produce two clips whose recording windows overlapped. The
recorder plays the demo once and drives everything from tick callbacks, so overlapping windows
interleave: the second clip starts recording while the first is still running, the first clip's
stop ends the second one's take, and the zoom and the landing camera fire for the wrong grenade.
That is why the camera looked like it could not decide what to film.

Throws whose windows overlap are now filmed as one clip. One lead in, one zoom hold before the
first throw, the whole burst filmed from the thrower, then one cut to a camera pulled back far
enough to hold every landing in frame. When the landings are further apart than
`maximumGroupSpread` no single shot works, so the camera follows the first throw instead.

On the test demo this is not an edge case: 113 smokes became 49 clips, with 64 throws folded
into the clip they shared. Bursts of four and five throws are common in an execute.

The same rule applies to highlights, where two players can trade kills inside one firefight.
Those merge into a single clip following the higher scoring player, and the clip note says who
else was in it.

Two related guards came out of this. A clip is never pushed past its own action by the round
clamp, which used to happen when a grenade thrown at the end of one round detonated inside the
next and landed a clip two seconds of empty footage away from the throw. And the plan is checked
to hold no overlapping segments at all.

### Flying with the grenade

```bash
HighlighterCS2.exe match.dem -m nades_smoke -fly
```

Instead of standing still and cutting to the landing spot, the camera sits behind the grenade
and follows it the whole way, from the moment it leaves the hand until it opens.

HLAE has a camera path system for exactly this, but `mirv_campath add` only captures wherever
the camera happens to be, so a path cannot be scripted keyframe by keyframe from the console.
What it does have is `mirv_campath load`, which reads a path from an XML file. So the recorder
writes the path itself:

```xml
<campath positionInterp="cubic" rotationInterp="sCubic" fovInterp="cubic" hold="true">
  <points>
    <p t="0.0000" x="-160.38" y="-1308.22" z="603.61" rx="0" ry="-0.34" rz="72.81" fov="90"/>
    ...
  </points>
</campath>
```

One keyframe every `flySampleStride` ticks, each one placed `flyDistance` back along the path
the grenade had already travelled and raised by `flyHeight`, looking at where the grenade is at
that moment. Cubic interpolation smooths the rest. At the throw the recorder runs
`mirv_campath load`, then `mirv_campath offset current#0`, which pins the first keyframe to the
current moment so the path does not depend on absolute demo time, and then
`mirv_campath enabled 1`. The take ends with `mirv_campath enabled 0` and a clear.

Putting the camera on ground the grenade has already flown through is the same trick as
[Choosing the angle](#choosing-the-angle), and it has the same benefit: that space is known to
be open, because the grenade was just there. The only unproven part is the `flyHeight` lift.

In this mode the flight is never trimmed and the clip is one continuous take, since the flight
is the thing being filmed. HLAE needs at least four keyframes to enable a path, so a grenade
that barely moved falls back to the normal landing shot.

### Choosing the angle

The landing camera used to sit on the straight line from the landing spot back to the thrower.
That is wrong often enough to be annoying: a grenade thrown over a wall arcs over it, but the
straight line at camera height goes through it, so the shot is a close up of a wall. Same story
with a smoke thrown through a window, where the thrower is outside and the smoke is inside.

The demo already carries the answer. `parse_grenades` gives the projectile position on every
tick, and the grenade physically travelled that path, so the path is known to be clear. The
recorder walks backwards along it from the resting point and takes the direction the grenade
came in on, then places the camera that far back along that direction, looking at the landing.
A grenade lobbed over a wall is filmed from above and behind the arc; a smoke rolled along the
floor is filmed from along the floor.

The walk stops where the path stops being straight enough, measured as the travelled distance
against the straight line back to the landing. That keeps a bouncy tail from dragging the camera
around a corner. A near vertical drop is not used at all, since the direction would put the
camera in the ceiling, and a steep approach is levelled off at 55 degrees.

When there is not enough clean flight the old thrower line is used, which is why both modes are
still there. On the test demo 261 of 294 grenades of every kind got their angle from the flight,
and where it applied the camera moved a median of 80 units from where it used to sit.

This is a much better guess, not a guarantee. Nothing here reads the map geometry, so a shot can
still be blocked. `nades.cameraMode` set to `thrower` restores the old behaviour.

### Throws straight out of spawn

Plenty of smokes are thrown in the first second of a round. The player lines the throw up while
still frozen, walks into place, and releases the moment the round starts. Clipping those from the
round start meant the run up was missing: on the test demo a spawn throw got between 0.4 and 2.1
seconds of lead in, none of it showing the aim.

A throw made within `spawnWindowSeconds` of the round starting is recognised as a spawn throw and
gets `spawnLeadSeconds` of run up instead, reaching back into the freeze time where the aiming
actually happens. The clip still never crosses into the round before, so a short freeze time
simply shortens the run up.

That is not a rare case. On the test demo 39 of 99 smokes were thrown inside the first four
seconds of a round.

### How a throw is filmed

Each grenade becomes one clip built from these beats:

| Beat | When | What happens |
| --- | --- | --- |
| clip start | `leadInSeconds` (3 s) before the throw | Camera locks to the thrower, recording starts |
| `zoom` | `freezeLeadSeconds` (1 s) before the throw | `mirv_fov 22.5`, roughly 4x magnification on the aim point |
| `unzoom` | `freezeSeconds` (1 s) later, right on the throw | `mirv_fov default` |
| throw | | Filmed from the thrower's view |
| cut to the landing | `landingCutSeconds` (0.5 s) after the throw | `spec_mode 4` frees the camera, `spec_goto` teleports it next to the landing spot so you watch the grenade arrive |
| clip end | `landingHoldSeconds` (3 s) after detonation | Recording stops |

### Long flights are trimmed

A smoke that hangs in the air for ten seconds does not need ten seconds of screen time. When the flight is long enough for the skip to pay for itself, the clip is split in two: the first part runs from the lead in through the throw, then playback jumps forward and the second part picks up `landingLeadSeconds` (3 s) before detonation, already looking at the landing spot.

| Flight | Segments | Recorded | Cut out |
| --- | --- | --- | --- |
| 2 s | 1 | 8.0 s | nothing |
| 5 s | 1 | 11.0 s | nothing |
| 10 s | 2 | 9.5 s | 6.5 s |

The split follows the same forward seek rule as highlight segmentation, so it only happens when the jump moves strictly forward. Short flights stay in one piece rather than gaining a pointless cut.

The zoom hold runs for real demo time rather than freezing the picture. A hard `demo_pause` stops demo ticks, and every command in the pipeline is scheduled with `mirv_cmd addAtTick`, so nothing would ever fire to unpause it and the recording would hang forever. Slowing the demo with `demo_timescale` does not help either: HLAE pins `host_framerate` while recording and advances the demo one step per rendered frame, so the timescale is ignored and the zoom flashes past in a couple of frames. Half a second of held demo time is the reliable option, and since the player is standing still lining up the throw it reads as a still frame anyway. Raise `freezeSeconds` if you want longer on the aim point.

The landing camera is placed `landingDistance` units from the detonation point, on the direction the grenade came in on, and angled to look straight at the spot. See [Choosing the angle](#choosing-the-angle) for how that direction is worked out and when it falls back to the throw line.

### `nades`

| Key | Default | What it does |
| --- | --- | --- |
| `leadInSeconds` | `3.0` | How long before the throw the clip starts |
| `spawnWindowSeconds` | `4.0` | A throw this soon after the round starts counts as a spawn throw |
| `spawnLeadSeconds` | `6.0` | Run up for a spawn throw, reaching back into the freeze time |
| `freezeLeadSeconds` | `1.0` | How long before the throw the zoom hold begins |
| `freezeSeconds` | `1.0` | How long the zoomed view is held |
| `zoomFov` | `22.5` | Field of view while zoomed, lower means closer |
| `landingCutSeconds` | `0.5` | How long after the throw the camera cuts to the landing spot |
| `landingLeadSeconds` | `3.0` | How much of the flight is kept before detonation when a long flight is trimmed |
| `landingHoldSeconds` | `3.0` | How long the camera stays there after detonation |
| `cameraMode` | `flight` | `flight` follows the line the grenade flew in on, `thrower` uses the throw line |
| `followFlight` | `false` | Fly behind the grenade, same as `-fly` |
| `flyDistance` | `110.0` | How far behind the grenade the chase camera sits |
| `flyHeight` | `20.0` | How high above its path the chase camera sits |
| `flySampleStride` | `4` | How often the flight is sampled into a keyframe |
| `minimumApproach` | `60.0` | How much clean flight is needed before that direction is trusted |
| `maximumGroupSpread` | `600.0` | How far apart landings can be and still share one shot |
| `landingDistance` | `220.0` | Camera distance from the detonation point |
| `landingHeight` | `90.0` | How far the camera is raised, `thrower` mode only |
| `calloutSampleStride` | `64` | Tick spacing when sampling callouts, lower is more accurate and slower |

---

## Importing demos

```bash
HighlighterCS2.exe -demoget
```

It looks in your Downloads folder and in the two CS2 demo folders. The `demos` folder itself is
not searched, because anything in there you already put there yourself.

FACEIT hands out demos as `.dem.zst` archives with names like
`1-9b7f9f3a-0f64-428e-9412-76baeeecd686-1-1.dem.zst`, which tell you nothing. Each file found is
unpacked, its header is read for the map and the server, and you are asked what to call it. The
name you type becomes `demos/<name>.dem`. Press enter to take the suggestion, type `skip` to pass
on one, or `stop` to finish early.

```
  1/3  Unpacking 1-9b7f9f3a-0f64-428e-9412-76baeeecd686-1-1.dem.zst
       · de_dust2 from FACEIT 191 MB
       Name for this demo (skip to pass, stop to finish) [dust21509]:
```

`.dem.gz` and `.dem.bz2` are handled as well, and a plain `.dem` sitting in the game folder is
copied rather than moved. Nothing is ever deleted from Downloads or from the game folder.

Imported files are noted in `work/imported_demos.json` by name and size, so a second run only
offers what is genuinely new. Change the file and it counts as new again.

## Updating

```bash
HighlighterCS2.exe -update
```

It reads the latest release of [this repository](https://github.com/Sevelinish/CS2Prak-HighlightMaker),
compares the tag with the version you are running, and stops there if you are already current.
If there is something newer it prints the version, the size and the release notes, downloads the
zip and installs it.

A program cannot overwrite itself while it is running, so the install happens in two parts. The
zip is unpacked into `work/update/staged` and checked for `HighlighterCS2.exe` and `_internal`,
so a wrong or truncated download is rejected before anything is touched. Then an installer
script is started detached, the program exits, and the script waits for the process to be gone
before replacing the files. The next start says which version was installed.

**What is replaced:** `HighlighterCS2.exe`, `_internal`, `README.md` and `docs`.

**What is kept:** `config.json`, the output folder, `demos`, `tools`, `work` and `logs`. Your
clips, your demos, the downloaded HLAE and ffmpeg, and every setting you changed stay exactly
as they were.

If the old process somehow never exits, the installer gives up and changes nothing rather than
replacing files under a running program. Either way `logs/update.log` says what happened.

| Setting | Default | What it does |
| --- | --- | --- |
| `update.releaseApiUrl` | the repository releases feed | Where to look for a newer version |
| `update.assetPattern` | `*.zip` | Which release file holds the program |
| `update.checkOnStart` | `false` | Reserved for a launcher that wants a check on every run |
| `update.relaunchAfterInstall` | `false` | Start the new version once it is installed |
| `update.timeoutSeconds` | `600` | Network timeout for the download |

Running from source there is nothing to replace, so `-update` says so and points at `git pull`.

## Plugin API

HighlighterCS2 can run headless and be driven by another program. The API is written
specifically for [CS2Prak-Launcher](https://github.com/Sevelinish/CS2Prak-Launcher): the
launcher lists the rounds, the user picks what they want, and the plugin records it.

```bash
HighlighterCS2.exe --api http --api-port 0 --api-endpoint-file work/api.json
```

The process prints one JSON line with the base URL and the bearer token, then serves the API
on loopback. A stdio transport is available with `--api stdio` for launchers that would
rather own the process and talk over a pipe.

| Command group | What it covers |
| --- | --- |
| `handshake`, `system.probe` | Identity, capabilities, whether CS2, HLAE and ffmpeg are ready |
| `demos.*`, `match.*` | Demo list, map, tick rate, rounds, players, kills |
| `highlights.find`, `grenades.find` | The tables the user picks from, with stable identifiers |
| `plan.preview` | What will be recorded, before the game launches |
| `jobs.*` | Queue a recording, follow its stages, cancel it, collect the files |
| `session.*` | The game kept open between jobs, and closing it |
| `update.*` | Check for a newer release and install it |
| `config.*` | Read, describe and patch every setting |
| `output.*` | The videos already written |

Recording is asynchronous. `jobs.submit` returns a job id immediately, and the job publishes
events through eight stages until the files are on disk. Passing `keepGameOpen` on a job leaves
CS2 running so the next job skips the startup.

The full command reference is in [docs/API.md](docs/API.md).

## Keeping the game open

Starting Counter-Strike 2 takes 60 to 120 seconds, and on a short batch that is most of the
wait. The `-exit0` flag leaves the game running when the recording is done, so the next batch
goes straight to recording.

```bash
HighlighterCS2.exe match.dem -p s1mple -exit0
```

When the last clip finishes the game does not quit. The demo is closed with `disconnect` and
Counter-Strike 2 goes back to its main menu, so nothing is left playing on screen.

Reusing a game means sending it console commands after that, and the game is launched with a
console port on loopback for exactly this. The port is opened only when the game is being kept
open, only for the lifetime of that game, and it carries a password generated for that launch.
Run the program again and it finds the running game through a marker in
`work/warm_session.json`, writes the new scripts, and sends `exec highlighter_session` followed
by `playdemo` down that port. That is the same order a cold launch uses, so the demo starts at
tick zero and the schedule fires normally. Any demo can be handed over this way, not only the
one that was recorded before.

The port is probed right after the game starts. If this build of CS2 does not open one, the
program falls back to the older approach for that session: the demo stays loaded, rewinds to
the start, and a listener made of `mirv_cmd addAtTick` entries polls for a cfg the next run
drops in. It works, but the demo keeps playing in the background. Set
`recording.handoverChannel` to `demo` to choose that on purpose, or to avoid opening a port.

A fresh game is launched anyway, without failing anything, when the resolution or window mode
changed, when the warm window has run out, or when the running game does not answer. In that
case the stale game is closed first, since a second CS2 cannot start alongside it.

Recording is finished when the take files are complete, not when the game exits. The wait only
starts counting once the first frames are written, so the two minutes CS2 spends loading do not
count against it. See [Why saving used to be slow](#why-saving-used-to-be-slow).

The program prints how long the session stays usable when it finishes. Close the game yourself
when you are done.

| Setting | Default | Meaning |
| --- | --- | --- |
| `recording.keepGameOpen` | `false` | Same as passing `-exit0` every time |
| `recording.handoverChannel` | `netcon` | `netcon` closes the demo, `demo` leaves it playing |
| `recording.handoverIntervalSeconds` | `1.0` | How often the running game looks for a new script, `demo` channel only |
| `recording.handoverTimeoutSeconds` | `120.0` | How long to wait for the running game to produce |
| `game.netconPort` | `0` | Console port for a kept open game, `0` picks a free one |
| `recording.takeSettleSeconds` | `2.0` | How long a take must stop growing before it counts as done |
| `recording.takeStallSeconds` | `120.0` | How long to wait on a recording that stopped producing |

Recording rewrites the CS2 video settings and puts them back when the game closes. While the
game is kept open that restore is deferred to the next cold launch, and the backups stay next
to the originals with a `.highlighter-backup` suffix.

## Why saving used to be slow

HLAE does not write the video itself. It pipes raw frames to `ffmpeg.exe` child processes, one
per stream. `mirv_streams record end` only closes that pipe: ffmpeg still has to encode
whatever is queued and then write the mp4 index, which lands at the end of the file.

The old code told the game to `quit` on the same line as `mirv_streams record end`, and treated
`cs2.exe` disappearing as the end of the recording. On Windows the ffmpeg children outlive their
parent, so saving started on top of encoders that were still running: the assembler read files
that were still growing and competed with them for the disk. With `-exit0` the game never
quits, so the program waited for the take files to stop changing instead, which is the correct
signal, and saving was instant. Same work, different waiting.

Both modes now use the correct signal:

- Recording is finished when every segment has a video file and the total size has stopped
  changing for `takeSettleSeconds`. If the game disappears first, the takes are given time to
  finish writing rather than being read mid-flight.
- The `quit` is no longer glued to the end of the recording. It is scheduled a few seconds of
  demo time later, so HLAE gets to close its streams cleanly, and the program closes the game
  itself if that never happens. Like every other timed command it runs through a cfg, because a
  bare `quit` handed to `mirv_cmd addAtTick` is silently ignored.
- Only then does the assembler run, over files nothing else is touching.

The total wall clock is about the same, since the encoders have to finish either way. What
changes is that the waiting now happens in the recording stage where it belongs, saving is
quick, and no clip is ever assembled from a half written take.

## The kill from the other side

```bash
HighlighterCS2.exe match.dem -p s1mple -enemy
```

The clip opens the way it always did, following the player. Then the same moment plays again
from each victim's own eyes, one after another, in the order they died, all inside the same
video file.

The demo only plays forwards, and everything is driven by tick callbacks, so the same stretch
cannot be filmed twice in one run. The recording is split into **passes** instead. Pass one
records every player view. At the end of it the schedule is cleared, the next pass is scheduled
and the demo rewinds. Each pass records a set of takes that do not overlap each other.

Victim views of kills that are seconds apart share one pass. Kills a fraction of a second apart
need a pass each, since their windows overlap. A four kill round with two tight pairs comes out
as three passes: the player view, then two victims, then the other two.

Every take lands in its own folder, and the clip is assembled from its segments in order, so the
file reads player view first and victims after. The passes are only about when the game records
them, not about what ends up in the video.

Two guards come out of the same machinery that keeps a warm game alive. A pass script always
clears the schedule before it adds its own entries, and it rewinds to a tick strictly before its
first entry, so nothing can retrigger the callback that caused the rewind.

| Setting | Default | What it does |
| --- | --- | --- |
| `recording.recordEnemyView` | `false` | Same as passing `-enemy` every time |
| `recording.enemyLeadSeconds` | `2.5` | How long before the kill the victim view starts |
| `recording.enemyHoldSeconds` | `1.5` | How long it keeps rolling after the kill |

Recording takes longer, because the demo is replayed once per pass. `-enemy` applies to
highlights only, grenade modes ignore it.

## What ends up in the output folder

Every run writes into `Highlighter/<demo>/`. Without `-one-file` the clips sit there directly.
With `-one-file` they go into `parts/` and only the joined video sits at the top.

Two runs of the same demo with different flags used to leave both layouts side by side, so a
folder could hold a ten second clip from an earlier run next to an eighteen second clip of the
same name under `parts/`. That reads as if the join broke when it did not.

A run now retires the copies it has superseded: a clip of the same name left by the other layout,
and a joined video left behind when `-one-file` is off. Only files this run replaced are removed,
anything with a different name is left alone, and the count is reported on the saving step.

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

Segments are recorded as separate files and joined by ffmpeg through the concat demuxer, with no re-encoding. The same mechanism joins whole clips when `-one-file` is used.

## Configuration

Type `config` in the prompt to edit `config.json` in the console, see
[Editing the config](#editing-the-config). Any other text editor works too, the file is plain
JSON and is read fresh on every run.

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
| `closeGameWhenDone` | `true` | Close CS2 after the last clip, ignored when `keepGameOpen` is on |
| `openOutputFolder` | `true` | Open the clip folder when finished |
| `singleFile` | `false` | Join every clip into one video, same as `-one-file` |
| `recordEnemyView` | `false` | Replay every kill from the victim's eyes, same as `-enemy` |
| `enemyLeadSeconds` | `2.5` | Recorded time before a kill in the victim view |
| `enemyHoldSeconds` | `1.5` | Recorded time after a kill in the victim view |
| `keepGameOpen` | `false` | Leave CS2 running for the next batch, same as `-exit0` |
| `handoverChannel` | `netcon` | `netcon` closes the demo, `demo` leaves it playing |
| `handoverIntervalSeconds` | `1.0` | How often the running game looks for a new script |
| `handoverTimeoutSeconds` | `120.0` | How long to wait for the running game to produce |
| `takeSettleSeconds` | `2.0` | How long a take must stop growing before it counts as done |
| `takeStallSeconds` | `120.0` | How long to wait on a recording that stopped producing |

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
| `netconPort` | `0` | Console port for a kept open game, `0` picks a free one |
| `steamEnvironment` | `SteamAppId` and friends | Environment variables, without them CS2 will not reach Steam |
| `consoleVariables` | see config | Cvars set before recording |
| `gameStartupTimeoutSeconds` | `300` | How long to wait for `cs2.exe` to appear after injection |
| `recordingTimeoutMinutes` | `120` | When to force the game closed |
| `closeGraceSeconds` | `30` | How long to let the game close itself before stopping it |
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

### `update`

| Key | Default | What it does |
| --- | --- | --- |
| `releaseApiUrl` | the repository releases feed | Where `-update` looks for a newer version |
| `assetPattern` | `*.zip` | Which release file holds the program |
| `checkOnStart` | `false` | Reserved for a launcher that wants a check on every run |
| `relaunchAfterInstall` | `false` | Start the new version once it is installed |
| `timeoutSeconds` | `600` | Network timeout for the download |

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

With `applyHighGraphics: true` the application edits `cs2_video.txt` in the `userdata` folder,
and it is careful about it because those are your settings:

* it changes **only keys that already exist**, inventing none, so the file never breaks
* it writes down the old value of every key it touched, in `work/graphics_preset.json`
* it sets `Autoconfig: 0` so CS2 does not overwrite the settings on startup
* afterwards it puts back **only those keys**, and only where the value is still the one it wrote

That last point is the one that matters. The file is never replaced wholesale, so anything you
changed yourself in between is kept: a setting you edited by hand is recognised as yours and left
alone, and settings the recorder never touched are not affected at all. If the program is killed
before it can tidy up, the record survives and the next run puts everything back.

`restoreGraphicsOnExit: false` keeps the recording preset in place on purpose, and
`applyHighGraphics: false` means your settings are never touched at all, at the cost of recording
at whatever quality you play on.

Turn `applyHighGraphics` off if you would rather record with your own settings. Note that CS2 rewrites this file while running, so the restore only wins once the game has closed.

### Warmup in demos

The `is_warmup_period` field the parser exposes came back as `False` in every CS2 demo tested, knife warmup round included. It cannot be trusted. The start of the match is taken from the `begin_new_match` event instead, and everything before it is discarded.

## Project layout

```
src/highlighter/
├── application.py       the whole scenario
├── cli.py               command line parsing
├── entrypoint.py        turning parsed arguments into a run
├── version.py           the version everything reports and compares against
├── editor/              the full screen editor the prompt opens for config.json
│   ├── buffer.py        the text being edited, lines and cursor
│   ├── screen.py        the frame: title bar, gutter, text, status, help
│   ├── highlight.py     colouring JSON a line at a time
│   ├── validator.py     parse and schema check before anything is written
│   ├── viewport.py      history.py  theme.py
│   └── editor.py        config_editor.py  the loop and the config.json wiring
├── library/             what the program remembers about each demo
│   ├── profile.py       the map, the roster and how a demo is keyed
│   ├── inspector.py     reading a header and a player table, or a parsed match
│   ├── index.py         the book on disk, work/demo_index.json
│   ├── librarian.py     reading only what is new, within a time budget
│   └── directory.py     library.py  the nicknames the prompt offers
├── shell/               the prompt the exe opens when it is started bare
│   ├── grammar.py       the arguments, values and words the prompt knows
│   ├── suggester.py     what to offer for the word under the cursor
│   ├── prompt.py        the line editor and the keys it answers to
│   ├── layout.py        fitting prompt, text, ghost and hint into the width
│   ├── document.py      the line being edited
│   ├── reader.py        keys.py  renderer.py  terminal.py  history.py
│   └── router.py        runner.py  session.py  catalogue.py  launcher.py
├── importing/           bringing new demos in from Downloads and the game folders
│   ├── sources.py       where to look
│   ├── archives.py      unpacking zst, gz and bz2
│   ├── ledger.py        what was imported already
│   └── importer.py  command.py
├── update/              checking GitHub and installing a newer release
│   ├── checker.py       what the newest release is
│   ├── payload.py       downloading, unpacking and verifying it
│   ├── swap.py          the installer script that runs after we exit
│   └── installer.py  service.py  command.py
├── api/                 the plugin API built for CS2Prak-Launcher
│   ├── contract.py      protocol version, command and capability catalogue
│   ├── service.py       the command implementations
│   ├── selection.py     the filter model shared by every command
│   ├── jobs.py          the job queue, states and cancellation
│   ├── events.py        the event journal and the progress reporter
│   ├── recorder.py      the headless recording pipeline
│   └── transport/       http.py  stdio.py
├── config/              config.json schema, loading, migrations
│   └── schema.py  repository.py  migrations.py
├── domain/              the domain model
│   ├── kill.py  round.py  match.py  player.py  team.py  weapon.py
│   ├── flight.py        the path a grenade actually flew
│   ├── camera.py        picking the angle the landing is filmed from
│   └── highlight.py  grenade.py  geometry.py
├── demo/                reading .dem
│   ├── reader.py        demoparser2 into Match
│   ├── timeline.py      cutting off the warmup
│   └── locator.py       finding demos by folder and by name
├── detection/           finding moments
│   ├── engine.py  context.py  registry.py  rule.py  player_filter.py
│   └── rules/           multi_kill  weapon_feat  clutch  trick_shot
├── plan/                the clip plan, the contract between stages
│   ├── grouping.py      folding overlapping moments into one clip
│   ├── passes.py        splitting takes into rewind passes
│   └── models.py  builder.py  segmenter.py  writer.py
├── recording/           everything HLAE related
│   ├── mirv_script.py   cfg generation
│   ├── warm_session.py  the game kept open between recordings
│   ├── take_watcher.py  knowing a recording finished without the game exiting
│   └── script_writer.py graphics.py  launcher.py  game_process.py  session.py
├── media/               assembling the final mp4
│   └── assembler.py  concat.py  reel.py  encoders.py  crosshair.py  output_library.py
├── provisioning/        downloading HLAE and ffmpeg
│   └── toolchain.py  downloader.py  archive.py  release_resolver.py  hlae_installation.py
├── game/                locating Steam and CS2
│   └── steam.py  installation.py
└── presentation/        the console
    ├── banner.py        the header
    ├── steps.py         the numbered steps and their timings
    ├── summary.py       the table of what was written
    └── highlight_table.py  grenade_table.py  selector.py  selection_parser.py  demo_picker.py
```

The `branding` package next to `build.py` is build time only. It turns `logo.svg` into the
multi size `.ico` that PyInstaller embeds in the executable, without any imaging dependency:
it reads the straight line paths out of the SVG, fills them with an even odd scanline, and
writes the icon directory itself.

To add your own detection rule: subclass `HighlightRule`, set `name`, add the class to `AVAILABLE_RULES` in `detection/registry.py` and a weight to `tagWeights`.

## Tests

```bash
.venv\Scripts\python -m pytest
```

Nearly eight hundred tests. They cover argument parsing, demo lookup, detection and scoring, segmentation, the guard against seek loops, mirv script generation, encoder selection, config migrations, HLAE install integrity, watching the game process, the demo index and its nickname lookup, the config editor with its buffer, viewport, colouring and validation, and the prompt with its line editing and suggestions.

## Requirements

* Windows
* Counter-Strike 2
* Python 3.11 or newer, only to run from source
* Free space for the raw takes in the `work` folder

HLAE needs CS2 started with `-insecure`. That is the normal mode for watching demos and it does not affect your account, but you cannot join an online match while in it.
