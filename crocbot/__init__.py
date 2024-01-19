import os
from dotenv import load_dotenv
if not load_dotenv(verbose=True):
    #raise RuntimeError('Failed to load .env file')
if os.environ.get('ENV') == 'PROD':
    import crocbot
else:
    import crocbot_dev as crocbot



# Environment variables info -------------------------------------------------- #
# 
# ENV: PROD or DEV (default) - bot production or development mode
# BOT_TOKEN: Telegram bot token
# DATABASE_URL: PostgreSQL database URL
# AI_PLATFORM: AI-model platform (default: google)
# AI_API_KEY: API key for AI services
# 
# BLOCK_CHATS: Chat id to block bot (separated by `,`)
# CROCO_CHATS: Chat id to enable CROCO AI (separated by `,`)
# TOP10_CHAT_NAMES: {chat_id: chat_name,...} - Chat names for each chat_id in TOP10 CHATS cmd
