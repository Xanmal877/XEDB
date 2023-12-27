@echo off
python -m venv XanDiscordBotEnv

call XanDiscordBotEnv\Scripts\activate

pip install -r piplist.txt

call cls

python XanDiscordBot.py
