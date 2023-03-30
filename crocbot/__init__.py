import os
from dotenv import load_dotenv
load_dotenv(verbose=True)
if os.environ.get('ENV') == 'PROD':
    import crocbot
else:
    import crocbot_dev as crocbot



# Environment variables info -------------------------------------------------- #
# 
# ENV: PROD or DEV (default) - bot production or development mode
# BOT_TOKEN: Telegram bot token
# DATABASE_URL: PostgreSQL database URL
# OPENAI_API_KEY: OpenAI API key
