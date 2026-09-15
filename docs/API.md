# HighlighterCS2 Plugin API

This API is written specifically for **CS2Prak-Launcher** (https://github.com/Sevelinish/CS2Prak-Launcher).

It is the supported integration surface of HighlighterCS2. The launcher drives the whole
pipeline through it: list demos, read rounds and players, detect highlights, read grenade
throws, let the user pick what they want, then queue a recording job and follow it to the
finished `.mp4` files.

The API is versioned independently of the command line. The command line stays a human tool,
the API stays a machine tool, and neither is allowed to break the other.

| Property | Value |
| --- | --- |
| Plugin id | `highlightercs2` |
| Plugin kind | `demo-recorder` |
| Protocol version | `1.0` |
| Transports | `http`, `stdio` |
| Host application | CS2Prak-Launcher |
| Platform | Windows |

## Contents

1. [Starting the plugin](#starting-the-plugin)
2. [Message format](#message-format)
3. [HTTP transport](#http-transport)
4. [stdio transport](#stdio-transport)
5. [Identifiers](#identifiers)
6. [The selection object](#the-selection-object)
7. [Per job overrides](#per-job-overrides)
8. [Jobs](#jobs)
9. [Keeping the game open](#keeping-the-game-open)
10. [Events](#events)
11. [Command reference](#command-reference)
12. [Error codes](#error-codes)
13. [Integration recipe](#integration-recipe)
14. [Guarantees and limits](#guarantees-and-limits)

## Starting the plugin

The plugin is the same executable as the interactive app. The `--api` flag replaces the
interactive run with an API server.

```bash
HighlighterCS2.exe --api http --api-port 0 --api-endpoint-file work/api.json
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--api [http\|stdio]` | `http` when the flag is present without a value | Serve the API instead of running the app |
| `--api-host HOST` | `127.0.0.1` | Address the HTTP transport binds to |
| `--api-port PORT` | `8787` | Port the HTTP transport binds to. `0` picks a free port |
| `--api-token TOKEN` | generated | Bearer token clients must send |
| `--api-endpoint-file PATH` | none | Write the base URL and token to this JSON file once the API is up |
| `--api-no-events` | off | Stop the stdio transport from pushing job events |
| `-v`, `--verbose` | off | Write debug lines to `logs/highlighter.log` |

### The ready line

The first line the process writes to stdout is a single JSON object. Read it, then stop
reading stdout if you use the HTTP transport.

```json
{
  "kind": "ready",
  "plugin": "HighlighterCS2",
  "version": "1.0.0",
  "protocol": "1.0",
  "pid": 12940,
  "root": "D:\Games\HighlighterCS2",
  "configFile": "D:\Games\HighlighterCS2\config.json",
  "transport": "http",
  "baseUrl": "http://127.0.0.1:61918",
  "host": "127.0.0.1",
  "port": 61918,
  "token": "0Gk1nT..."
}
```

Passing `--api-port 0` and reading the port back from this line is the recommended way to
avoid port collisions with the launcher's own server on `127.0.0.1:5000`.

`--api-endpoint-file` writes the same object to a file, which is easier to consume when the
launcher starts the plugin detached and does not capture stdout.

### Stopping the plugin

Send `shutdown`. With no `force` flag it refuses while a recording is running and tells you
so. Killing the process is safe at any point except during a recording, where it leaves CS2
open and the take folder half written.

## Message format

Every call is one request object and one response object, on both transports.

### Request

```json
{
  "id": "any string you choose",
  "command": "highlights.find",
  "payload": { "demo": "match.dem" }
}
```

`id` is optional. When omitted the plugin generates one and returns it. `payload` is
optional and defaults to an empty object.

### Response

```json
{
  "kind": "response",
  "id": "any string you choose",
  "command": "highlights.find",
  "protocol": "1.0",
  "ok": true,
  "elapsedMs": 412,
  "data": { "count": 14 }
}
```

On failure `data` is absent and `error` is present.

```json
{
  "kind": "response",
  "id": "req-7",
  "command": "demos.inspect",
  "protocol": "1.0",
  "ok": false,
  "elapsedMs": 3,
  "error": {
    "code": "demo_not_found",
    "message": "No demo called 'nope.dem' was found",
    "details": {
      "requested": "nope.dem",
      "searchDirectories": ["D:\Games\HighlighterCS2\demos"]
    }
  }
}
```

Check `ok` first. `error.code` is a stable machine value, `error.message` is human text that
may change between versions, `error.details` carries whatever is useful for that code.

### Field naming

Request and response fields are `camelCase`. `config.json` keys are `camelCase` as well, so
a config document taken from `config.get` can be sent straight back into `config.patch` or
into a job's `overrides`.

SteamID64 values are sent as strings, because they do not fit a 32 bit integer and JavaScript
loses precision on them. Account ids, slots and tick numbers are plain integers.

## HTTP transport

Bound to loopback. Every route except `/health` requires the bearer token.

```
Authorization: Bearer <token>
Content-Type: application/json
```

| Method | Route | Body | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | none | Liveness check, no token needed |
| GET | `/v1/handshake` | none | Shortcut for the `handshake` command |
| POST | `/v1/command` | full request envelope | Universal entry point |
| POST | `/v1/<command>` | the payload only | One route per command, for example `/v1/jobs.submit` |
| GET | `/v1/events?since=&jobId=&waitSeconds=&limit=` | none | Long poll for job events |
| GET | `/v1/events/stream?since=&jobId=` | none | Endless newline delimited event stream |

`POST /v1/<command>` takes the payload directly, without the envelope:

```
POST /v1/highlights.find
{ "demo": "match.dem", "selection": { "players": ["s1mple"] } }
```

The response is always the full envelope, whichever route was used.

### HTTP status codes

The status mirrors `error.code` so a client can react before parsing the body. A successful
call is always `200`.

| Status | When |
| --- | --- |
| 200 | `ok` is true, or the job was cancelled |
| 400 | Malformed JSON, bad payload, unknown enum value |
| 401 | Missing or wrong token |
| 404 | Unknown route, unknown command, unknown demo, unknown job |
| 409 | The selection matched nothing |
| 413 | Request body over 4 MB |
| 422 | The demo could not be parsed, or the config document is invalid |
| 424 | CS2, HLAE or ffmpeg is missing |
| 426 | Protocol major version mismatch |
| 502 | A tool download failed |
| 500 | Recording or encoding failed, or an unexpected error |

### Browser origins

The launcher renders its UI in WebView2 on `http://127.0.0.1:5000`, which is a different
origin from the plugin. Preflight requests are answered and `Access-Control-Allow-Origin` is
returned for loopback origins only. Any other origin gets no CORS grant.

## stdio transport

One JSON object per line in, one JSON object per line out. UTF-8, newline terminated, no
pretty printing. Nothing else is written to stdout, so the stream stays parseable.

```
> {"id":"1","command":"handshake","payload":{"clientName":"CS2Prak-Launcher"}}
< {"kind":"response","id":"1","command":"handshake","ok":true,...}
```

Job events are pushed on the same stream as they happen, unless `--api-no-events` was passed.
Tell them apart by the `kind` field:

| `kind` | Meaning |
| --- | --- |
| `response` | The answer to a request you sent, matched by `id` |
| `event` | An unsolicited job event |

A malformed line produces a `bad_request` response and the session continues. Blank lines are
ignored. The session ends when stdin closes.

Use stdio when the launcher spawns the plugin as a child process and owns its lifetime. Use
HTTP when several parts of the launcher talk to one long lived plugin, or when the UI layer
needs to call it directly.

## Identifiers

Every highlight and every grenade carries an `id`. The id is derived from the demo content,
not from list order, so it survives re-parsing, re-sorting and filtering. Store the ids the
user picked and send them back in `selection.ids`.

| Kind | Shape | Example |
| --- | --- | --- |
| Highlight | `h-<round>-<steamId64>` | `h-7-76561198717658391` |
| Grenade | `g-<kind>-<throwTick>-<steamId64>` | `g-smoke-10206-76561198951318036` |

A player has at most one highlight per round, so the highlight id is unique inside a demo. A
grenade id includes the throw tick, so several throws by the same player in the same round
stay distinct.

## The selection object

`selection` is the single filter model used by `highlights.find`, `grenades.find`,
`plan.preview` and `jobs.submit`. Every field is optional. Fields combine with AND. An empty
selection means everything.

```json
{
  "ids": ["h-7-76561198717658391"],
  "rounds": [3, 7, 11],
  "roundRange": { "from": 1, "to": 15 },
  "players": ["s1mple", "76561198717658391"],
  "tags": ["awp_double", "clutch_1v3"],
  "weapons": ["awp"],
  "grenadeKinds": ["smoke"],
  "landingPlaces": ["window"],
  "minimumScore": 12,
  "minimumKills": 3,
  "order": "round_asc",
  "limit": 10
}
```

| Field | Type | Applies to | Meaning |
| --- | --- | --- | --- |
| `ids` | string or string[] | both | Exact items, from a previous `find` call |
| `rounds` | number or number[] | both | Keep only these round numbers |
| `roundRange` | `{from,to}` | both | Keep rounds inside this inclusive range |
| `players` | string or string[] | both | SteamID64, exact name, or a case insensitive substring |
| `tags` | string[] | highlights | Keep rounds that carry any of these detection tags |
| `weapons` | string[] | highlights | Keep rounds where any kill used one of these weapons |
| `grenadeKinds` | string[] | grenades | `smoke`, `flash`, `he`, `molotov`, `decoy` and their aliases |
| `landingPlaces` | string[] | grenades | Case insensitive substring match on the callout |
| `minimumScore` | number | highlights | Keep rounds scoring at least this |
| `minimumKills` | number | highlights | Keep rounds with at least this many kills |
| `order` | string | both | `round_asc` (default), `score_desc`, `time_asc` |
| `limit` | number | both | Keep at most this many items. `0` means no limit |

Names are matched leniently on purpose: a player called `-n1clxe` is found by `-n1clxe`, by
`n1cl`, or by their SteamID64. When a partial name is ambiguous the filter keeps every match
rather than guessing.

### Worked example

Record the highlights of one player in rounds 3, 7 and 11:

```json
{
  "demo": "match.dem",
  "source": "highlights",
  "selection": {
    "players": ["76561198717658391"],
    "rounds": [3, 7, 11]
  }
}
```

Record every smoke that landed on Window:

```json
{
  "demo": "match.dem",
  "source": "grenades",
  "selection": {
    "grenadeKinds": ["smoke"],
    "landingPlaces": ["window"]
  }
}
```

## Per job overrides

`overrides` is a partial `config.json` document merged over the stored configuration for one
job only. Nothing is written to disk and the next job starts from the stored values again.
Any key of `config.json` can be overridden, and nested objects merge key by key instead of
being replaced wholesale.

```json
{
  "overrides": {
    "recording": { "fps": 120, "width": 2560, "height": 1440, "singleFile": true },
    "encoding": { "quality": 16 },
    "nades": { "freezeSeconds": 1.5 }
  }
}
```

The `version` key is ignored in a patch and cannot be rewritten.

Use `config.describe` to build a settings screen without hard coding the field list. It
returns every setting with its dotted path, kind, unit, default and a one line description.

```json
{
  "fields": [
    {
      "path": "recording.fps",
      "kind": "integer",
      "unit": "fps",
      "description": "Frames per second of the captured video",
      "default": 60
    }
  ]
}
```

Kinds are `boolean`, `integer`, `number`, `text`, `choice`, `path`, `list` and `map`.

## Jobs

Recording launches Counter-Strike 2, plays the demo, captures it through HLAE and encodes the
result with ffmpeg. It takes minutes, so it is asynchronous.

`jobs.submit` validates the request, queues it and returns immediately with a `jobId`. One
job runs at a time, because CS2 and HLAE cannot record two demos at once. The rest wait in
the queue and report their `queuePosition`.

### States

| State | Meaning |
| --- | --- |
| `queued` | Accepted, waiting for the recorder |
| `running` | The recorder owns it |
| `succeeded` | Finished, `result` is filled in |
| `failed` | Stopped on an error, `error` is filled in |
| `cancelled` | Stopped on request, no error |

`succeeded`, `failed` and `cancelled` are final.

### Stages

A running job moves through eight stages. `progress.stage` is the current one and
`progress.total` is eight.

| Stage | Title | What happens |
| --- | --- | --- |
| 1 | Reading `<demo>` | The demo is parsed, or served from cache |
| 2 | Selecting `<source>` | The selection is applied |
| 3 | Planning clips | Segments, camera beats and the plan file are written |
| 4 | Preparing HLAE and ffmpeg | Tools are located, downloaded once if missing |
| 5 | Starting Counter-Strike 2 | HLAE injects the hook, or the running game is reused |
| 6 | Recording N clips | The demo plays, the takes are written, then the game is closed |
| 7 | Saving videos | Takes are encoded into the output folder |
| 8 | Opening the output folder | Skipped when `recording.openOutputFolder` is false |

Stage 4 can take a long time on the very first run, because HLAE and ffmpeg are downloaded.
Stage 5 covers the CS2 startup, which is normally 60 to 120 seconds on its own, unless a warm
session is reused. See [Keeping the game open](#keeping-the-game-open).

### Cancellation

`jobs.cancel` behaves differently depending on the state:

- A `queued` job is cancelled instantly and never starts.
- A `running` job is asked to stop, and CS2 is closed so the recorder is not left waiting.
  Takes already written are left on disk, and the job settles on `cancelled` shortly after.
- A final job is returned unchanged.

A cancelled job carries no `error`. Treat `cancelled` as a normal outcome, not a failure.

## Keeping the game open

Starting Counter-Strike 2 costs about 60 to 120 seconds, and it is the single largest part of
a short recording. A job can leave the game running so the next one skips it.

Set `keepGameOpen` on `jobs.submit`, or `recording.keepGameOpen` in the configuration or in a
job's `overrides`. The command line spelling is `-exit0`.

### Two channels

Reusing a game means sending it console commands, and there are two ways to do that. The
channel is chosen by `recording.handoverChannel`.

**`netcon` (default).** The game is launched with a console port on loopback, protected by a
password generated for that launch. When the last clip is done the demo is closed with
`disconnect` and the game sits on the main menu, which is what the user expects to see. The
next job connects to that port and sends `exec highlighter_session` followed by `playdemo`,
exactly the order a cold launch uses.

**`demo`.** No port is opened. Instead the demo stays loaded: the last clip clears the mirv
schedule, rewinds to the start and arms a listener, which is a set of `mirv_cmd addAtTick`
entries spread across the demo, each running `exec highlighter_handover`. That cfg does not
exist yet, which costs nothing. The next job writes it last, and the running game picks it up
within `handoverIntervalSeconds`. As soon as the first take starts growing the plugin deletes
the cfg so the listener has nothing left to run.

The `demo` channel keeps the demo playing in the background, which some people find confusing.
It exists because it needs nothing from the engine beyond `exec`.

### Falling back on its own

`netcon` is probed right after the game starts. If the port never opens, the plugin switches
that session to the `demo` channel before the recording reaches its last clip, and says so in a
stage detail. Nothing fails and no job is lost.

### What the marker holds

The plugin writes a marker recording the process id, the channel, the console port, the demo,
the resolution and how long the session stays usable. The console password is kept in the
marker file only and is never returned by the API.

### What happens at the start of the next job

The process must still be alive, the window must be the same size and mode, and the session
must not have expired. A `netcon` session accepts any demo, because it can load one. A `demo`
session only accepts the demo that is already loaded.

### When a fresh game is launched anyway

The plugin launches a fresh game, without failing the job, when:

- there is no marker, or the process behind it is gone
- the resolution or window mode differs, or a `demo` session is asked for another demo
- the warm window has run out
- the console port does not answer, or the running game produces nothing within
  `handoverTimeoutSeconds`

In the last case the stale game is closed first, because a second CS2 cannot be started
alongside it.

### How long a session stays warm

On the `netcon` channel the game waits on the main menu and the window is a formality, sized
from the demo length and reported as `secondsLeft`.

On the `demo` channel the rewind means the demo replays from the start and the listener is
armed for that playback, so the window really is about one demo length. When it runs out the
demo ends, the game returns to the menu and the next job launches a fresh one.

### How a recording is known to be finished

Not by the game exiting. HLAE pipes raw frames to `ffmpeg.exe` child processes, and those keep
encoding after the last frame and write the mp4 index at the very end. On Windows they outlive
the game, so a job that assembled as soon as `cs2.exe` disappeared was reading files that were
still being written.

Every job, warm or not, waits for the take files instead: done when every segment has a video
file and the total size has stopped changing for `takeSettleSeconds`. If the game disappears
first, the takes are still given time to finish. If nothing changes for `takeStallSeconds` the
plugin stops waiting and encodes whatever was captured.

The `quit` is scheduled a few seconds of demo time after the last clip rather than on the same
line, so HLAE can close its streams cleanly, and the plugin closes the game itself if that
never happens.

### Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `recording.keepGameOpen` | `false` | Leave the game running when a job finishes |
| `recording.handoverChannel` | `netcon` | `netcon` closes the demo, `demo` keeps it playing |
| `recording.handoverIntervalSeconds` | `1.0` | How often the running game looks for a new script, `demo` channel only |
| `recording.handoverTimeoutSeconds` | `120.0` | How long to wait for the running game to produce |
| `game.netconPort` | `0` | Console port for a kept open game, `0` picks a free one |
| `recording.takeSettleSeconds` | `2.0` | How long a take must stop growing before it counts as done |
| `recording.takeStallSeconds` | `120.0` | How long to wait on a recording that stopped producing |

### About the console port

The port is opened only when `keepGameOpen` is on, only for the lifetime of that game, and it
is bound by the engine on the local machine with a password generated per launch. Set
`game.netconPort` to pin it to a known number, or set `recording.handoverChannel` to `demo` if
you would rather no port were opened at all.

`session.get` reports the port so a launcher can show it. The password is never returned.

### Video settings while warm

Recording changes a handful of CS2 video settings and puts them back when the game closes. While
a session is warm the game still owns those files, so the restore is deferred. It happens on the
next cold launch, or on `session.release`.

Only the keys the recorder actually changed are touched, and the old value of each one is written
to `work/graphics_preset.json`. Putting them back skips any key the user has since changed
themselves, so a settings edit made between two recordings is never overwritten.

## Events

Every job publishes events to a shared journal. Each event has a monotonically increasing
`sequence`, so a client can resume exactly where it stopped.

```json
{
  "kind": "event",
  "sequence": 42,
  "jobId": "8f21c0...",
  "type": "stage.begin",
  "timestamp": 1789380456.575,
  "data": { "stage": 5, "total": 8, "title": "Launching Counter-Strike 2" }
}
```

| Type | `data` | Raised when |
| --- | --- | --- |
| `job.queued` | `queuePosition`, `request` | The job was accepted |
| `job.started` | `request` | The recorder picked it up |
| `stage.begin` | `stage`, `total`, `title` | A stage started |
| `stage.detail` | `stage`, `title`, `message` | A stage reported a detail line |
| `stage.end` | `stage`, `total`, `title`, `note` | A stage finished |
| `stage.failed` | `stage`, `total`, `title`, `note` | A stage stopped on an error |
| `plan.ready` | `plan` | The plan is built, before the game launches |
| `clip.written` | `name`, `path`, `segmentCount`, `hasAudio` | One video finished encoding |
| `job.succeeded` | `result` | The job finished |
| `job.failed` | `error` | The job stopped on an error |
| `job.cancelled` | `whileQueued` when it never ran | The job was cancelled |

Three ways to consume them:

1. Poll `jobs.events` with `since` set to the last `nextSequence` you saw.
2. Long poll the same command with `waitSeconds` up to 60. It returns as soon as anything
   arrives, or empty when the wait runs out.
3. Open `GET /v1/events/stream` and read newline delimited JSON until you close it. A blank
   line is sent periodically to keep the connection alive.

On the stdio transport events arrive by themselves, no polling needed.

The journal keeps the last 4000 events. A client that reconnects after a long silence may
find that `nextSequence` jumped, which means older events were dropped. The job document from
`jobs.get` always holds the authoritative current state, so fall back to it rather than
replaying.

## Command reference

Payload fields marked with `*` are required.

### handshake

Identify the plugin and read the full command and capability catalogue. Call it once at
startup and cache the result.

| Payload | Type | Meaning |
| --- | --- | --- |
| `clientName` | string | Your name, echoed back |
| `clientVersion` | string | Your version, echoed back |
| `protocol` | string | Protocol you speak. A major version mismatch is refused |

Returns the plugin identity, the protocol version, the `writtenFor` block naming
CS2Prak-Launcher, the transport list, the capability list, the command catalogue, the known
grenade kinds, the valid `source` values and the resolved paths.

Capabilities are `{name, supported, detail}` triples. A capability reported as
`supported: false` is documented rather than hidden, for example `concurrentRecording`, which
CS2 and HLAE do not allow.

### system.probe

Report readiness without downloading anything. Call it before offering a Record button.

Returns `ready` (true when CS2, HLAE and ffmpeg are all usable), a `tools` array of
`{name, ready, path, note}`, `gameRunning`, `warmSession`, the selected `encoder`,
`autoDownload`, the demo search directories and the output directory.

`warmSession` is the game left running by an earlier job, or `null`.

`gameRunning` is important: a recording refuses to start while CS2 is already open.

### config.get

Returns `{configFile, config}`. `config` is the exact document stored in `config.json`.

### config.describe

Returns `{fields}` as described in [Per job overrides](#per-job-overrides).

### config.patch

| Payload | Type | Meaning |
| --- | --- | --- |
| `patch` * | object | Partial config document, merged over the stored one |
| `persist` | boolean | Write it to `config.json`. Default `true` |

Returns `{configFile, persisted, config}` with the merged result. Changing detection settings
clears the cached highlight results, so the next `highlights.find` re-runs detection.

### demos.list

| Payload | Type | Meaning |
| --- | --- | --- |
| `search` | string | Case insensitive substring of the file name |
| `limit` | number | Keep at most this many |

Returns `{count, total, searchDirectories, demos}`. Demos come from the configured demo
folder and from the CS2 replay folders, newest first, duplicates removed.

Each demo is `{name, fileName, path, sizeBytes, modifiedAt}` where `modifiedAt` is a Unix
timestamp in seconds.

### demos.inspect

| Payload | Type | Meaning |
| --- | --- | --- |
| `demo` * | string | File name or full path |
| `refresh` | boolean | Re-parse instead of using the cache |

Returns `{demo, map, tickRate, serverName, roundCount, durationSeconds, players, rounds}`.
Rounds are included without their kills, which keeps the document small enough to render a
round list straight away.

The first call parses the demo and can take tens of seconds. The result is cached per file
path and modification time, so every later call on the same demo is instant. `refresh: true`
parses again and replaces the cached result.

### match.rounds

| Payload | Type | Meaning |
| --- | --- | --- |
| `demo` * | string | File name or full path |
| `rounds` | number or number[] | Only these round numbers |
| `includeKills` | boolean | Fold the kill list into each round |

Returns `{demo, count, rounds}`. Each round has `number`, `freezeEndTick`, `endTick`,
`durationSeconds`, `winner`, `endReason`, `killCount` and `roster`.

### match.players

| Payload | Type | Meaning |
| --- | --- | --- |
| `demo` * | string | File name or full path |

Returns `{demo, count, players}` sorted by kill count, each with `name`, `steamId64`,
`accountId`, `slot` and `killCount`. Use this to populate a player filter.

### highlights.find

| Payload | Type | Meaning |
| --- | --- | --- |
| `demo` * | string | File name or full path |
| `selection` | object | See [The selection object](#the-selection-object) |
| `detection` | object | Partial config document, applied to detection for this call only |

Returns `{demo, map, total, count, selection, highlights}`. `total` is how many the detector
found, `count` is how many survived the selection.

Each highlight carries `id`, `roundNumber`, `player`, `side`, `score`, `headline`,
`killCount`, `headshotCount`, `firstTick`, `lastTick`, `startSeconds`, `endSeconds`, `tags`,
`weapons` and the full `kills` array.

`tags` are `{code, label, weight}`. The code is stable and usable in `selection.tags`, the
label is display text, the weight is that tag's contribution to `score`.

### grenades.find

| Payload | Type | Meaning |
| --- | --- | --- |
| `demo` * | string | File name or full path |
| `kinds` | string or string[] | Grenade kinds to read. Defaults to all |
| `selection` | object | See [The selection object](#the-selection-object) |

Returns `{demo, map, kinds, total, count, selection, places, grenades}`. `places` is the
sorted set of callouts in the result, ready for a filter dropdown.

Each grenade carries `id`, `kind`, `roundNumber`, `thrower`, `side`, `throwTick`,
`detonateTick`, `flightSeconds`, `roundTimeSeconds`, `roundClock`, `landingPlace`, `landing`,
`throwerPosition`, `throwerAngles`, `setpos` and `setang`.

`camera` is the landing camera the recorder would use: `{mode, reason, position, angles}`.
`mode` is `flight` when it was taken from the line the grenade flew in on, or `thrower` when
there was not enough clean flight and it fell back to the line back to the thrower.
`flightSamples` says how many trajectory samples were available.

`landingPlace` comes from the map's own nav place names, so it reads as `Window`,
`BombsiteB`, `Connector` and so on, and it works on any map without a hard coded table. When
no place is close enough the value is `unknown`.

`setpos` and `setang` are ready to paste into the CS2 console to stand exactly where the
player stood and look exactly where they looked.

### plan.preview

Build the recording plan without launching anything. Use it to show the user how long the
recording will take before they commit.

| Payload | Type | Meaning |
| --- | --- | --- |
| `demo` * | string | File name or full path |
| `source` | string | `highlights` (default) or `grenades` |
| `selection` | object | See [The selection object](#the-selection-object) |
| `overrides` | object | See [Per job overrides](#per-job-overrides) |

Returns `{source, plan}`. The plan holds `demo`, `recording`, `output`, `clips` and a
`summary` of `{clipCount, segmentCount, totalSeconds}`.

`summary.mergedSources` counts how many selected items were folded into a clip they shared with
another. Grenades thrown within a few seconds of each other, and highlights from two players in
the same firefight, cover the same stretch of the demo. The recorder plays the demo once, so two
overlapping recordings would cut each other short, and those are filmed as one clip instead. Pick
four grenades in one execute and you may get one clip back rather than four.

Each clip lists its `segments` and `beats`. A segment is a continuous stretch of demo time
that is actually recorded, so more than one segment means dead time was cut out. A beat is a
timed console action inside a clip, used by grenade clips for the zoom hold and the cut to
the landing spot.

Fails with `empty_selection` when nothing matched.

### jobs.submit

| Payload | Type | Meaning |
| --- | --- | --- |
| `demo` * | string | File name or full path |
| `source` | string | `highlights` (default) or `grenades` |
| `selection` | object | See [The selection object](#the-selection-object) |
| `overrides` | object | See [Per job overrides](#per-job-overrides) |
| `label` | string | Free text carried on the job for your own bookkeeping |
| `validate` | boolean | Check the selection before queueing. Default `true` |
| `keepGameOpen` | boolean | Leave CS2 running when the job finishes so the next one skips the startup |

Returns the job document. The job is `queued` at this point.

With `validate` left on, a selection that matches nothing is refused here with
`empty_selection` instead of failing minutes later. When the demo was already read by
`highlights.find` or `grenades.find` the check is instant, because the parse is cached.

### jobs.get

| Payload | Type | Meaning |
| --- | --- | --- |
| `jobId` * | string | From `jobs.submit` |

Returns the job document: `jobId`, `state`, `request`, `createdAt`, `startedAt`,
`finishedAt`, `elapsedSeconds`, `queuePosition`, `progress`, `plan`, `result`, `error`.

`plan` is filled in once stage 3 completes, which is the first moment you can show the user
exactly what is being recorded.

### jobs.list

| Payload | Type | Meaning |
| --- | --- | --- |
| `state` | string | Keep only jobs in this state |
| `limit` | number | Keep at most this many |

Returns `{count, busy, jobs}`, newest first. `busy` is true while a job is running. The
plugin keeps the last 50 jobs and drops finished ones beyond that.

### jobs.events

| Payload | Type | Meaning |
| --- | --- | --- |
| `jobId` | string | Only this job's events |
| `since` | number | Return events after this sequence. Default `0` |
| `waitSeconds` | number | Block up to this long for new events. Max `60` |
| `limit` | number | Return at most this many. Default `200` |

Returns `{events, nextSequence, lastSequence}`. Pass `nextSequence` back as `since` on the
next call.

### jobs.cancel

| Payload | Type | Meaning |
| --- | --- | --- |
| `jobId` * | string | From `jobs.submit` |

Returns the job document. See [Cancellation](#cancellation).

### jobs.result

| Payload | Type | Meaning |
| --- | --- | --- |
| `jobId` * | string | From `jobs.submit` |

Returns `{jobId, state, result, error}`. The result holds `outputDirectory`,
`requestedClips`, `producedClips`, `artifacts` and `reel`.

The result also carries `reusedGame`, true when this job skipped the CS2 startup, and
`warmSession`, the session left behind for the next job or `null`.

An artifact is `{name, path, kind, durationSeconds, segmentCount, hasAudio}` where `kind` is
`clip` or `reel`. `reel` is only present when `recording.singleFile` was on, and it is the
single joined video.

`producedClips` can be lower than `requestedClips` when a take failed to capture. That is
reported as success with fewer artifacts, not as a failed job.

### session.get

Report the game left running for the next recording. Takes no payload.

Returns `{active, session}`. The session is `null` when nothing is being kept open, otherwise
it carries `pid`, `executable`, `demoPath`, `demoName`, `configDirectory`, `handoverScript`,
`width`, `height`, `fullscreen`, `startedAt`, `expiresAt`, `secondsLeft`,
`graphicsRestorePending`, `channel`, `netconPort` and `demoClosed`.

`demoClosed` is true when the game is waiting on the main menu rather than replaying a demo.

A session whose process is gone is reported as inactive and its marker is cleared.

### session.release

Close the game that is being kept open and put the CS2 video settings back.

| Payload | Type | Meaning |
| --- | --- | --- |
| none | | |

Returns `{released, pid, graphicsRestored}`, or `{released: false, reason}` when there was
nothing to release. Call it when the user is done recording for now, otherwise the game sits
on the main menu until they close it.

### update.check

Ask GitHub whether a newer HighlighterCS2 release exists. Takes no payload.

Returns `{current, latest, available, release}`. `release` carries `tag`, `name`, `assetName`,
`sizeBytes`, `publishedAt` and `pageUrl`, or is `null` when the feed could not be read.

`latest` is `null` when the newest release has no tag that parses as a version. Treat that as
"unknown", not as "up to date".

### update.install

Download the newest release and schedule it to replace the running one.

| Payload | Type | Meaning |
| --- | --- | --- |
| none | | |

Returns `{installing, check, version, script, log, relaunch}` when an update was staged, or
`{installing: false, reason, check}` when the current version is already the newest.

The plugin does not replace itself while it is running. It stages the new release, writes an
installer script and starts it detached. That script waits for this process to exit, replaces
the program files and leaves a marker the next start reports. So the caller should shut the
plugin down right after a successful `update.install`, then start it again a few seconds later.

`config.json`, the output folder, `demos`, `tools`, `work` and `logs` are excluded from the
replacement, so nothing the user produced is lost.

Fails with `internal` when the plugin is running from source rather than from a built release.

### output.list

| Payload | Type | Meaning |
| --- | --- | --- |
| `demo` | string | Limit to this demo's subfolder |

Returns `{directory, count, videos}` with every `.mp4`, `.mkv` and `.mov` under that folder.

### output.reveal

| Payload | Type | Meaning |
| --- | --- | --- |
| `demo` | string | Limit to this demo's subfolder |

Opens the folder in the file manager. Returns `{directory, opened}`.

### shutdown

| Payload | Type | Meaning |
| --- | --- | --- |
| `force` | boolean | Stop even while a recording is running |

Returns `{stopping, reason}`. When a job is running and `force` is absent, `stopping` is
false and nothing happens.

## Error codes

| Code | HTTP | Meaning | What to do |
| --- | --- | --- | --- |
| `bad_request` | 400 | The payload is malformed or a value is out of range | Fix the request |
| `unknown_command` | 404 | No such command | Check `handshake` for the catalogue |
| `unsupported_protocol` | 426 | Protocol major version mismatch | Update one side |
| `unauthorized` | 401 | Missing or wrong bearer token | Resend the token from the ready line |
| `demo_not_found` | 404 | No demo with that name or path | `details.searchDirectories` says where it looked |
| `demo_unreadable` | 422 | The demo could not be parsed | The file is truncated or from an unsupported build |
| `empty_selection` | 409 | The selection matched nothing | Widen the filter |
| `config_invalid` | 422 | The config document is not valid | Fix the patch |
| `game_not_found` | 424 | Counter-Strike 2 was not found | Set `paths.cs2Directory` |
| `toolchain_unavailable` | 424 | HLAE or ffmpeg is missing and cannot be installed | Enable `toolchain.autoDownload` or set the paths |
| `download_failed` | 502 | A tool download failed | Retry, or install the tool manually |
| `recording_failed` | 500 | The game or HLAE failed during recording | Read `logs/highlighter.log` |
| `encoding_failed` | 500 | ffmpeg failed while writing the video | Read `logs/highlighter.log` |
| `job_not_found` | 404 | No job with that id | The job may have aged out of the history |
| `job_conflict` | 409 | The job cannot move to that state | Re-read the job |
| `cancelled` | 200 | The job was cancelled | Not an error |
| `internal` | 500 | Unexpected failure | Read `logs/highlighter.log` and report it |

Codes are added over time. Treat an unrecognised code as a generic failure and show
`error.message`.

## Integration recipe

The order the launcher would normally use.

```
1. start the plugin                 HighlighterCS2.exe --api http --api-port 0
2. read the ready line              baseUrl + token
3. handshake                        cache the command and capability catalogue
4. system.probe                     enable or disable the Record button
5. demos.list                       show the demo list
6. demos.inspect                    show map, rounds and players
7. highlights.find                  show the table the user picks from
   grenades.find                    the same for smokes and the rest
8. plan.preview (optional)          show how long the recording will be
9. jobs.submit                      returns a jobId immediately
10. follow the events               progress bar and stage text
11. jobs.result                     the finished files
```

### C# client sketch

```csharp
var http = new HttpClient { BaseAddress = new Uri(ready.BaseUrl) };
http.DefaultRequestHeaders.Authorization =
    new AuthenticationHeaderValue("Bearer", ready.Token);

async Task<JsonElement> CallAsync(string command, object payload)
{
    var response = await http.PostAsJsonAsync($"/v1/{command}", payload);
    var envelope = await response.Content.ReadFromJsonAsync<JsonElement>();
    if (!envelope.GetProperty("ok").GetBoolean())
    {
        var error = envelope.GetProperty("error");
        throw new HighlighterException(
            error.GetProperty("code").GetString(),
            error.GetProperty("message").GetString());
    }
    return envelope.GetProperty("data");
}

var job = await CallAsync("jobs.submit", new
{
    demo = "match.dem",
    source = "highlights",
    selection = new { players = new[] { steamId64 }, rounds = new[] { 3, 7, 11 } },
    overrides = new { recording = new { fps = 120, singleFile = true } }
});

var jobId = job.GetProperty("jobId").GetString();
```

### Following a job

```csharp
long since = 0;
while (true)
{
    var page = await CallAsync("jobs.events", new { jobId, since, waitSeconds = 30 });
    foreach (var item in page.GetProperty("events").EnumerateArray())
    {
        var type = item.GetProperty("type").GetString();
        var data = item.GetProperty("data");

        if (type == "stage.begin")
            ReportStage(data.GetProperty("stage").GetInt32(),
                        data.GetProperty("total").GetInt32(),
                        data.GetProperty("title").GetString());

        if (type == "clip.written")
            AddClip(data.GetProperty("path").GetString());

        if (type is "job.succeeded" or "job.failed" or "job.cancelled")
            return;
    }
    since = page.GetProperty("nextSequence").GetInt64();
}
```

The long poll returns as soon as something happens, so this loop is idle most of the time and
reacts within milliseconds. There is no need for a timer.

## Guarantees and limits

**The warm game is a single slot.** Only one game is ever kept open, and it is tied to one
demo at one resolution. A job for a different demo launches a fresh game and the old marker is
replaced.

**One recording at a time.** CS2 and HLAE cannot record two demos at once. Submitting more
jobs is fine, they queue. `system.probe` reports `gameRunning`, and a job started while CS2
is already open fails with `recording_failed`.

**Parsing is cached.** A demo is parsed once per file path and modification time. Detection
results are cached per demo and per detection settings. Grenade results are cached per demo
and per requested kinds. `demos.inspect` with `refresh: true` parses the demo again, and
`config.patch` drops the cached detection and grenade results.

**Identifiers are content derived.** They do not change between calls, between sorts, or
between runs of the plugin, as long as the demo file is the same.

**The job history is bounded.** The last 50 jobs are kept, and finished ones beyond that are
dropped. The event journal keeps the last 4000 events.

**Overrides never touch disk.** Only `config.patch` with `persist` writes `config.json`.

**The API never prompts.** Every interactive prompt of the command line app is replaced by an
explicit request field. Nothing waits for console input.

**Updating replaces the program, not the data.** `update.install` swaps the executable and its
bundle. `config.json`, the output folder, `demos`, `tools`, `work` and `logs` are left alone.

**Windows only.** The recorder depends on HLAE, which is Windows only. The API refuses
nothing on other platforms, but recording cannot work there.

**Paths are absolute in responses.** Everything the API returns as a path is fully resolved,
so the launcher can hand it to the shell without guessing the working directory.

**The token is per process.** A generated token lives as long as the plugin process. Restart
the plugin and read the new ready line.

## Versioning

`protocol` follows major.minor. A new minor version only adds commands, payload fields or
response fields. A major version may remove or change them. Send the protocol you were built
against in `handshake` and the plugin refuses a major mismatch instead of failing later in a
confusing way.

Unknown payload fields are ignored, and clients should ignore unknown response fields the
same way.
