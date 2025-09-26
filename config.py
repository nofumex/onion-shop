import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
CRYPTOBOT_API_TOKEN = os.getenv("CRYPTOBOT_API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) if os.getenv("CHANNEL_ID") else 0
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")