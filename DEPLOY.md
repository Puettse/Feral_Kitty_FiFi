# Deploying FiFi on a VPS

Runs the bot as a systemd service with persistent disk (config, ticket
records, panels, and the gimme_report SQLite database survive restarts and
redeploys — unlike Railway's ephemeral filesystem).

Requires: a Debian/Ubuntu-ish VPS with Python 3.10+ and git.

## 1. Create a service user and directories

```bash
sudo useradd --system --home /opt/fifi --shell /usr/sbin/nologin fifi
sudo mkdir -p /opt/fifi /etc/fifi
```

## 2. Clone and install

```bash
sudo git clone https://github.com/Puettse/Feral_Kitty_FiFi.git /opt/fifi
cd /opt/fifi
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
```

## 3. Seed the runtime config

The bot reads its config from `FKF_CONFIG_PATH` (set below to
`/opt/fifi/data/config.json`) and rewrites that file at runtime, so it
lives outside the git tree. Seed it once from the committed copy:

```bash
sudo mkdir -p /opt/fifi/data
sudo cp /opt/fifi/Feral_Kitty_FiFi/data/config.json /opt/fifi/data/config.json
sudo chown -R fifi:fifi /opt/fifi
```

## 4. Environment file

```bash
sudo cp /opt/fifi/deploy/fifi.env.example /etc/fifi/fifi.env
sudo chmod 600 /etc/fifi/fifi.env
sudo nano /etc/fifi/fifi.env   # paste DISCORD_TOKEN and the gimme_report IDs
```

Copy the values of `REPORT_CHANNEL_ID`, `JOIN_LEAVE_LOG_CHANNEL_IDS`, and
`BAN_LOG_CHANNEL_ID` from your Railway service Variables before you shut
Railway down.

## 5. Install and start the service

```bash
sudo cp /opt/fifi/deploy/fifi.service /etc/systemd/system/fifi.service
sudo systemctl daemon-reload
sudo systemctl enable --now fifi
```

Watch it come up:

```bash
journalctl -u fifi -f
```

You should see "Extensions loaded: ..." and "Logged in as ...".

## 6. Shut down Railway

**Important:** do this as soon as the VPS instance is confirmed working.
Two running copies of the bot will double-respond to every command and
both react to `!STOP!`. In Railway, remove the service (or scale it to
zero / take the token away from it).

Note: any state the Railway instance wrote (reaction panels, ticket
records, scheduler jobs) lived on its ephemeral disk and is gone unless
you attached a volume — expect to re-post panels (`!rolespanel`,
`!ticketspanel_chan`, `!welcome`, `!profilepanel`) once on the new host.

## Updating

```bash
cd /opt/fifi
sudo -u fifi git pull
sudo .venv/bin/pip install -r requirements.txt
sudo systemctl restart fifi
```

## Useful commands

```bash
systemctl status fifi        # is it running
journalctl -u fifi -n 200    # recent logs
sudo systemctl restart fifi  # restart after config/code changes
```
