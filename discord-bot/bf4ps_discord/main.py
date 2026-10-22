"""Leader-only Discord gateway. Standby never connects."""
import asyncio
import logging
import os
import signal
import time
import discord
from discord import app_commands
import datetime
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
        self.started_at=discord.utils.utcnow()
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

        admin=app_commands.Group(name="admin",description="BF4 Player Stats server administration")

        @admin.command(name="status",description="Show private bot and HA cluster status")
        async def admin_status(interaction: discord.Interaction):
            if interaction.guild is None or interaction.user.id != interaction.guild.owner_id:
                await interaction.response.send_message("Only the server owner can use this command until a management role is configured.",ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True,thinking=True)
            try:
                state=await asyncio.wait_for(asyncio.to_thread(
                    leases.status_snapshot,DSN,NODE,self.authority),timeout=6)
            except Exception:
                await interaction.followup.send("Control-plane database unavailable; status cannot be verified.",ephemeral=True)
                return
            if not state["authorized"]:
                await interaction.followup.send("Leadership has changed. Please retry.",ephemeral=True)
                return
            now=discord.utils.utcnow()
            nodes=state["nodes"]
            standby=[f"`{n['node']}` ({'online' if n['fresh'] else 'stale'}, {'draining' if n['draining'] else 'enabled' if n['enabled'] else 'disabled'})" for n in nodes if n["node"]!=state["leader"]]
            embed=discord.Embed(title="BF4 Player Stats — Operator Status",color=discord.Color.blurple(),timestamp=now)
            embed.add_field(name="Discord leader",value=f"`{state['leader'] or 'None'}`",inline=True)
            embed.add_field(name="Leadership generation",value=str(state["generation"]),inline=True)
            embed.add_field(name="Lease expires",value=f"<t:{int(state['expires'].timestamp())}:R>" if state["expires"] else "Unavailable",inline=True)
            embed.add_field(name="Standby node(s)",value="\n".join(standby)[:1024] or "None registered",inline=False)
            embed.add_field(name="Control-plane database",value="Connected",inline=True)
            embed.add_field(name="Bot uptime",value=str(datetime.timedelta(seconds=int((now-self.started_at).total_seconds()))),inline=True)
            embed.add_field(name="Bot version",value=os.environ.get("BOT_VERSION","Not configured"),inline=True)
            embed.add_field(name="Management access",value="Guild owner (role settings not yet implemented)",inline=False)
            embed.add_field(name="Minimum role",value="Everyone (settings not yet implemented)",inline=True)
            embed.add_field(name="Listen channels",value="All (settings not yet implemented)",inline=True)
            embed.add_field(name="Audit channel",value="Disabled (settings not yet implemented)",inline=True)
            embed.set_footer(text=f"Node {NODE} · Live HA control-plane snapshot")
            await interaction.followup.send(embed=embed,ephemeral=True)

        self.tree.add_command(admin)

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
