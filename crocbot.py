import os
import requests
import telebot
from dotenv import load_dotenv
load_dotenv(verbose=True)

BOT_TOKEN = os.environ.get('BOT_TOKEN', None)
ALLOW_CHATS = [-1001625589718]
INVOKE_CMDS = ['lead someone..', 'take lead', 'take lead..', 'take lead guys', 'take lead guys..']
INVOKE_CMDS = ['nonono']

def sendRefuseLeadInlineBtn(message):
    chat_id = message.chat.id
    first_name = message.from_user.first_name
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': f"{first_name} refused to lead!",
        'reply_markup': {
            "inline_keyboard": [[{"text": "I want to be a leader!", "callback_data": "new_game"}]]
        }
    }
    r = requests.post(url, json=payload)
    return r

def sendStartGameInlineBtn(message):
    chat_id = message.chat.id
    first_name = message.from_user.first_name
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': f"**{first_name} is explaining the word!**",
        'parse_mode': 'Markdown',
        'reply_markup': {
            "inline_keyboard": [
                [
                    {"text": "See word", "callback_data": "see_word"},
                    {"text": "Generate hints", "callback_data": "generate_hints"}
                ],
                [
                    {"text": "Change word", "callback_data": "change_word"},
                    {"text": "Drop lead", "callback_data": "drop_lead"}
                ]
            ]
        }
    }
    r = requests.post(url, json=payload)
    return r

bot = telebot.TeleBot(BOT_TOKEN)
@bot.message_handler(commands=['start'])
def start_cmd(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        bot.send_message(chatId, 'Hey!\nI am alive and working properly.')

@bot.message_handler(commands=['game'])
def start_game(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        sendStartGameInlineBtn(message)

@bot.message_handler(commands=['stop'])
def stop_game(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        bot.send_message(chatId, '❌ The game is stopped!\nTo start a new game, use command:\n/game@CrocodileGameENN_bot')
    
@bot.message_handler(content_types=['text'])
def send_text(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        m = message.text.lower()
        if m in INVOKE_CMDS:
            r = sendRefuseLeadInlineBtn(message)
            print(r)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chatId = call.message.chat.id
    if chatId in ALLOW_CHATS:
        if call.data == 'new_game':
            sendStartGameInlineBtn(call)
            bot.delete_message(chatId, call.message.message_id)
            bot.answer_callback_query(call.id, "Word: Radio", show_alert=True)
        elif call.data == 'see_word':
            bot.answer_callback_query(call.id, "Word: Radio", show_alert=True)
        elif call.data == 'generate_hints':
            bot.answer_callback_query(call.id, "Hint 1:\nHint 2:\nHint 3:\nHint 4:\nHint 5:\n\n❕ You are free to use your own customised hints!", show_alert=True)
        elif call.data == 'change_word':
            bot.answer_callback_query(call.id, "Word: Light", show_alert=True)
        elif call.data == 'drop_lead':
            sendRefuseLeadInlineBtn(call)
            bot.delete_message(chatId, call.message.message_id)


print("Bot is running...")
bot.infinity_polling(none_stop=True)
