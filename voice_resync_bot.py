import os
import asyncio
import discord

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
YOUR_USER_ID = os.getenv("USER_ID", "").strip()

# ====== CONFIG (fill these in) ======
MOVE_PAUSE_SECONDS = 0.6         # how long you're moved away
COOLDOWN_SECONDS = 12.0          # prevents repeated moves on rapid joins
# ====================================

async def get_member_safe(guild: discord.Guild, user_id: int) -> discord.Member | None:
    m = guild.get_member(user_id)
    if m is not None:
        return m
    try:
        return await guild.fetch_member(user_id)  # API fallback (reliable)
    except (discord.NotFound, discord.Forbidden):
        return None

class ResyncMover(discord.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._lock = asyncio.Lock()
        self._cooldown_until = 0.0

    async def on_ready(self):
        print(f"Logged in as {self.user} (id={self.user.id})")

    async def on_voice_state_update(self, member, before, after):
        # Ignore the bot itself
        if self.user and member.id == self.user.id:
            print(f"returning because detected bot id or user id")
            return

        # Ignore other bots
        if member.bot:
            return
            
        # Ignore YOU (so your own join/moves don't trigger a resync)
        if member.id == int(YOUR_USER_ID):
            print("returning because detected YOUR user id")
            return

        # Determine guild safely
        channel = after.channel or before.channel
        if channel is None:
            print(f"Channel is none")
            return

        guild = channel.guild

        # DEBUG Events
        print(f"VOICE EVENT: member={member} before={before.channel} after={after.channel}")

        you = await get_member_safe(guild, YOUR_USER_ID)
        if you is None or you.voice is None or you.voice.channel is None:
            print("you is none / not in voice")
            return
        
        
        # # Find YOU
        # you = guild.get_member(YOUR_USER_ID)
        # if you is None or you.voice is None or you.voice.channel is None:
        #     print(f"you is none")
        #     return

        # Dynamic target: wherever YOU are
        your_channel = you.voice.channel

        # Detect someone joining YOUR channel
        joined_your_channel = (
            after.channel is not None and
            after.channel.id == your_channel.id and
            (before.channel is None or before.channel.id != your_channel.id)
        )

        if not joined_your_channel:
            print(f"Event was not joining your channel")
            return

        # Cooldown
        now = asyncio.get_running_loop().time()
        if now < self._cooldown_until:
            return

        async with self._lock:
            now = asyncio.get_running_loop().time()
            if now < self._cooldown_until:
                return
            self._cooldown_until = now + COOLDOWN_SECONDS

            resync_ch = guild.afk_channel
            if resync_ch is None:
                print(f"[skip] No AFK channel configured in guild '{guild.name}' ({guild.id}).")
                return


            try:
                print(f"[resync] {member} joined {your_channel.name}. Moving you...")
                await you.move_to(resync_ch, reason="Voice resync cycle")
                await asyncio.sleep(MOVE_PAUSE_SECONDS)
                await you.move_to(your_channel, reason="Voice resync cycle")
                print("[resync] done.")
            except discord.Forbidden:
                print("Forbidden: missing Move Members or role hierarchy issue.")
            except Exception as e:
                print(f"Move error: {e}")



def main():
    if not TOKEN:
        raise RuntimeError("Set DISCORD_TOKEN as an environment variable (DISCORD_TOKEN).")

    intents = discord.Intents.default()
    intents.guilds = True
    intents.voice_states = True

    client = ResyncMover(intents=intents)
    client.run(TOKEN)


if __name__ == "__main__":
    main()