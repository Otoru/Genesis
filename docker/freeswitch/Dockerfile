# Multi-stage build: download sounds in an image with wget
FROM alpine:latest AS downloader
RUN apk add --no-cache wget
RUN mkdir -p /sounds && \
    cd /sounds && \
    wget -q https://files.freeswitch.org/releases/sounds/freeswitch-sounds-en-us-callie-8000-1.0.51.tar.gz && \
    tar -xzf freeswitch-sounds-en-us-callie-8000-1.0.51.tar.gz && \
    rm freeswitch-sounds-en-us-callie-8000-1.0.51.tar.gz && \
    mkdir -p /sounds-extracted && \
    cp -r sounds/en/us/callie/* /sounds-extracted/ || \
    cp -r */en/us/callie/* /sounds-extracted/ || \
    cp -r en/us/callie/* /sounds-extracted/ && \
    # Move files from digits/8000/ to digits/ for FreeSWITCH compatibility
    if [ -d /sounds-extracted/digits/8000 ]; then \
        cp /sounds-extracted/digits/8000/* /sounds-extracted/digits/ && \
        rm -rf /sounds-extracted/digits/8000; \
    fi

FROM safarov/freeswitch

# Install termcap for interactive CLI support
# Try both apt-get (Debian/Ubuntu) and apk (Alpine)
RUN (apt-get update && apt-get install -y --no-install-recommends ncurses-term && rm -rf /var/lib/apt/lists/*) || \
    (apk add --no-cache ncurses-terminfo-base ncurses-terminfo) || \
    true

# Copy sounds from downloader stage
COPY --from=downloader /sounds-extracted /usr/share/freeswitch/sounds/en/us/callie

# Copy custom configuration files
# Configs are now mounted via volume

# Set working directory
WORKDIR /usr/share/freeswitch

# Run FreeSWITCH
CMD ["freeswitch", "-nonat", "-nf"]
