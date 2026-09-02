FROM ghcr.io/linuxserver/baseimage-kasmvnc:ubuntunoble-ffa21aaf-ls56

ENV TITLE="Apex FX & MetaTrader" \
    WINEARCH=win64 \
    WINEPREFIX="/config/.wine" \
    DISPLAY=:0 \
    WINEDEBUG="-all,err-toolbar,fixme-all" \
    WINEDLLOVERRIDES="mscoree,mshtml="

RUN mkdir -p /config/.wine && \
    chown -R abc:abc /config/.wine && \
    chmod -R 755 /config/.wine

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    dos2unix \
    python3-pip \
    wget \
    python3-pyxdg \
    netcat-openbsd \
    ca-certificates \
    lsb-release \
    cabextract \
    unzip \
    p7zip-full \
    gnupg \
    xdotool \
    x11-utils \
    x11-apps && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -pm755 /etc/apt/keyrings && \
    wget -O - https://dl.winehq.org/wine-builds/winehq.key | sudo gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key - && \
    wget -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/ubuntu/dists/noble/winehq-noble.sources && \
    dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --install-recommends winehq-staging && \
    apt-get purge winetricks -y && \
    wget -O /tmp/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks && \
    chmod +x /tmp/winetricks && \
    mv /tmp/winetricks /usr/local/bin && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt || true

COPY headless-mt5/app/ /app/
COPY headless-mt5/app/scripts /scripts
COPY . /app/

RUN dos2unix /scripts/*.sh && \
    chmod +x /scripts/*.sh && \
    touch /var/log/mt5_setup.log && \
    chown abc:abc /var/log/mt5_setup.log && \
    chmod 664 /var/log/mt5_setup.log

COPY headless-mt5/root /

EXPOSE 8501 3000 5001

VOLUME /config
