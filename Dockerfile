FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        udev libudev1 \
        eject lsscsi \
        libdiscid0 \
        curl gnupg software-properties-common ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# MakeMKV (prebuilt binaries via the community PPA already validated on this host's own OS)
RUN add-apt-repository -y ppa:heyarje/makemkv-beta \
    && apt-get update \
    && apt-get install -y --no-install-recommends makemkv-bin makemkv-oss \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
