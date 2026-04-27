# safeword.py (FINAL - CRASH SAFE + HTML FALLBACK)

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import asyncio
import io
from datetime import datetime, timezone

import discord
from discord.ext import commands

# SAFE IMPORT (NO CRASH)
try:
    import chat_exporter
except ImportError:
    chat_exporter = None
    print("[WARNING] chat_exporter NOT installed — transcript disabled")

from ..utils.discord_resolvers import resolve_role_any, resolve_channel_any, normalize
from ..utils.io_helpers import aio_retry
from ..utils.perms import staff_check_factory


@dataclass
class SlowmodeSnapshot:
    prior_slowmode: Optional[int]


STAFF_FALLBACK_NAME = "Staff"


class Safeword(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._state: Dict[int, SlowmodeSnapshot] = {}
        self._last_trigger_at: Dict[int, float] = {}
        self._processing: set[int] = set()
        self._staff_check = staff_check_factory(lambda: self.bot.config)

    def _cfg(self) -> Dict[str, Any]:
        return (self.bot.config or {}).get("safeword") or {}

    # ---------------------------
    # HTML EXPORT (SAFE)
    # ---------------------------
    async def _export_html(self, channel: discord.TextChannel, limit: int):
        if not chat_exporter:
            return None

        try:
            transcript = await chat_exporter.export(
                channel,
                limit=min(100, max(1, limit)),
                tz_info="UTC",
                military_time=True,
                bot=self.bot
            )

            if transcript is None:
                return None

            return discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"safeword-{channel.id}.html"
            )

        except Exception as e:
            print(f"[EXPORT ERROR] {e}")
            return None

    # ---------------------------
    # SLOWMODE APPLY
    # ---------------------------
    async def _apply_slowmode(self, channel: discord.TextChannel):
        try:
            prior = channel.slowmode_delay

            await aio_retry(
                lambda: channel.edit(
                    slowmode_delay=3600,
                    reason="Safeword triggered"
                ),
                ctx="slowmode"
            )

            self._state[channel.id] = SlowmodeSnapshot(prior)
            return None

        except Exception as e:
            print(f"[SLOWMODE ERROR] {e}")
            return "error"

    async def _release_slowmode(self, channel: discord.TextChannel):
        try:
            snap = self._state.get(channel.id)

            if snap:
                await aio_retry(
                    lambda: channel.edit(
                        slowmode_delay=snap.prior_slowmode or 0,
                        reason="Safeword release"
                    ),
                    ctx="release"
                )

                self._state.pop(channel.id, None)

            return None

        except Exception as e:
            print(f"[RELEASE ERROR] {e}")
            return "error"

    # ---------------------------
    # LISTENER (STRICT MATCH)
    # ---------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            if message.author.bot or not message.guild:
                return

            cfg = self._cfg()

            content = message.content.strip()
            trigger = (cfg.get("trigger") or "!STOP!").strip()
            release = (cfg.get("release_trigger") or "!Release").strip()

            # STRICT ONLY
            if content == trigger:
                await self._handle_trigger(message)

            elif content == release:
                await self._handle_release(message)

        except Exception as e:
            print(f"[LISTENER ERROR] {e}")

    # ---------------------------
    # TRIGGER HANDLER
    # ---------------------------
    async def _handle_trigger(self, message: discord.Message):

        ch = message.channel

        if not isinstance(ch, discord.TextChannel):
            return

        if ch.id in self._processing:
            return

        self._processing.add(ch.id)

        try:
            cfg = self._cfg()

            # cooldown
            cd = int(cfg.get("cooldown_seconds") or 0)
            now = asyncio.get_event_loop().time()

            if now - self._last_trigger_at.get(ch.id, 0) < cd:
                await ch.send("⏳ Safeword already triggered recently.")
                return

            self._last_trigger_at[ch.id] = now

            # ping roles
            mentions = []
            for token in cfg.get("roles_to_ping") or []:
                role = resolve_role_any(message.guild, token)
                if role:
                    mentions.append(role.mention)

            if mentions:
                await ch.send(
                    " ".join(mentions),
                    allowed_mentions=discord.AllowedMentions(roles=True)
                )

            # alert embed
            text = (cfg.get("lock_message") or {}).get("text") or "🛑 Safeword triggered."
            img = (cfg.get("lock_message") or {}).get("image_url")

            embed = discord.Embed(
                description=text,
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.set_author(
                name=f"{message.author} • {message.author.id}",
                icon_url=message.author.display_avatar.url
            )

            if img:
                embed.set_image(url=img)

            await ch.send(embed=embed)

            # transcript logging
            log_id = cfg.get("log_channel_id")

            if isinstance(log_id, int):
                log_ch = resolve_channel_any(message.guild, log_id)

                if isinstance(log_ch, discord.TextChannel):

                    if chat_exporter:
                        file = await self._export_html(ch, 25)

                        if file:
                            await log_ch.send(
                                content=f"📦 Safeword triggered in {ch.mention}",
                                file=file
                            )
                        else:
                            await log_ch.send("⚠️ Transcript failed to generate.")

                    else:
                        await log_ch.send("⚠️ Transcript unavailable (chat_exporter not installed)")

            # apply slowmode
            err = await self._apply_slowmode(ch)

            if err:
                await ch.send("❌ Failed to apply slowmode.")

        finally:
            self._processing.remove(ch.id)

    # ---------------------------
    # RELEASE
    # ---------------------------
    async def _handle_release(self, message: discord.Message):

        ch = message.channel

        if not isinstance(ch, discord.TextChannel):
            return

        cfg = self._cfg()

        if not any(normalize(r.name) == normalize(STAFF_FALLBACK_NAME) for r in message.author.roles):
            await ch.send("❌ Staff only.")
            return

        err = await self._release_slowmode(ch)

        await ch.send("✅ Safeword released. Slowmode restored.")

        log_id = cfg.get("log_channel_id")

        if isinstance(log_id, int):
            log_ch = resolve_channel_any(message.guild, log_id)

            if isinstance(log_ch, discord.TextChannel):
                await log_ch.send(
                    f"🟢 Safeword released in {ch.mention} by {message.author.mention}"
                )

        if err:
            await ch.send("⚠️ Something failed during release.")

    # ---------------------------
    # CLEANUP COMMAND
    # ---------------------------
    @commands.command(name="thanos")
    async def thanos_cmd(self, ctx, user_id: int, depth: int = 25):

        if not self._staff_check(ctx):
            return await ctx.send("❌ Staff only.")

        msgs = []

        async for m in ctx.channel.history(limit=depth):
            if m.author.id == user_id:
                msgs.append(m)

        for m in msgs:
            try:
                await m.delete()
            except:
                pass

        await ctx.send(f"✅ Removed {len(msgs)} messages.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Safeword(bot))
