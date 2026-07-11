# Troubleshooting

## Windows: Python is missing or too old

Native Windows support begins with v0.8.0 and requires Python 3.10+. The installer does not install Python. Install a supported version from <https://www.python.org/downloads/windows/>, open a new PowerShell window, then run the installer again.

## Windows: `image-prompt-library` is not found

The installer adds `%LOCALAPPDATA%\ImagePromptLibrary\bin` to your user PATH. Close PowerShell, open a new window, and try the command again. The public command is a `.cmd`, so it remains callable when Windows PowerShell uses the `Restricted` execution policy. If PATH is still unavailable, run that public shim directly:

```powershell
& "$env:LOCALAPPDATA\ImagePromptLibrary\bin\image-prompt-library.cmd" status
```

Use `image-prompt-library doctor` to check the user PATH and selected version.

## Windows: the port is occupied

Do not stop unrelated processes. Start this install on an unused port instead:

```powershell
image-prompt-library start --port 8001
```

## Windows: stale runtime record or startup failure

Run:

```powershell
image-prompt-library doctor
image-prompt-library status
```

`doctor` distinguishes a stale runtime record from a live managed process. Do not delete a PID record while its matching process is live, and do not kill all Python processes. For startup or health failures, inspect `%LOCALAPPDATA%\ImagePromptLibrary\logs\app.err.log` and `app.out.log`; the preceding attempt is retained as `app.previous.err.log` and `app.previous.out.log`.

## Windows: update recovery or rollback

A handled update failure restores the previous version and runtime when possible. The controller does not provide a durable crash journal, so an OS or power interruption can still leave work for `doctor`. Check the selected version and health with `image-prompt-library version`, `image-prompt-library status`, and `image-prompt-library doctor`; then retry or use `image-prompt-library rollback` if the validated previous version is available.

## Windows: uninstall and private data

`image-prompt-library uninstall` preserves `%USERPROFILE%\ImagePromptLibrary`. Use `--delete-library` only when you intentionally want to remove private prompts and images too.

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

That is expected for a fresh install. A fresh local library starts empty. Click `+ Add` to create your first prompt card, or install the optional sample library if you want demo content first:

```bash
image-prompt-library sample-data en
```

To confirm the installed app is using the library path you expect, run:

```bash
image-prompt-library status
image-prompt-library doctor
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
