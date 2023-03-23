import os
import requests
import telebot
from sql_helper.current_running_game_sql import addGame_sql, getGame_sql, removeGame_sql
from dotenv import load_dotenv
load_dotenv(verbose=True)

BOT_TOKEN = os.environ.get('BOT_TOKEN', None)
ALLOW_CHATS = [-1001625589718]
INVOKE_CMDS = ['lead someone..', 'take lead', 'take lead..', 'take lead guys', 'take lead guys..']
INVOKE_CMDS = ['nonono']
WORD = ['hhghgh']

def sendRefuseLeadInlineBtn(chat_id, message):
    first_name = message.from_user.first_name
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': f"{first_name} refused to lead!",
        'reply_markup': {
            "inline_keyboard": [[{"text": "I want to be a leader!", "callback_data": "start_game_from_refuse"}]]
        }
    }
    r = requests.post(url, json=payload)
    return r

def sendStartGameInlineBtn(chat_id, message):
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

def sendGuessedWordInlineBtn(chat_id, message, word):
    first_name = message.from_user.first_name
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': f"{first_name} found the word! **{word}**",
        'parse_mode': 'Markdown',
        'reply_markup': {
            "inline_keyboard": [[{"text": "New game", "callback_data": "start_game"}]]
        }
    }
    r = requests.post(url, json=payload)
    return r

def startGame(message):
    # Init game and generate word
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    user_obj = message.from_user
    WORD[0] = "getword".lower()
    addGame_sql(chatId, user_obj.id, 0, WORD[0])
    sendStartGameInlineBtn(chatId, message)
    # Save word to database
    bot.register_next_step_handler_by_chat_id(chatId, catchWord)
    return WORD[0]

def stopGame(message, isRefused=False):
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    removeGame_sql(chatId)
    if isRefused:
        sendRefuseLeadInlineBtn(chatId, message)
    else:
        bot.send_message(chatId, '❌ The game is stopped!\nTo start a new game, use command:\n/game@CrocodileGameENN_bot')
    # Delete word from database
    bot.clear_step_handler_by_chat_id(chatId)

def changeWord(message):
    # Generate new word and revoke old one
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    user_obj = message.from_user
    WORD[0] = "changedWord".lower()
    addGame_sql(chatId, user_obj.id, 0, WORD[0])
    bot.send_message(chatId, f'✅ [{user_obj.first_name}](tg://user?id={user_obj.id}) has changed the word!')
    # Save word to database
    bot.clear_step_handler_by_chat_id(chatId)
    bot.register_next_step_handler_by_chat_id(chatId, catchWord)
    return WORD[0]

def catchWord(message):
    # Check if user guessed the word
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    print(message.text.lower(), WORD[0])
    if message.text.lower() != WORD[0]:
        bot.send_message(chatId, '❌ Wrong word!')
        bot.register_next_step_handler_by_chat_id(chatId, catchWord)
        return
    sendGuessedWordInlineBtn(chatId, message, WORD[0])
    # Delete word from database
    bot.clear_step_handler_by_chat_id(chatId)

def getCurrGame(chatId, userId):
    # Get current game from database
    curr_game = getGame_sql(chatId)
    if curr_game is None:
        # Game is not started
        return 1
    elif int(curr_game[1]) != userId:
        # User is not a leader
        return 0
    else:
        # User is a leader
        return curr_game

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
        startGame(message)

@bot.message_handler(commands=['stop'])
def stop_game(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        stopGame(message)

@bot.message_handler(content_types=['text'])
def send_text(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        m = message.text.lower()
        if m in INVOKE_CMDS:
            r = sendRefuseLeadInlineBtn(chatId, message)
            print(r)


# Callbacks handler for inline buttons ---------------------------------------- #
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chatId = call.message.chat.id
    if chatId in ALLOW_CHATS:
        curr_game = getCurrGame(chatId, call.from_user.id)
        if call.data == 'start_game':
            if curr_game == 1:
                word = startGame(call)
                bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
            elif curr_game == 0:
                bot.answer_callback_query(call.id, "❌ Game has already started by someone else!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ Game has already started by you!", show_alert=True)
        elif call.data == 'start_game_from_refuse':
            if curr_game == 1:
                word = startGame(call)
                bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                bot.delete_message(chatId, call.message.message_id)
            elif curr_game == 0:
                bot.answer_callback_query(call.id, "❌ Game has already started by someone else!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ Game has already started by you!", show_alert=True)
        elif call.data == 'see_word':
            if curr_game == 1:
                bot.answer_callback_query(call.id, "❌ Game has not started yet!", show_alert=True)
            elif curr_game == 0:
                bot.answer_callback_query(call.id, "❌ Only leader can see the word!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, f"Word: {WORD[0]}", show_alert=True)
        elif call.data == 'generate_hints':
            if curr_game == 1:
                bot.answer_callback_query(call.id, "❌ Game has not started yet!", show_alert=True)
            elif curr_game == 0:
                bot.answer_callback_query(call.id, "❌ Only leader can generate hints!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Hint 1:\nHint 2:\nHint 3:\nHint 4:\nHint 5:\n\n❕ You are free to use your own customised hints!", show_alert=True)
        elif call.data == 'change_word':
            if curr_game == 1:
                bot.answer_callback_query(call.id, "❌ Game has not started yet!", show_alert=True)
            elif curr_game == 0:
                bot.answer_callback_query(call.id, "❌ Only leader can change the word!", show_alert=True)
            else:
                word = changeWord(call)
                bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
        elif call.data == 'drop_lead':
            if curr_game == 1:
                bot.answer_callback_query(call.id, "❌ Game has not started yet!", show_alert=True)
            elif curr_game == 0:
                bot.answer_callback_query(call.id, "❌ You are not laeding the game!", show_alert=True)
            else:
                stopGame(call, isRefused=True)
                bot.delete_message(chatId, call.message.message_id)

# ------------------------------------------------------------- #
# Enable save next step handlers, so they work for all messages
bot.enable_save_next_step_handlers(delay=2)
# Load next_step_handlers from a file
bot.load_next_step_handlers()
print("Bot is running...")
bot.infinity_polling(none_stop=True)
