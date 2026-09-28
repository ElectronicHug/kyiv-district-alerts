# Deploy on Google Cloud: e2-micro example

Run the relay on a small VM so your local computer can be switched off. This example uses **Debian 12, an `e2-micro` VM, a 20 GB standard persistent disk and Docker Compose** in `us-central1-a`. All resource names below are examples; no production account details are included.

The relay connects out to Telegram. It needs no domain, website, HTTPS certificate or public application port. You manage SSH through Google Identity-Aware Proxy (IAP).

**Validation:** commands have been checked against official documentation and the repository configuration. This public guide has not been executed end to end on a newly created VM.

## Before you start

You need your own Google Cloud project with billing enabled, permission to create Compute Engine and network resources, and your own Telegram API credentials. The account used for SSH needs IAP tunnel access (`roles/iap.tunnelResourceAccessor`) and permissions to connect to the VM. If your organization enforces OS Login, it also needs the appropriate OS Login role. See [Google's IAP SSH permissions](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding).

**Costs:** Google lists eligible `e2-micro` usage in `us-west1`, `us-central1` and `us-east1` under its [Free Tier limits](https://docs.cloud.google.com/free/docs/free-cloud-features#compute). This example uses an external IPv4 address for outbound connectivity; review [IPv4 and network pricing](https://cloud.google.com/vpc/network-pricing). VM eligibility does not make the full deployment free: address charges, excess traffic, disks, snapshots and optional backups can add costs. Check your project's usage and set a [billing budget alert](https://docs.cloud.google.com/billing/docs/how-to/budgets); an alerts-only budget does not automatically stop spending.

## 1. Create the VM from Cloud Shell

Open [Google Cloud Shell](https://console.cloud.google.com/cloudshell), which already has `gcloud`. **The following commands are Bash, not PowerShell.** Replace `YOUR_PROJECT_ID` with a project you own. Use unused resource names, and run these creation commands once.

```bash
TASK_PROJECT_ID='YOUR_PROJECT_ID'
TASK_REGION='us-central1'
TASK_ZONE='us-central1-a'
TASK_VM='kyiv-alerts-demo'
TASK_NETWORK='kyiv-alerts-demo-net'
TASK_SUBNET='kyiv-alerts-demo-subnet'

gcloud services enable compute.googleapis.com iap.googleapis.com \
  --project="$TASK_PROJECT_ID"

gcloud compute networks create "$TASK_NETWORK" \
  --project="$TASK_PROJECT_ID" --subnet-mode=custom

gcloud compute networks subnets create "$TASK_SUBNET" \
  --project="$TASK_PROJECT_ID" --network="$TASK_NETWORK" \
  --region="$TASK_REGION" --range=10.42.0.0/24

gcloud compute firewall-rules create kyiv-alerts-demo-iap-ssh \
  --project="$TASK_PROJECT_ID" --network="$TASK_NETWORK" \
  --direction=INGRESS --action=ALLOW --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 --target-tags=kyiv-alerts-iap

gcloud compute instances create "$TASK_VM" \
  --project="$TASK_PROJECT_ID" --zone="$TASK_ZONE" \
  --machine-type=e2-micro --provisioning-model=STANDARD \
  --image-project=debian-cloud --image-family=debian-12 \
  --boot-disk-size=20GB --boot-disk-type=pd-standard \
  --network="$TASK_NETWORK" --subnet="$TASK_SUBNET" \
  --tags=kyiv-alerts-iap --no-service-account --no-scopes

gcloud compute ssh "$TASK_VM" \
  --project="$TASK_PROJECT_ID" --zone="$TASK_ZONE" --tunnel-through-iap
```

This creates a dedicated network with an IAP-only SSH rule, rather than relying on broad SSH rules in a default network. The VM has an ephemeral external IPv4 address and no attached service account. The basic relay needs no Google Cloud API access from inside the VM. References: [VM creation flags](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/create) and [IAP firewall configuration](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding#create_a_firewall_rule).

## 2. Install Docker on the VM

**Run this section and sections 3–7 inside the SSH session on the VM.** These commands target a fresh Debian 12 VM and configure Docker's official package repository:

```bash
sudo apt-get update
sudo apt-get install --yes ca-certificates curl gnupg git nano
sudo mkdir -p /etc/apt/keyrings
curl --fail --silent --show-error --location \
  https://download.docker.com/linux/debian/gpg \
  | sudo gpg --dearmor --yes --output /etc/apt/keyrings/docker.gpg
sudo chmod 644 /etc/apt/keyrings/docker.gpg

TASK_DEBIAN_CODENAME="$(. /etc/os-release && printf '%s' "$VERSION_CODENAME")"
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian %s stable\n' \
  "$(dpkg --print-architecture)" "$TASK_DEBIAN_CODENAME" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install --yes docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

For other Debian releases, existing Docker installations or package conflicts, use the [official Docker installation guide](https://docs.docker.com/engine/install/debian/). All Docker commands below use `sudo`; adding your login to the Docker group is unnecessary for this guide.

## 3. Get the public source and configure your copy

Clone the public repository. If you maintain a fork, use your fork's URL instead.

```bash
TASK_REPO_URL='https://github.com/ElectronicHug/kyiv-district-alerts.git'
git clone "$TASK_REPO_URL" kyiv-district-alerts
cd kyiv-district-alerts
umask 077
cp .env.example .env
cp config.example.yaml config.yaml
mkdir -p .local
chmod 600 .env config.yaml
chmod 700 .local
nano .env
```

Enter your `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`. For this IPv4 example, leave `TELEGRAM_USE_IPV6=0`. The default official status channel needs no `ALERTS_API_TOKEN`. Save the file, then:

```bash
sudo docker compose build
sudo docker compose run --rm relay python -m src.telegram.listener --list-groups
```

Complete the interactive Telegram login on the VM. It creates the private `.local/telegram.session`. The command prints your group IDs and names without sending messages. Do not paste login codes, passwords or the session into GitHub.

```bash
nano config.yaml
```

Set the negative `output_peer_id` and exact `output_name`. Add your trusted public monitoring channels, join them with the same Telegram account, and replace the fictional area aliases. Keep `@va_kyiv` in both `channels` and `alert_status_channel` for official city updates. The full settings explanation is in [setup and configuration](SETUP.md#choose-your-areas).

## 4. Test, then start the continuous relay

Stop any other relay that sends to this same group before starting this copy. A fresh VM database seeds recent source history without forwarding it; it does not import your old local journal.

```bash
sudo docker compose run --rm relay python -m src.telegram.listener --check-config
sudo docker compose run --rm relay python -m src.telegram.listener --test-send
```

Confirm the labeled connection test in your group. It checks login and destination access, not the accuracy of your filtering rules. Then:

```bash
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail=50 relay
sudo docker compose exec relay python -m src.health
```

Leave the relay running and exit SSH with `exit`. The VM and Docker continue running independently of Cloud Shell and your local computer. Docker's `unless-stopped` policy restarts the container after a process exit or host reboot unless you deliberately stopped it.

## 5. Check operation and resource use

Reconnect with the `gcloud compute ssh ... --tunnel-through-iap` command from section 1, then `cd kyiv-district-alerts`:

```bash
sudo docker compose ps
sudo docker compose logs --tail=100 relay
sudo docker compose exec relay python -m src.health
sudo docker stats --no-stream
df -h .
```

An `e2-micro` is a small starting point for this lightweight app, not a capacity guarantee. Inspect memory, disk usage and logs with your own source volume. The journal and backups grow over time; review retention before the disk fills. The Compose file limits container logs to three 10 MB files.

The health check tracks the delivery loop; it does not validate alert accuracy or automatically restart an unhealthy container. Email outage alerts and offsite backups are separate optional work, not configured by this guide. Do not publish a web or Docker management port for this relay.

## 6. Back up privately

For a consistent journal backup while the relay runs:

```bash
sudo docker compose exec relay python -m scripts.backup_database
```

The output is in `.local/backups/`. This protects neither against losing the whole VM nor against losing the Telegram session.

For a portable private recovery archive, pause delivery briefly and package the session, journal and your settings together:

```bash
umask 077
TASK_BACKUP_FILE="$PWD/../kyiv-alerts-private-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
sudo docker compose stop relay
sudo tar -czf "$TASK_BACKUP_FILE" .env config.yaml .local
sudo chmod 600 "$TASK_BACKUP_FILE"
sudo chown "$(id -u):$(id -g)" "$TASK_BACKUP_FILE"
sudo docker compose start relay
printf 'Private backup: %s\n' "$TASK_BACKUP_FILE"
```

If archiving fails, restart the relay and investigate the error. Keep a copy outside the VM using a private transfer or storage location. From Cloud Shell or your own terminal, `gcloud compute scp --tunnel-through-iap --project=YOUR_PROJECT_ID --zone=us-central1-a VM_NAME:REMOTE_ARCHIVE_PATH LOCAL_DESTINATION` downloads it; replace every placeholder with your own values.

The archive contains API credentials and an authenticated Telegram session. Never attach it to a public issue or commit it. To restore, extract into a private directory, verify the SQLite database, stop the target relay, restore `.env`, `config.yaml` and `.local` with restricted permissions, then start and check health. Do not run two restored copies against the same destination.

## 7. Update or stop the app

From the repository directory on the VM:

```bash
git pull --ff-only
sudo docker compose build
sudo docker compose up -d
sudo docker compose ps
sudo docker compose exec relay python -m src.health
```

Building first leaves the existing container running if the build fails. Compose replaces it after a successful build. The bind-mounted `.local`, `.env` and personal `config.yaml` are not overwritten by Git. Make a private backup before applying updates.

To stop delivery without deleting its state:

```bash
sudo docker compose stop relay
```

Resume with `sudo docker compose start relay`. Stopping the container leaves the VM running and potentially billable.

## 8. Retire the VM when you no longer need it

Back up privately first. In Google Cloud Console, [stop the VM](https://docs.cloud.google.com/compute/docs/instances/stop-start-instance) to pause its compute usage, or delete it when retiring the deployment. Stopped VMs can still incur storage and other resource charges. VM deletion can delete its boot disk, including your session and journal. Review the disk-deletion option, retained snapshots, IP addresses and other resources; use the billing dashboard to confirm what remains.
