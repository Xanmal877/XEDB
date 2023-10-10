pip install -r requirements.txt

REM Run the Python script with the environment variables as arguments
Python DiscordBot.py %DISCORD_BOT_TOKEN% %ENDPOINT% %CHANNEL_ID%

pause
