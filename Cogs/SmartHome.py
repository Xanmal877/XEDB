import discord
from discord.ext import commands
import asyncio
from kasa import SmartBulb

class SmartHome(commands.Cog):
    def __init__(self, client):
        self.client = client
        # List of user IDs allowed to control the lights
        self.allowed_users = [
            175421668850794506,  # Replace with actual user IDs (without quotes since they are integers)
            427689980241117184   # Replace with actual user IDs
            # Add more user IDs as needed
        ]
        self.bulb_ips = {
            'bulb1': '192.168.1.45',
            'bulb2': '192.168.1.46'
        }

    @commands.Cog.listener()
    async def on_ready(self):
        print("Smart Cog ready to control!")
        await self.client.tree.sync()

    async def control_light(self, ip, state):
            bulb = SmartBulb(ip)
            await bulb.update()  # Fetch the latest state
            if state == 'on':
                await bulb.turn_on()
            else:
                await bulb.turn_off()

    @discord.app_commands.command(name="lightoff", description="Turn off the lights")
    async def light_off(self, interaction: discord.Interaction):
        # Ensure to use self.allowed_users here to access the instance variable
        if interaction.user.id in self.allowed_users:
            tasks = [self.control_light(ip, 'off') for ip in self.bulb_ips.values()]
            await asyncio.gather(*tasks)
            await interaction.response.send_message("Bedroom lights turned off!")
        else:
            await interaction.response.send_message("You do not have permission to control the lights.", ephemeral=True)

    @discord.app_commands.command(name="lighton", description="Turn on the lights")
    async def light_on(self, interaction: discord.Interaction):
        # Ensure to use self.allowed_users here as well
        if interaction.user.id in self.allowed_users:
            tasks = [self.control_light(ip, 'on') for ip in self.bulb_ips.values()]
            await asyncio.gather(*tasks)
            await interaction.response.send_message("Bedroom lights turned on!")
        else:
            await interaction.response.send_message("You do not have permission to control the lights.", ephemeral=True)

# When you load the cog, make sure to pass the instance of the bot client.
async def setup(client):
    await client.add_cog(SmartHome(client))
