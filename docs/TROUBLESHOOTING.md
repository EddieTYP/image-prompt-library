# Troubleshooting

## `./scripts/start.sh` cannot find Python dependencies

Run setup first:

```bash
./scripts/setup.sh
```

Then restart:

```bash
./scripts/start.sh
```

## Port already in use

For source/development mode, change `.env`:

```bash
BACKEND_PORT=8001
FRONTEND_PORT=5178
```

Then restart the app.

For installed release mode, start on a different port:

```bash
image-prompt-library start --port 8001
```

## Empty library after first start

That is expected for a fresh install. Click `+ Add` to create your first prompt card, or install the optional sample library if you want demo content first:

```bash
image-prompt-library sample-data en
```

## Images or database missing after moving folders

Check `IMAGE_PROMPT_LIBRARY_PATH` in `.env` or the installed app configuration. Your database and image folders must stay together.

## Command not found after install

If `image-prompt-library` is not found, add `~/.local/bin` to your shell `PATH`, or use the fallback command printed by the installer:

```bash
~/.image-prompt-library/app/current/scripts/appctl.sh start
```

## LAN access does not work

By default, the app binds to `127.0.0.1`, which is local to the machine. For LAN access, explicitly bind to `0.0.0.0` only on a trusted machine/network:

```bash
image-prompt-library start --host 0.0.0.0
```

Then check your OS firewall and router/VPN settings.
