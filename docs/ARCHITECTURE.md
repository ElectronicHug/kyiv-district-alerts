# Architecture and limitations

One Python process logs in as a Telegram user through Telethon, reads configured public source channels, stores text and metadata in SQLite, and sends selected text to a group the account has joined.

| Component | Responsibility |
| --- | --- |
| `src/telegram/listener.py` | Login, channel events, catch-up, routing and delivery retries |
| `src/relevance.py` | Place-name matching, status phrases and recent reply context |
| `src/official_alerts.py` | Explicit yellow / red / all-clear headline recognition |
| `src/duplicates.py` | Conservative suppression of some brief cross-channel repeats |
| `src/formatting.py` | Escaped Telegram HTML, source links, Kyiv time and digests |
| `src/storage.py` | SQLite journal, delivery progress and official alert state |
| `src/health.py` | Local delivery-loop heartbeat |

New sources seed up to `initial_history_limit` recent posts without sending them. Later runs process posts after the last stored message ID. Relevant text edits can trigger delivery again. Long text is split into numbered messages. Source signatures on standalone trailing lines are removed, and remaining text is preserved.

Direct matches take priority over nearby matches, then broad matches. Local “Чисто” reports are relayed immediately; replies can inherit direct or nearby context from a parent within six hours by default. A clear statement followed by a new threat is not labeled as clear. Quiet digests are tied to an explicit active official city alert; an all-clear clears that alert's old queue.

## Practical limits

- A place mention does not prove a threat. Sources and text rules can be late or wrong.
- Local “Чисто” is a source report, distinct from the official city all-clear.
- Aliases require configuration. Unlisted slang and ambiguous wording can be missed.
- Media-only posts are retained as metadata but have no relayed text. No media binaries are downloaded.
- Delivery is not exactly once: a crash after Telegram accepts a message and before the journal records it can cause a duplicate.
- A healthy heartbeat does not verify Telegram source accuracy, new source activity, or backup success.
- Source text and serialized Telegram metadata are saved locally. Do not publish the resulting database, corpus, review sheet or session.

## Offline validation

Tests use fictional geography and temporary SQLite files. They cover matching, reply context, duplicate suppression, official-status recognition, formatting, delivery persistence, backup consistency, corpus merging and heartbeat age checks. No Telegram credentials or cloud account are needed to run them. Passing offline tests does not confirm an individual user's Telegram login or group permissions.
