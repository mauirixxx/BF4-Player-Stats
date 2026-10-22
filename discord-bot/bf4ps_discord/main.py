"""Leader-only Discord gateway. Standby never connects."""
import asyncio
import logging
import os
import signal
import time
import discord
from discord import app_commands
from . import leases

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("bf4ps.discord")
DSN=os.environ["BOT_DATABASE_URL"].replace("postgresql+psycopg://","postgresql://")
NODE=os.environ["NODE_ID"]
TOKEN=os.environ.get("DISCORD_BOT_TOKEN","")
DRY_RUN=os.environ.get("DRY_RUN","0")=="1"
TTL=30
RENEW=10

class Bot(discord.Client):
    def __init__(self, authority):
        intents=discord.Intents.none()
        intents.guilds=True
        super().__init__(intents=intents)
        self.authority=authority
        self.tree=app_commands.CommandTree(self)
        @self.tree.command(name="ping",description="Check the BF4 Player Stats bot connection")
        async def ping(interaction: discord.Interaction):
            try:
                valid=await asyncio.wait_for(asyncio.to_thread(
                    leases.is_current,DSN,NODE,self.authority),timeout=5)
            except Exception:
                valid=False
            if not valid:
                await interaction.response.send_message("Bot leadership is changing. Please retry.",ephemeral=True)
                return
            await interaction.response.send_message("BF4 Player Stats bot is online! 🐹",ephemeral=True)

    async def setup_hook(self):
        synced=await self.tree.sync()
        log.info("slash_commands_synced node=%s count=%s",NODE,len(synced))

    async def on_ready(self):
        log.info("discord_ready node=%s user=%s",NODE,self.user)

async def run():
    if not DRY_RUN and (not TOKEN or TOKEN=="REPLACE_ME"):
        raise RuntimeError("Set DISCORD_BOT_TOKEN in private .env")
    stopping=asyncio.Event()
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):
        try: loop.add_signal_handler(sig,stopping.set)
        except NotImplementedError: pass
    bot=None
    session=None
    lease=None
    deadline=0.0
    next_renew=0.0
    try:
        while not stopping.is_set():
            try:
                await asyncio.wait_for(asyncio.to_thread(leases.heartbeat,DSN,NODE),timeout=7)
                if lease is None:
                    started=time.monotonic()
                    acquired=await asyncio.wait_for(asyncio.to_thread(leases.acquire,DSN,NODE,TTL),timeout=7)
                    if acquired:
                        lease=acquired
                        deadline=started+TTL
                        next_renew=started+RENEW
                        log.info("leadership_acquired node=%s generation=%s dry_run=%s",NODE,lease.generation,DRY_RUN)
                        if not DRY_RUN:
                            bot=Bot(lease.generation)
                            session=asyncio.create_task(bot.start(TOKEN,reconnect=True))
                elif time.monotonic()>=next_renew:
                    started=time.monotonic()
                    ok=await asyncio.wait_for(asyncio.to_thread(leases.renew,DSN,NODE,lease.generation,TTL),timeout=7)
                    if not ok: raise RuntimeError("lease renewal rejected")
                    deadline=started+TTL
                    next_renew=started+RENEW
                if lease and time.monotonic()>=deadline: raise RuntimeError("local authority expired")
                if session and session.done():
                    raise RuntimeError(f"Discord gateway stopped: {session.exception() if not session.cancelled() else 'cancelled'}")
            except Exception as exc:
                log.warning("control_plane_error node=%s reason=%s",NODE,exc)
                if lease:
                    log.warning("leadership_suspended node=%s generation=%s",NODE,lease.generation)
                    if session:
                        await bot.close()
                        try: await asyncio.wait_for(session,timeout=5)
                        except (Exception,asyncio.CancelledError): session.cancel()
                        session=None
                        bot=None
                    lease=None
                    # Conservative: do not release on uncertain DB outcome; let TTL expire.
                await asyncio.sleep(3)
            try: await asyncio.wait_for(stopping.wait(),timeout=1)
            except asyncio.TimeoutError: pass
    finally:
        if session:
            await bot.close()
            try: await asyncio.wait_for(session,timeout=5)
            except (Exception,asyncio.CancelledError): session.cancel()
        if lease:
            try: await asyncio.wait_for(asyncio.to_thread(leases.release,DSN,NODE,lease.generation),timeout=7)
            except Exception: pass
        log.info("stopped node=%s",NODE)

if __name__=="__main__":
    asyncio.run(run())
