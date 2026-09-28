"""Journal new Telegram channel posts and relay their text to a private group."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from telethon import TelegramClient, events, utils
from telethon.errors import UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest

from src.alerts_api import alert_status_message, fetch_kyiv_air_raid_state, now_utc
from src.credentials import load_alerts_token, load_credentials, load_telegram_ipv6
from src.duplicates import repeated_report
from src.formatting import digest_message, message_chunks
from src.health import write_heartbeat
from src.official_alerts import official_kyiv_alert_intro, official_kyiv_alert_state
from src.relevance import RelevanceRules
from src.storage import MessageStore, SourcePost


PROJECT_ROOT = Path(__file__).resolve().parents[2]
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def load_config(config_path: Path) -> tuple[list[str], int, str, int, bool]:
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    telegram = config.get("telegram") if isinstance(config, dict) else None
    if not isinstance(telegram, dict):
        raise ValueError("config.yaml needs a telegram section")

    raw_channels = telegram.get("channels")
    if not isinstance(raw_channels, list) or not raw_channels:
        raise ValueError("telegram.channels must contain at least one public channel")

    channels = []
    for raw_channel in raw_channels:
        if not isinstance(raw_channel, str):
            raise ValueError("Every channel must be a public username string")
        username = raw_channel.strip().removeprefix("https://t.me/").removeprefix("@").strip("/")
        if not USERNAME_PATTERN.fullmatch(username):
            raise ValueError(f"Invalid public channel username: {raw_channel!r}")
        if username.casefold() not in {item.casefold() for item in channels}:
            channels.append(username)

    output_peer_id = telegram.get("output_peer_id")
    output_name = telegram.get("output_name")
    history_limit = telegram.get("initial_history_limit", 100)
    auto_join_channels = telegram.get("auto_join_channels", False)
    if not isinstance(output_peer_id, int) or isinstance(output_peer_id, bool):
        raise ValueError("telegram.output_peer_id must be a numeric Telegram peer ID")
    if output_peer_id >= 0:
        raise ValueError("Set telegram.output_peer_id to your negative group ID from --list-groups")
    if not isinstance(output_name, str) or not output_name.strip():
        raise ValueError("telegram.output_name must name the private destination group")
    if not isinstance(history_limit, int) or isinstance(history_limit, bool) or history_limit < 1:
        raise ValueError("telegram.initial_history_limit must be a positive integer")
    if not isinstance(auto_join_channels, bool):
        raise ValueError("telegram.auto_join_channels must be true or false")
    return channels, output_peer_id, output_name, history_limit, auto_join_channels


async def list_groups() -> None:
    """Log in interactively and list group destinations without sending anything."""
    api_id, api_hash = load_credentials(PROJECT_ROOT)
    session_dir = PROJECT_ROOT / ".local"
    session_dir.mkdir(exist_ok=True)
    async with TelegramClient(str(session_dir / "telegram"), api_id, api_hash,
                              use_ipv6=load_telegram_ipv6(PROJECT_ROOT)) as client:
        print("Group ID\tGroup name")
        async for dialog in client.iter_dialogs():
            if dialog.is_group:
                print(f"{utils.get_peer_id(dialog.entity)}\t{dialog.name}")


def check_config(config_path: Path) -> None:
    """Validate local settings without login, credentials or network requests."""
    channels, _, _, _, _ = load_config(config_path)
    mode, _, _, _ = load_delivery_config(config_path)
    load_alert_status_channel(config_path, channels)
    load_alerts_poll_seconds(config_path)
    if mode == "filtered":
        RelevanceRules.from_yaml(config_path)


def load_delivery_config(config_path: Path) -> tuple[str, int, int, int]:
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    delivery = config.get("delivery", {}) if isinstance(config, dict) else {}
    if not isinstance(delivery, dict):
        raise ValueError("delivery must be a mapping")
    mode = delivery.get("mode", "all")
    interval = delivery.get("digest_interval_minutes", 30)
    max_items = delivery.get("digest_max_items", 20)
    duplicate_window = delivery.get("duplicate_window_seconds", 90)
    if mode not in ("all", "filtered"):
        raise ValueError("delivery.mode must be all or filtered")
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
        raise ValueError("delivery.digest_interval_minutes must be positive")
    if not isinstance(max_items, int) or isinstance(max_items, bool) or not 1 <= max_items <= 20:
        raise ValueError("delivery.digest_max_items must be 1..20")
    if not isinstance(duplicate_window, int) or isinstance(duplicate_window, bool) or duplicate_window < 0:
        raise ValueError("delivery.duplicate_window_seconds must be nonnegative")
    return mode, interval, max_items, duplicate_window


def load_alerts_poll_seconds(config_path: Path) -> int:
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    alerts_api = config.get("alerts_api", {}) if isinstance(config, dict) else {}
    if not isinstance(alerts_api, dict):
        raise ValueError("alerts_api must be a mapping")
    seconds = alerts_api.get("poll_seconds", 60)
    if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds < 60:
        raise ValueError("alerts_api.poll_seconds must be at least 60")
    return seconds


def load_alert_status_channel(config_path: Path, channels: list[str]) -> str | None:
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    telegram = config.get("telegram", {}) if isinstance(config, dict) else {}
    raw = telegram.get("alert_status_channel") if isinstance(telegram, dict) else None
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("telegram.alert_status_channel must be a public channel username")
    username = raw.strip().removeprefix("@").casefold()
    if username not in {channel.casefold() for channel in channels}:
        raise ValueError("telegram.alert_status_channel must also be listed in telegram.channels")
    return username


def source_post(message, channel_id: int, channel_username: str) -> SourcePost:
    try:
        raw_json = json.dumps(message.to_dict(), ensure_ascii=False, default=str)
    except (AttributeError, TypeError, ValueError):
        raw_json = None
    return SourcePost(
        channel_id=channel_id,
        message_id=message.id,
        channel_username=channel_username,
        posted_at=message.date.isoformat(),
        text=message.raw_text or "",
        reply_to_message_id=message.reply_to_msg_id,
        edited_at=message.edit_date.isoformat() if message.edit_date else None,
        has_media=bool(message.media),
        raw_json=raw_json,
    )


async def listen(config_path: Path, database_path: Path, *, test_send: bool = False) -> None:
    channels, output_peer_id, output_name, history_limit, auto_join_channels = load_config(config_path)
    delivery_mode, digest_interval, digest_max_items, duplicate_window = load_delivery_config(config_path)
    alert_status_channel = load_alert_status_channel(config_path, channels)
    alerts_poll_seconds = load_alerts_poll_seconds(config_path)
    # The official city channel takes priority over the optional third-party API.
    alerts_token = load_alerts_token(PROJECT_ROOT) if alert_status_channel is None else None
    rules = RelevanceRules.from_yaml(config_path) if delivery_mode == "filtered" else None
    api_id, api_hash = load_credentials(PROJECT_ROOT)
    use_ipv6 = load_telegram_ipv6(PROJECT_ROOT)
    session_dir = PROJECT_ROOT / ".local"
    session_dir.mkdir(exist_ok=True)
    store = MessageStore(database_path)

    try:
        async with TelegramClient(str(session_dir / "telegram"), api_id, api_hash,
                                  use_ipv6=use_ipv6) as client:
            dialogs = {utils.get_peer_id(dialog.entity): dialog for dialog in await client.get_dialogs()}
            destination = dialogs.get(output_peer_id)
            if destination is None or destination.name.casefold() != output_name.casefold():
                raise ValueError(
                    f"The signed-in account must be in the private group {output_name!r} "
                    f"with peer ID {output_peer_id}"
                )

            entities = []
            usernames_by_id = {}
            for channel in channels:
                entity = await client.get_entity(channel)
                if not getattr(entity, "broadcast", False):
                    raise ValueError(f"@{channel} is not a public broadcast channel")
                if utils.get_peer_id(entity) not in dialogs:
                    if not auto_join_channels:
                        raise ValueError(f"The signed-in account must join @{channel} before listening")
                    try:
                        await client(JoinChannelRequest(entity))
                    except UserAlreadyParticipantError:
                        pass
                    print(f"Joined or confirmed @{channel} for reading", file=sys.stderr)
                entities.append(entity)
                usernames_by_id[entity.id] = channel

            if test_send:
                await client.send_message(
                    destination.entity,
                    "<b>🧪 Перевірка підключення</b>\n\n"
                    "Це тестове повідомлення. Підключення до вашої групи працює.",
                    link_preview=False, parse_mode="html",
                )
                print(f"Formatted preview sent to {output_name}", file=sys.stderr)
                return

            # Catch-up uses the IDs saved before live handlers can run.
            last_ids = {entity.id: store.last_id(entity.id) for entity in entities}
            delivery_lock = asyncio.Lock()
            syncing = True

            async def deliver_pending() -> None:
                async with delivery_lock:
                    if alert_status_channel:
                        store.sync_official_alerts(alert_status_channel)
                    for row in store.pending():
                        decision = None
                        intro = ""
                        if row["channel_username"].casefold() == alert_status_channel:
                            state = official_kyiv_alert_state(row["text"])
                            if state is None:
                                store.mark_routed(row["channel_id"], row["message_id"],
                                                  "skip", "official_status", "not an explicit city alert status")
                                continue
                            store.mark_routed(row["channel_id"], row["message_id"],
                                              "notify", "official_status", f"city alert state: {state}")
                            intro = official_kyiv_alert_intro(state)
                        elif rules is not None:
                            parent = (
                                store.get_post(row["channel_id"], row["reply_to_message_id"])
                                if row["reply_to_message_id"] is not None else None
                            )
                            decision = rules.classify_with_reply(row["text"], row["posted_at"], parent)
                            action, reason = decision.action, decision.reason
                            if action == "digest" and store.active_alert_since() is None:
                                action, reason = "skip", "Quiet report outside a confirmed active city alert"
                            if action == "notify" and duplicate_window and not row["sent_chunks"]:
                                since = (datetime.now(timezone.utc) - timedelta(seconds=duplicate_window)).isoformat()
                                for prior in store.recent_notifications(since, row["channel_id"]):
                                    difference = abs((datetime.fromisoformat(row["edited_at"] or row["posted_at"]) -
                                                      datetime.fromisoformat(prior["edited_at"] or prior["posted_at"])).total_seconds())
                                    if difference > duplicate_window:
                                        continue
                                    prior_parent = store.get_post(prior["channel_id"], prior["reply_to_message_id"]) if prior["reply_to_message_id"] else None
                                    prior_decision = rules.classify_with_reply(prior["text"], prior["posted_at"], prior_parent)
                                    if repeated_report(row["text"], decision, prior["text"], prior_decision, rules):
                                        action, reason = "skip", f"Cross-channel repeat of @{prior['channel_username']}/{prior['message_id']} within {duplicate_window}s"
                                        break
                            store.mark_routed(row["channel_id"], row["message_id"],
                                              action, decision.tier, reason)
                            if action != "notify":
                                print(
                                    f"Routed @{row['channel_username']}/{row['message_id']} "
                                    f"to {action}: {reason}", file=sys.stderr
                                )
                                continue
                        if decision is not None:
                            label = (
                                "✅ Чисто / відбій" if decision.is_clear else
                                "📍 Поруч" if decision.tier == "nearby" else "📍"
                            )
                            intro = f"{label} {', '.join(decision.places)}"
                        chunks = message_chunks(
                            row["channel_username"], row["message_id"], row["posted_at"],
                            row["text"], row["edited_at"], intro=intro,
                            context_message_id=(decision.context_message_id if decision else None),
                        )
                        for index in range(row["sent_chunks"], len(chunks)):
                            await client.send_message(
                                destination.entity, chunks[index], link_preview=False, parse_mode="html"
                            )
                            store.mark_chunk_sent(row["channel_id"], row["message_id"], index + 1)
                        store.mark_delivered(row["channel_id"], row["message_id"])

                    if rules is not None:
                        digest_rows = store.active_digest_pending()
                        if digest_rows:
                            first_routed = datetime.fromisoformat(digest_rows[0]["routed_at"])
                            due = first_routed + timedelta(minutes=digest_interval)
                            if len(digest_rows) >= digest_max_items or datetime.now(timezone.utc) >= due:
                                batch = digest_rows[:digest_max_items]
                                await client.send_message(
                                    destination.entity, digest_message(batch), silent=True,
                                    link_preview=False, parse_mode="html",
                                )
                                store.mark_digest_delivered(batch)
                                print(f"Sent quiet digest of {len(batch)} posts", file=sys.stderr)

            @client.on(events.NewMessage(chats=entities))
            async def on_new_post(event):
                if not event.message.post:
                    return
                channel_id = utils.resolve_id(event.chat_id)[0]
                post = source_post(event.message, channel_id, usernames_by_id[channel_id])
                if store.record(post):
                    print(f"Stored @{post.channel_username}/{post.message_id}", file=sys.stderr)
                if not syncing:
                    try:
                        await deliver_pending()
                    except Exception as error:
                        print(f"Delivery pending; will retry: {error}", file=sys.stderr)

            @client.on(events.MessageEdited(chats=entities))
            async def on_edited_post(event):
                if not event.message.post:
                    return
                channel_id = utils.resolve_id(event.chat_id)[0]
                post = source_post(event.message, channel_id, usernames_by_id[channel_id])
                if store.record_edit(post):
                    print(f"Updated @{post.channel_username}/{post.message_id}", file=sys.stderr)
                if not syncing:
                    try:
                        await deliver_pending()
                    except Exception as error:
                        print(f"Delivery pending; will retry: {error}", file=sys.stderr)

            for entity in entities:
                channel = usernames_by_id[entity.id]
                last_id = last_ids[entity.id]
                if last_id is None:
                    # Seed context without flooding the group with older posts.
                    history = await client.get_messages(entity, limit=history_limit)
                    for message in reversed(history):
                        if getattr(message, "post", False):
                            store.record(source_post(message, entity.id, channel), historical=True)
                    print(f"Seeded recent history from @{channel}", file=sys.stderr)
                else:
                    async for message in client.iter_messages(entity, min_id=last_id, reverse=True):
                        if getattr(message, "post", False):
                            store.record(source_post(message, entity.id, channel))
                    print(f"Caught up @{channel} after message {last_id}", file=sys.stderr)

            syncing = False
            await deliver_pending()
            write_heartbeat(session_dir / "heartbeat.json", channels)

            async def retry_delivery() -> None:
                while True:
                    await asyncio.sleep(30)
                    try:
                        await deliver_pending()
                        write_heartbeat(session_dir / "heartbeat.json", channels)
                    except Exception as error:
                        print(f"Delivery pending; will retry: {error}", file=sys.stderr)

            retry_task = asyncio.create_task(retry_delivery())
            async def poll_kyiv_alerts() -> None:
                while True:
                    try:
                        state, alert_json = await asyncio.to_thread(fetch_kyiv_air_raid_state, alerts_token)
                        store.observe_kyiv_alert(state, now_utc(), alert_json)
                        pending = store.pending_kyiv_alert()
                        if pending is not None:
                            await client.send_message(
                                destination.entity,
                                alert_status_message(pending["state"], pending["checked_at"]),
                                link_preview=False, parse_mode="html",
                            )
                            store.mark_kyiv_alert_notified(pending["state"])
                            print(f"Kyiv air raid level changed to {state}", file=sys.stderr)
                    except Exception as error:
                        print(f"Kyiv alert API poll failed; status unchanged: {error}", file=sys.stderr)
                    await asyncio.sleep(alerts_poll_seconds)

            alerts_task = asyncio.create_task(poll_kyiv_alerts()) if alerts_token else None
            if alerts_task is None:
                reason = "official @va_kyiv channel active" if alert_status_channel else "ALERTS_API_TOKEN is not set"
                print(f"Kyiv alert level API inactive: {reason}", file=sys.stderr)
            try:
                print(
                    f"Listening to {', '.join('@' + channel for channel in channels)}; "
                    f"delivery mode {delivery_mode} to {output_name}",
                    file=sys.stderr,
                )
                await client.run_until_disconnected()
            finally:
                retry_task.cancel()
                if alerts_task is not None:
                    alerts_task.cancel()
                try:
                    await retry_task
                except asyncio.CancelledError:
                    pass
                if alerts_task is not None:
                    try:
                        await alerts_task
                    except asyncio.CancelledError:
                        pass
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.yaml")
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / ".local" / "messages.sqlite3")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--test-send", action="store_true", help="send one test message to the private group and exit")
    actions.add_argument("--list-groups", action="store_true", help="log in and print your group IDs; sends nothing")
    actions.add_argument("--check-config", action="store_true", help="validate settings offline; no login or messages")
    args = parser.parse_args()
    try:
        if args.list_groups:
            asyncio.run(list_groups())
        elif args.check_config:
            check_config(args.config)
            print("Configuration is valid. No login or messages sent.")
        else:
            asyncio.run(listen(args.config, args.database, test_send=args.test_send))
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Error: {error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
