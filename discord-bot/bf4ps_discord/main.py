"""Leader-only Discord gateway. Standby never connects."""
import asyncio
import logging
import os
import signal
import time
import discord
from discord import app_commands
import datetime
from . import leases, guild_settings

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
        self._audit_starts={}
        self._audit_outcomes={}
        self._audit_channels={}

        self.tree=app_commands.CommandTree(self)
        @self.tree.command(name="ping",description="Check the BF4 Player Stats bot connection")
        async def ping(interaction: discord.Interaction):
            try:
                valid=await asyncio.wait_for(asyncio.to_thread(
                    leases.is_current,DSN,NODE,self.authority),timeout=5)
            except Exception:
                valid=False
            if not valid:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.response.send_message("Bot leadership is changing. Please retry.",ephemeral=True)
                return
            await interaction.response.send_message("BF4 Player Stats bot is online! 🐹",ephemeral=True)

        admin=app_commands.Group(name="admin",description="BF4 Player Stats server administration")

        async def manager_settings(interaction):
            if interaction.guild is None:
                return None
            try:
                settings=await asyncio.wait_for(asyncio.to_thread(guild_settings.get,DSN,interaction.guild.id),timeout=5)
                return settings
            except Exception:
                return None

        @admin.command(name="managementrole",description="Set or clear the role allowed to administer the bot")
        @app_commands.describe(role="Management role; omit to restore guild-owner-only access")
        async def managementrole(interaction: discord.Interaction, role: discord.Role | None = None):
            if interaction.guild is None:
                self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                await interaction.response.send_message("This command requires a server.",ephemeral=True)
                return
            settings=await manager_settings(interaction)
            if settings is None:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.response.send_message("Settings database unavailable; no changes made.",ephemeral=True)
                return
            if not guild_settings.allowed(interaction.user,interaction.guild,settings):
                self.audit_result(interaction,"DENIED","Insufficient management permissions")
                await interaction.response.send_message("You are not authorized to manage this bot.",ephemeral=True)
                return
            if role is not None and (role.is_default() or role.is_bot_managed() or role.is_integration()):
                self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                await interaction.response.send_message("Choose an assignable server role, not @everyone or a managed role.",ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            try:
                valid=await asyncio.wait_for(asyncio.to_thread(leases.is_current,DSN,NODE,self.authority),timeout=5)
                if not valid:
                    raise RuntimeError("leadership changed")
                await asyncio.wait_for(asyncio.to_thread(guild_settings.set_management_role,
                    DSN,interaction.guild.id,role.id if role else None,interaction.user.id),timeout=5)
            except Exception:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.followup.send("Could not save the setting; please retry.",ephemeral=True)
                return
            await interaction.followup.send(
                f"Management access: {role.mention} and higher roles, plus the guild owner." if role else
                "Management access reset to guild owner only.",ephemeral=True)

        @admin.command(name="minimumrole",description="Set the minimum role required for player statistics commands")
        @app_commands.describe(role="Minimum player role; omit to allow Everyone")
        async def minimumrole(interaction: discord.Interaction, role: discord.Role | None = None):
            if interaction.guild is None:
                self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                await interaction.response.send_message("This command requires a server.",ephemeral=True)
                return
            settings=await manager_settings(interaction)
            if settings is None:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.response.send_message("Settings database unavailable; no changes made.",ephemeral=True)
                return
            if not guild_settings.allowed(interaction.user,interaction.guild,settings):
                self.audit_result(interaction,"DENIED","Insufficient management permissions")
                await interaction.response.send_message("You are not authorized to manage this bot.",ephemeral=True)
                return
            if role is not None and (role.is_default() or role.is_bot_managed() or role.is_integration()):
                self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                await interaction.response.send_message("Choose a normal server role, not @everyone or a managed role.",ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            try:
                valid=await asyncio.wait_for(asyncio.to_thread(leases.is_current,DSN,NODE,self.authority),timeout=5)
                if not valid:
                    raise RuntimeError("leadership changed")
                await asyncio.wait_for(asyncio.to_thread(guild_settings.set_minimum_role,
                    DSN,interaction.guild.id,role.id if role else None,interaction.user.id),timeout=5)
            except Exception:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.followup.send("Could not save the setting; please retry.",ephemeral=True)
                return
            await interaction.followup.send(
                f"Player commands require {role.mention} or higher; authorized admins bypass this restriction." if role else
                "Player commands are now available to Everyone (subject to listen-channel restrictions).",ephemeral=True)

        @admin.command(name="listenchannel",description="Add or remove a channel for player commands")
        @app_commands.describe(action="Add or remove an allowed channel",channel="Text channel for player commands")
        @app_commands.choices(action=[app_commands.Choice(name="Add",value="add"),app_commands.Choice(name="Remove",value="remove")])
        async def listenchannel(interaction: discord.Interaction, action: app_commands.Choice[str], channel: str):
            if interaction.guild is None:
                self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                await interaction.response.send_message("This command requires a server.",ephemeral=True)
                return
            settings=await manager_settings(interaction)
            if settings is None:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.response.send_message("Settings database unavailable; no changes made.",ephemeral=True)
                return
            if not guild_settings.allowed(interaction.user,interaction.guild,settings):
                self.audit_result(interaction,"DENIED","Insufficient management permissions")
                await interaction.response.send_message("You are not authorized to manage this bot.",ephemeral=True)
                return
            if not channel.isdecimal() or not isinstance(interaction.guild.get_channel(int(channel)),discord.TextChannel):
                self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                await interaction.response.send_message("Choose a valid server text channel.",ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            try:
                valid=await asyncio.wait_for(asyncio.to_thread(leases.is_current,DSN,NODE,self.authority),timeout=5)
                if not valid:
                    raise RuntimeError("leadership changed")
                channels=await asyncio.wait_for(asyncio.to_thread(guild_settings.update_listen_channel,
                    DSN,interaction.guild.id,int(channel),action.value=="add",interaction.user.id),timeout=5)
            except ValueError as exc:
                self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                await interaction.followup.send(str(exc)+". No changes made.",ephemeral=True)
                return
            except Exception:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.followup.send("Could not update listen channels; please retry.",ephemeral=True)
                return
            if channels:
                mentions=[f"<#{cid}>" for cid in channels]
                await interaction.followup.send("Player listen channels: "+", ".join(mentions)[:1700]+". Admins can use all channels.",ephemeral=True)
            else:
                await interaction.followup.send("No listen channels configured — player commands allowed in all channels.",ephemeral=True)

        @listenchannel.autocomplete("channel")
        async def listenchannel_autocomplete(interaction: discord.Interaction, current: str):
            if interaction.guild is None:
                return []
            settings=await manager_settings(interaction)
            if settings is None or not guild_settings.allowed(interaction.user,interaction.guild,settings):
                return []
            try:
                configured=guild_settings.listen_channel_ids(settings)
            except ValueError:
                return []
            action=interaction.namespace.action
            action=action.value if isinstance(action,app_commands.Choice) else action
            if action not in ("add","remove"):
                return []
            channels=[c for c in interaction.guild.text_channels if (c.id not in configured if action=="add" else c.id in configured)]
            query=current.lower().lstrip("#")
            return [app_commands.Choice(name="#"+c.name,value=str(c.id)) for c in channels if query in c.name.lower() or query in str(c.id)][:25]

        @admin.command(name="logchannel",description="Set or remove the audit channel")
        @app_commands.describe(action="Set or remove",channel="Choose a suggested channel")
        @app_commands.choices(action=[app_commands.Choice(name="Set",value="set"),app_commands.Choice(name="Remove",value="remove")])
        async def logchannel(interaction: discord.Interaction, action: app_commands.Choice[str], channel: str):
            settings=await manager_settings(interaction)
            if settings is None or interaction.guild is None:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.response.send_message("Settings unavailable.",ephemeral=True)
                return
            if not guild_settings.allowed(interaction.user,interaction.guild,settings):
                self.audit_result(interaction,"DENIED","Insufficient management permissions")
                await interaction.response.send_message("Not authorized.",ephemeral=True)
                return
            selected=interaction.guild.get_channel(int(channel)) if channel.isdecimal() else None
            if not isinstance(selected,discord.TextChannel):
                self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                await interaction.response.send_message("Choose a valid text channel from suggestions.",ephemeral=True)
                return
            if action.value=="set":
                perms=selected.permissions_for(interaction.guild.me)
                if not (perms.view_channel and perms.send_messages and perms.embed_links):
                    self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                    await interaction.response.send_message("Bot needs View Channel, Send Messages and Embed Links.",ephemeral=True)
                    return
            await interaction.response.defer(ephemeral=True)
            try:
                if not await asyncio.wait_for(asyncio.to_thread(leases.is_current,DSN,NODE,self.authority),timeout=5):
                    raise RuntimeError("leadership changed")
                await asyncio.wait_for(asyncio.to_thread(guild_settings.change_audit_channel,DSN,
                    interaction.guild.id,selected.id,action.value=="set",interaction.user.id),timeout=5)
                if action.value=="remove":
                    self._audit_channels[interaction.id]=selected.id
            except ValueError as exc:
                self.audit_result(interaction,"BLOCKED","Invalid input or blocked operation")
                await interaction.followup.send(str(exc)+". No changes made.",ephemeral=True)
                return
            except Exception:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.followup.send("Could not update audit channel; retry.",ephemeral=True)
                return
            await interaction.followup.send(f"Audit channel set to {selected.mention}." if action.value=="set" else
                                            "Audit logging disabled.",ephemeral=True)

        @logchannel.autocomplete("channel")
        async def logchannel_autocomplete(interaction: discord.Interaction, current: str):
            if interaction.guild is None:
                return []
            settings=await manager_settings(interaction)
            if settings is None or not guild_settings.allowed(interaction.user,interaction.guild,settings):
                return []
            action=interaction.namespace.action
            action=action.value if isinstance(action,app_commands.Choice) else action
            configured=settings.get(guild_settings.AUDIT_CHANNEL)
            if action=="remove":
                channels=[interaction.guild.get_channel(int(configured))] if configured and configured.isdecimal() else []
            elif action=="set":
                channels=[c for c in interaction.guild.text_channels if str(c.id)!=configured]
            else:
                return []
            query=current.lower().lstrip("#")
            return [app_commands.Choice(name="#"+c.name,value=str(c.id)) for c in channels
                    if isinstance(c,discord.TextChannel) and (query in c.name.lower() or query in str(c.id))][:25]

        @admin.command(name="status",description="Show private bot and HA cluster status")
        async def admin_status(interaction: discord.Interaction):
            settings=await manager_settings(interaction)
            if settings is None:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.response.send_message("Settings database unavailable or command used outside a server.",ephemeral=True)
                return
            if not guild_settings.allowed(interaction.user,interaction.guild,settings):
                self.audit_result(interaction,"DENIED","Insufficient management permissions")
                await interaction.response.send_message("You are not authorized to manage this bot.",ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True,thinking=True)
            try:
                state=await asyncio.wait_for(asyncio.to_thread(
                    leases.status_snapshot,DSN,NODE,self.authority),timeout=6)
            except Exception:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
                await interaction.followup.send("Control-plane database unavailable; status cannot be verified.",ephemeral=True)
                return
            if not state["authorized"]:
                self.audit_result(interaction,"FAILED","Service unavailable or operation failed")
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
            configured=settings.get(guild_settings.MANAGEMENT_ROLE)
            management_role=interaction.guild.get_role(int(configured)) if configured and configured.isdecimal() else None
            management_label=(f"{management_role.mention} and higher roles + guild owner" if management_role else
                              "Guild owner only" if not configured else "Configured role missing — guild owner only")
            embed.add_field(name="Management access",value=management_label,inline=False)
            minimum_id=settings.get(guild_settings.MINIMUM_ROLE)
            minimum=interaction.guild.get_role(int(minimum_id)) if minimum_id and minimum_id.isdecimal() else None
            minimum_label=(f"{minimum.mention} and higher" if minimum else
                           "Everyone" if not minimum_id else "Configured role missing — player access denied")
            embed.add_field(name="Minimum role",value=minimum_label,inline=True)
            try:
                listen_ids=guild_settings.listen_channel_ids(settings)
                listen_label=", ".join(f"<#{cid}>" for cid in sorted(listen_ids))[:1024] if listen_ids else "All"
            except ValueError:
                listen_label="Invalid configuration — player access denied"
            embed.add_field(name="Listen channels",value=listen_label,inline=True)
            audit_id=settings.get(guild_settings.AUDIT_CHANNEL)
            audit_channel=interaction.guild.get_channel(int(audit_id)) if audit_id and audit_id.isdecimal() else None
            embed.add_field(name="Audit channel",value=audit_channel.mention if audit_channel else
                            ("Disabled" if not audit_id else "Configured channel missing"),inline=True)
            embed.set_footer(text=f"Node {NODE} · Live HA control-plane snapshot")
            await interaction.followup.send(embed=embed,ephemeral=True)

        self.tree.add_command(admin)

    def audit_result(self, interaction, result, reason=None):
        self._audit_outcomes[interaction.id]=(result,reason)

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.application_command:
            self._audit_starts[interaction.id]=time.monotonic()

    async def _send_audit(self, interaction: discord.Interaction, result: str):
        started=self._audit_starts.pop(interaction.id,None)
        override=self._audit_channels.pop(interaction.id,None)
        outcome,reason=self._audit_outcomes.pop(interaction.id,("SUCCESS",None)) if result=="completed" else ("FAILED","Unhandled command error")
        if interaction.guild is None:
            return
        try:
            settings=await asyncio.wait_for(asyncio.to_thread(guild_settings.get,DSN,interaction.guild.id),timeout=4)
            raw=settings.get(guild_settings.AUDIT_CHANNEL)
            if override is None and (not raw or not raw.isdecimal()):
                return
            channel=interaction.guild.get_channel(override if override is not None else int(raw))
            if not isinstance(channel,discord.TextChannel):
                return
            command=interaction.command.qualified_name if interaction.command else "unknown"
            elapsed=f"{int((time.monotonic()-started)*1000)} ms" if started is not None else "unavailable"
            user=interaction.user
            embed=discord.Embed(title="BF4 Player Stats — Command audit",color=discord.Color.green() if outcome=="SUCCESS" else discord.Color.red(),timestamp=discord.utils.utcnow())
            embed.add_field(name="Command",value=f"`/{command}`",inline=False)
            embed.add_field(name="User",value=f"{discord.utils.escape_markdown(user.display_name)} (`{user.id}`)",inline=False)
            embed.add_field(name="Used in",value=f"<#{interaction.channel_id}> (`{interaction.channel_id}`)",inline=False)
            embed.add_field(name="Result",value=outcome,inline=True)
            if reason:
                embed.add_field(name="Reason",value=reason,inline=False)
            if interaction.command and interaction.command.qualified_name in ("admin logchannel","admin listenchannel"):
                action=interaction.namespace.action
                action=action.value if isinstance(action,app_commands.Choice) else action
                target=interaction.namespace.channel
                embed.add_field(name="Requested change",value=f"{action} · <#{target}>" if target and str(target).isdecimal() else str(action),inline=False)
            if override is not None:
                embed.add_field(name="Audit logging",value="Disabled — final entry in former audit channel",inline=False)
            embed.add_field(name="Duration",value=elapsed,inline=True)
            embed.set_footer(text=f"Guild {interaction.guild.id} · Node {NODE}")
            await channel.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            log.exception("audit_delivery_failed interaction=%s",interaction.id)

    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        await self._send_audit(interaction,"completed")

    async def on_app_command_error(self, interaction: discord.Interaction, error):
        log.error("app_command_error command=%s error=%r",interaction.command,error)
        await self._send_audit(interaction,"error")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("Command failed. Please retry.",ephemeral=True)
        except discord.HTTPException:
            pass

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
