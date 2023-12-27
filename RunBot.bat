
python -m venv XanDiscordBotEnv
timeout 2

call XanDiscordBotEnv\Scripts\activate

timeout 5

pip install -r piplist.txt
timeout 3

python XanDiscordBot.py
timeout 5
