"""Настройки tg-bot-friend: токен из окружения, владелец и источник курсов."""
import os

bot_token = os.environ.get("BOT_TOKEN", "")
owner_id = int(os.environ.get("ADMIN_ID") or 0)
prices_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,litecoin,tether&vs_currencies=usd"
