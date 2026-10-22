FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Pin the Wikimedia Commons original logo; verify bytes before packaging.
RUN python -c 'import hashlib,pathlib,urllib.request; url="https://upload.wikimedia.org/wikipedia/commons/8/87/Battlefield_4_logo.png"; data=urllib.request.urlopen(url,timeout=30).read(); assert hashlib.sha256(data).hexdigest()=="b3c440693dd993474c2d4b0e8d524a52fb3810cd9d40b7dcf7da913065b5dc4f", "Unexpected logo checksum"; pathlib.Path("bf4ps_discord/assets/battlefield4_wordmark_commons.png").write_bytes(data)'
RUN useradd --create-home bot
USER bot
CMD ["python", "-m", "bf4ps_discord.main"]
