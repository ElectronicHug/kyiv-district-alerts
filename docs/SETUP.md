# Setup and operation

Start with the [Windows quick start](../README.md#quick-start-windows). Python 3.14 is the tested version. No cloud account or paid API is required for the default local setup.

## Choose your areas

Copy `config.example.yaml` to `config.yaml`. The examples are fictional and will not select real local reports until you replace them:

```yaml
relevance:
  direct:
    Обрана зона: ["обрана зона", "обрану зону", "обраній зоні"]
  nearby:
    Сусідня зона: ["сусідня зона", "сусідню зону", "сусідній зоні"]
  broad:
    Київ: ["київ", "києва", "києві"]
    Правий берег: ["правий берег", "правому березі", "на правий"]
```

The keys are display names, used in notification headings. The lists are phrases matched in source posts. Add common grammatical forms, abbreviations and local spellings. Matching ignores case, handles apostrophe variants, and respects word boundaries. It does not infer coordinates or understand every possible wording. Keep each tier as a nonempty mapping.

`direct` and `nearby` mentions normally send immediately. `broad` mentions normally enter the quiet digest. `distant_places` suppresses broad-only matches for excluded places; a match of `Правий берег` is exempt from that exclusion. The engine has a special case for a place named `Центр`: left-center phrases do not count as that local place.

Keep the rest of the example's `relevance` settings. `clear_phrases`, `status_phrases`, time windows and the broad text length limit also affect routing. Set `delivery.mode: all` only if you want every future text post from monitoring sources; the official status channel retains its separate status-only handling.

## Select channels and destination

- Add public channel usernames to `telegram.channels`, including your `alert_status_channel`.
- The logged-in account must join the destination group and sources. With `auto_join_channels: false`, join sources yourself. Enable it only if you want the app to join listed public sources automatically.
- Run `python -m src.telegram.listener --list-groups` with your environment's Python. Copy the negative ID and exact group name into `output_peer_id` and `output_name`.
- `--check-config` validates structure locally. It cannot confirm membership, permissions or whether your chosen aliases will appear in source posts.
- `--test-send` logs in, verifies the destination and sources, then sends one labeled connection test. It does not prove live filtering works.

## Linux / macOS

From the downloaded or cloned repository:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
cp config.example.yaml config.yaml
```

Fill in your credentials and configuration as described in the README, then:

```bash
.venv/bin/python -m src.telegram.listener --list-groups
# Fill output_peer_id / output_name and configure your channels and areas.
.venv/bin/python -m src.telegram.listener --check-config
.venv/bin/python -m src.telegram.listener --test-send
.venv/bin/python -m src.telegram.listener
```

## Docker

Install Docker with Compose. Create and fill `.env` and `config.yaml` first; they stay outside the image. Then:

```text
docker compose build
docker compose run --rm relay python -m src.telegram.listener --list-groups
```

Set the destination ID and name in `config.yaml`, and configure your areas and channels:

```text
docker compose run --rm relay python -m src.telegram.listener --check-config
docker compose run --rm relay python -m src.telegram.listener --test-send
docker compose up -d
docker compose logs --tail=50 relay
```

Stop with `docker compose down`. The `.local` directory persists your journal and Telegram session. No inbound port is published. Docker restarts the container after process exits, but an unhealthy health check alone does not trigger a restart. Run only one relay per destination.

## GCP e2-micro

For continuous operation without leaving your computer on, see the separate [GCP e2-micro deployment guide](DEPLOY_GCP.md). It covers a fresh Debian VM, Docker, IAP access, private configuration and backups.

## Optional Windows autostart

After successful login and a test send, `scripts/run_relay.ps1` runs the relay with logs in `.local/relay.log` and retries after an exit. `scripts/install_autostart.ps1` registers a hidden scheduled task named `Kyiv District Alerts` at your user logon. It needs the project's `.venv` and runs only while your computer is on and you are logged in. Register it only when you want autostart; do not combine it with another running copy.

To disable the task:

```powershell
Disable-ScheduledTask -TaskName 'Kyiv District Alerts'
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing or invalid API credentials | Fill `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in UTF-8 `.env`. Environment variables take precedence. |
| Placeholder group ID | Run `--list-groups` and set a negative ID and exact name. |
| Group not found | Log in with the account that joined that group; check ID and name. |
| Source membership error | Join the configured public source, or explicitly enable auto-join. |
| Official status arrives but no local reports | Add monitoring sources and replace the fictional aliases with real ones. |
| No digest | Digests require a confirmed active city alert; wait for the interval or item threshold. |
| Old posts are absent from the group | Initial history seeds context without forwarding. Earlier full channel history is not imported. |

Use `python -m src.health` to check the local relay heartbeat. It indicates delivery-loop activity, not that sources are publishing or that alerts are accurate.

## Backup and review

`python -m scripts.backup_database` makes a consistent SQLite backup in `.local/backups/`. Do not copy just the live main database file: recent writes can be in its write-ahead log. For recovery, stop the relay and restore a consistent backup. Keep the authenticated `.local/telegram.session` private too.

`python -m scripts.review_relevance` creates `.local/relevance_review.csv` from your journal. Labels there are advisory and do not change live rules automatically.

Advanced cloud backup, corpus export and monitoring scripts are included for adaptation. They require your own cloud environment and permissions and are not part of the local quick start. No production cloud settings are bundled.

## Optional alerts API

The default official Telegram status channel needs no alerts API token. An optional alerts.in.ua path is available: remove `telegram.alert_status_channel`, request your own token from [alerts.in.ua](https://alerts.in.ua/api-request), and set `ALERTS_API_TOKEN`. API polling has a minimum 60-second interval. In this mode the API's observed city state gates quiet digests. Network failures preserve the last observed state rather than producing a false all-clear.
