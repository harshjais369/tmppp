import requests
import telebot

token = ""
ALLOW_CHATS = [-1001625589718]
INVOKE_CMDS = ['lead someone..', 'take lead', 'take lead..', 'take lead guys', 'take lead guys..']
INVOKE_CMDS = ['nonono']

def sendInlineButton(chat_id):
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': "Exception refused to lead!",
        'reply_markup': {
            "inline_keyboard": [[{"text": "I want to be a leader!", "callback_data": "call"}]]
        }
    }
    r = requests.post(url, json=payload)
    return r

def sendStartGameInlineBtn(chat_id, message):
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': f"**{message.from_user.first_name} is explaining the word!**",
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

bot = telebot.TeleBot(token)
@bot.message_handler(commands=['start'])
def start_cmd(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        bot.send_message(chatId, 'Hey!\nI am alive and working properly.')

@bot.message_handler(commands=['game'])
def start_game(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        sendStartGameInlineBtn(chatId, message)

@bot.message_handler(commands=['stop'])
def stop_game(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        bot.send_message(chatId, 'The game is stopped!\nTo start a new game, use /game@CrocodileGameENN_bot command.')
    
@bot.message_handler(content_types=['text'])
def send_text(message):
    m = message.text.lower()
    if m in INVOKE_CMDS:
        r = sendInlineButton(message.chat.id)
        print(r)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    print(call.message.chat.id)
    for ch in ALLOW_CHATS:
        bot.send_message(ch,  f"-> Someone clicked on button:\n\n{call.from_user}")

print("Bot is running...")
bot.infinity_polling(interval=0, timeout=20)
