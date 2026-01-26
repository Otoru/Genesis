# FreeSWITCH Test Environment

Isolated Docker environment for testing the **Genesis** library with FreeSWITCH.

> [!IMPORTANT]
> This is a **testing only** environment. It is not part of the Genesis project build.

## Structure

```
docker/freeswitch/
├── Dockerfile              # FreeSWITCH Image
├── docker-compose.yml      # Orchestration
├── README.md               # This documentation
└── config/
    ├── event_socket.conf.xml
    ├── dialplan/
    │   └── default.xml
    ├── logs/               # Automatically created
    └── recordings/         # Automatically created
```

## Quick Start

```bash
cd docker/freeswitch
docker-compose up -d
```

> [!WARNING]
> This setup uses **Host Networking** (`network_mode: host`).
> - **Linux:** The container shares the host's networking stack. Ports are opened directly on the host interface.
> - **macOS:** The container shares the Docker VM's networking stack. You may need to access via the VM's IP or ensure Docker Desktop forwards traffic correctly.

## Configuration

### Event Socket Layer (ESL)

- **Host:** `127.0.0.1` (or host IP)
- **Port:** `8021`
- **Password:** `ClueCon`

### Outbound Socket

- **Port:** `9696`

### Capabilities & Limits

The container is configured with high-performance capabilities:
- `IPC_LOCK`, `SYS_NICE` for real-time audio scheduling
- `NET_ADMIN`, `NET_RAW` for network operations
- High `ulimits` (memlock, nofile, rtprio)

## Useful Commands

```bash
# View logs
docker-compose logs -f freeswitch

# Access FreeSWITCH console (interactive)
docker exec -it -e TERM=xterm-256color genesis-freeswitch fs_cli

# Run FreeSWITCH commands non-interactively
docker exec -it genesis-freeswitch fs_cli -x "status"
docker exec -it genesis-freeswitch fs_cli -x "sofia status"
docker exec -it genesis-freeswitch fs_cli -x "show channels"

# Common commands
docker exec -it genesis-freeswitch fs_cli -x "originate user/1000 9999"
docker exec -it genesis-freeswitch fs_cli -x "global_getvar domain"

# Stop environment
docker-compose down

# Clean up everything (including volumes)
docker-compose down -v
rm -rf config/logs config/recordings
```

## Troubleshooting

### Container does not start

```bash
docker-compose logs freeswitch
```

### Cannot connect to ESL

Check if the container is running:
```bash
docker ps | grep genesis-freeswitch
```

### Issues with Outbound Socket

Ensure your app is running at `0.0.0.0:9696` and is accessible from the container.

## Available Sound Files

The Docker image includes FreeSWITCH sound files (English US, Callie voice) at `/usr/share/freeswitch/sounds/en/us/callie/`.

### Main Directories

- **`digits/`** - Number pronunciations (0-9, 10-90, 100, 1000, million, etc.)
- **`ivr/`** - IVR prompts (welcome, menu options, confirmations, errors, etc.)
- **`directory/`** - Directory/phonebook prompts
- **`voicemail/`** - Voicemail system prompts
- **`currency/`** - Currency pronunciations (dollar, cents, etc.)
- **`conference/`** - Conference call prompts
- **`time/`** - Time and date pronunciations
- **`misc/`** - Miscellaneous sounds

### Usage in Code

When using `channel.playback()` or `channel.say()`, reference files relative to the sound prefix:

```python
# Play IVR prompt
await channel.playback("ivr/8000/ivr-welcome_to_freeswitch.wav")

# Say a number (uses digits/)
await channel.say("123", lang="en", kind="NUMBER")
```

### Common IVR Prompts

- `ivr-welcome_to_freeswitch.wav` - Welcome message
- `ivr-thank_you.wav` - Thank you
- `ivr-thank_you_for_calling.wav` - Goodbye message
- `ivr-that_was_an_invalid_entry.wav` - Invalid input
- `ivr-please_try_again.wav` - Retry prompt
- `ivr-one_moment_please.wav` - Hold message
- `ivr-for.wav` - "For" (menu navigation)
- `ivr-option.wav` - "Option"
- `ivr-or_press.wav` - "Or press"

### Listing Available Files

To see all available sound files:

```bash
docker exec -it genesis-freeswitch find /usr/share/freeswitch/sounds/en/us/callie -name "*.wav" | head -20
```

To see IVR prompts specifically:

```bash
docker exec -it genesis-freeswitch ls /usr/share/freeswitch/sounds/en/us/callie/ivr/8000/ | head -20
```
