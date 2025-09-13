from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# Deine API-Daten von https://my.telegram.org/apps
API_ID = 123456     # <--- hier deine api_id einsetzen
API_HASH = "abcdef1234567890"  # <--- hier dein api_hash einsetzen

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("Dein STRING_SESSION:\n")
    print(client.session.save())
