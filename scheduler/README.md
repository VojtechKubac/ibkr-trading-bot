# Scheduler

Systemd user-timer setup for the weekly trading bot run.

## Prerequisites

- Linux with systemd (user session enabled)
- Project installed and `.venv` created (`pip install -r requirements.txt`)
- `.env` file present at the project root (copy from `.env.example`)

## Install

```bash
bash scheduler/install.sh
```

This substitutes the project path into the unit files and installs them under
`~/.config/systemd/user/`, then enables and starts the timer.

## Check timer status

```bash
systemctl --user status trading-bot.timer
```

## View logs

```bash
journalctl --user -u trading-bot.service
```

## Run manually (without waiting for the timer)

```bash
systemctl --user start trading-bot.service
```

## Uninstall

```bash
systemctl --user disable --now trading-bot.timer
rm ~/.config/systemd/user/trading-bot.service \
   ~/.config/systemd/user/trading-bot.timer
systemctl --user daemon-reload
```
