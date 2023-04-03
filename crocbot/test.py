import os
import time
import requests
import telebot
import funcs
from sql_helper.current_running_game_sql import addGame_sql, getGame_sql, removeGame_sql
from sql_helper.rankings_sql import incrementPoints_sql, getUserPoints_sql, getTop25PlayersFromGroup_sql

BOT_TOKEN = os.environ.get('BOT_TOKEN', None)
BLOCK_CHATS = [int(x) for x in os.environ.get('BLOCK_CHATS', '').split(',') if x]
WORD = ['[Change this word]']
HINTS = []

def sendStartGameInlineBtn(chat_id, message):
    user_obj = message.from_user
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': f"**[{user_obj.first_name}](tg://user?id={user_obj.id}) is explaining the word!**",
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
    user_obj = message.from_user
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': f"🎉 [{user_obj.first_name}](tg://user?id={user_obj.id}) found the word! **{word}**",
        'parse_mode': 'Markdown',
        'reply_markup': {
            "inline_keyboard": [[{"text": "Start new game!", "callback_data": "start_game"}]]
        }
    }
    r = requests.post(url, json=payload)
    return r

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

def sendChangeLeaderInlineBtn(chat_id, message):
    user_obj = message.from_user
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': f"⚠ [{user_obj.first_name}](tg://user?id={user_obj.id}) wants to take the lead!",
        'parse_mode': 'Markdown',
        'reply_markup': {
            "inline_keyboard": [
                [
                    {"text": "Accept", "callback_data": "change_leader_accept"},
                    {"text": "Refuse", "callback_data": "change_leader_reject"}
                ]
            ]
        }
    }
    r = requests.post(url, json=payload)
    return r


def startGame(message, isStartFromCmd=False):
    # Init game and generate word
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    user_obj = message.from_user
    if isStartFromCmd:
        curr_game = getCurrGame(chatId, user_obj.id)
        if (curr_game['status'] != 'not_started'):
            return
    # Save word to database and start game
    HINTS.clear()
    WORD[0] = funcs.getNewWord()
    if not addGame_sql(chatId, user_obj.id, WORD[0]):
        msg = bot.send_message(chatId, '❌ There was an error on starting the game! Please try again later.\n\nUse /help for more information.')
        removeGame_sql(chatId)
        bot.clear_step_handler_by_chat_id(chatId)
        time.sleep(10)
        bot.delete_message(chatId, msg.message_id)
        return
    sendStartGameInlineBtn(chatId, message)
    bot.register_next_step_handler_by_chat_id(chatId, catchWord)
    return WORD[0]

def stopGame(message, isRefused=False, isChangeLeader=False):
    # Stop game if user is admin or leader
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    userId = message.from_user.id
    if isRefused:
        sendRefuseLeadInlineBtn(chatId, message)
    elif isChangeLeader:
        # If game started more than 30 seconds, allow others to change leader
        pass
    else:
        is_admin = bot.get_chat_member(chatId, userId).status in ['creator', 'administrator']
        curr_game = getCurrGame(chatId, userId)
        if curr_game['status'] == 'not_started':
            msg = bot.send_message(chatId, '⚠ The game is already stopped!')
            time.sleep(10)
            bot.delete_message(chatId, msg.message_id)
            return False
        elif (not is_admin) and curr_game['status'] == 'not_leader':
            msg = bot.send_message(chatId, '⚠ Only an admin or game leader can stop game!')
            time.sleep(10)
            bot.delete_message(chatId, msg.message_id)
            return False
        bot.send_message(chatId, '🛑 The game is stopped!\nTo start a new game, use command:\n/game@CrocodileGameEnn_bot')
    # Delete word from database
    removeGame_sql(chatId)
    bot.clear_step_handler_by_chat_id(chatId)
    return True

def changeWord(message):
    # Generate new word and revoke old one
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    user_obj = message.from_user
    # Save word to database and return (leader changed the word)
    HINTS.clear()
    WORD[0] = funcs.getNewWord()
    addGame_sql(chatId, user_obj.id, WORD[0])
    bot.send_message(chatId, f"❗ [{user_obj.first_name}](tg://user?id={user_obj.id}) has changed the word!", parse_mode='Markdown')
    bot.clear_step_handler_by_chat_id(chatId)
    bot.register_next_step_handler_by_chat_id(chatId, catchWord)
    return WORD[0]

def catchWord(message):
    # Catch all incoming messages and check if it is the word
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    userId = message.from_user.id
    print(message.text.lower(), WORD[0])
    if message.text.lower() == '/game' or message.text.lower() == '/game@crocodilegameenn_bot':
        msg = bot.send_message(chatId, '⚠ Do not blabber! The game is already started.')
        time.sleep(10)
        bot.delete_message(chatId, msg.message_id)
    elif message.text.lower() == '/stop' or message.text.lower() == '/stop@crocodilegameenn_bot':
        if stopGame(message):
            return
    elif message.text.lower() == '/help' or message.text.lower() == '/help@crocodilegameenn_bot':
        help_cmd(message)
    # Check if user guessed the word correctly
    if message.text.lower() != WORD[0]:
        bot.register_next_step_handler_by_chat_id(chatId, catchWord)
        return
    # Check if user is not leader
    curr_game = getCurrGame(chatId, userId)
    if curr_game['status'] == 'not_leader':
        # Someone guessed the word (delete word from database)
        removeGame_sql(chatId)
        sendGuessedWordInlineBtn(chatId, message, WORD[0])
        bot.clear_step_handler_by_chat_id(chatId)
        incrementPoints_sql(userId, chatId)
    elif curr_game['status'] == 'not_started':
        # Game is not started yet
        bot.clear_step_handler_by_chat_id(chatId)
    else:
        # User is a leader
        bot.register_next_step_handler_by_chat_id(chatId, catchWord)
    return

def getCurrGame(chatId, userId):
    # Get current game from database
    curr_game = getGame_sql(chatId)
    if curr_game is None:
        # Game is not started yet
        return dict(status='not_started')
    elif int(curr_game.leader_id) != userId:
        # User is not a leader
        return dict(status='not_leader', started_at=int(curr_game.started_at))
    else:
        # User is a leader
        return dict(status='leader', started_at=int(curr_game.started_at), data=curr_game)


# Bot commands --------------------------------------------------------------- #
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        bot.send_message(chatId, '👋 Hey!\nTo start a new game, use command:\n/game@CrocodileGameEnn_bot')

@bot.message_handler(commands=['game'])
def start_game(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        startGame(message, isStartFromCmd=True)

@bot.message_handler(commands=['stop'])
def stop_game(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        stopGame(message)

@bot.message_handler(commands=['rules'])
def rules_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        rules_msg = "There are two basic roles in this game: the leader (who explains the word) and the other participants (who find the word). The leader will press /game to look for a random word and try to describe it (or give few hints about the word) to other participants without saying that word. The other player\'s role is to find the word the leader explains, and type it in chat. The person who find and types the correct word in the chat first, will be considered winner. If the leader does not like the word, he can press “Change word” for another word. Additionally, if he finds it difficult explaining the word, he can get assistance by pressing “Generate hint” on his leader panel buttons."
        bot.send_message(chatId, f"📖 **Game Rules:**\n\n{rules_msg}", parse_mode='Markdown')

@bot.message_handler(commands=['mystats'])
def mystats_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        user_obj = message.from_user
        user_stats = getUserPoints_sql(user_obj.id, chatId)
        if user_stats is None:
            bot.send_message(chatId, '📊 You have no stats yet!')
        else:
            bot.send_message(chatId, f'📊 **Your total points:** {str(user_stats.points)}', parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        bot.send_message(chatId, '📖 **Help commands:**\n\n'
                                 '🎮 /game - start new game\n'
                                 '🛑 /stop - stop current game\n'
                                 '/rules - see game rules\n'
                                 '/mystats - see your stats\n'
                                 '/ranking - see top 25 players of this group\n'
                                 '/globalranking - see top 10 global level players\n'
                                 '/groupranking - see top 10 groups\n'
                                 '📖 /help - show this message',
                                 parse_mode='Markdown')


# Callbacks handler for inline buttons ---------------------------------------- #
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chatId = call.message.chat.id
    userObj = call.from_user
    if chatId not in BLOCK_CHATS:
        curr_game = getCurrGame(chatId, userObj.id)

        # Inline btn handlers for all general use cases
        if call.data == 'start_game': # User start new game from "XYZ found the word! **WORD**"
            if curr_game['status'] == 'not_started':
                word = startGame(call)
                bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    # only if other users except game-leader consent with it
                    # PENDING_NEXT_LEADER[0] = userObj
                    # sendChangeLeaderInlineBtn(chatId, call)
                    stopGame(call, isChangeLeader=True)
                    word = startGame(call)
                    bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, "⚠ Do not blabber! Game has already started by someone else.", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "⚠ Game has already started by you!", show_alert=True)
        elif call.data == 'start_game_from_refuse': # User start new game from "XYZ refused to lead!"
            if curr_game['status'] == 'not_started':
                word = startGame(call)
                bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                bot.delete_message(chatId, call.message.message_id)
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    # only if other users except game-leader consent with it
                    # PENDING_NEXT_LEADER[0] = userObj
                    # sendChangeLeaderInlineBtn(chatId, call)
                    stopGame(call, isChangeLeader=True)
                    word = startGame(call)
                    bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, "⚠ Do not blabber! Game has already started by someone else.", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "⚠ Game has already started by you!", show_alert=True)
        # elif call.data == 'change_leader_accept':
        #     if curr_game['status'] == 'not_started':
        #         bot.answer_callback_query(call.id, "❌ Game is finished now!", show_alert=True)
        #         bot.delete_message(chatId, call.message.message_id)
        #     elif curr_game['status'] == 'not_leader':
        #         bot.send_message(chatId, f"👍 [{userObj.first_name}](tg://user?id={userObj.id}) accepted {call.message.text.split(' wants to take the lead!')[0].split('⚠ ')[1]}\'s request to lead the game!")
        #     else:
        #         bot.send_message(chatId, f"{userObj.first_name} passed leadership to {call.message.text.split(' wants to take the lead!')[0].split('⚠ ')[1]}")
        # elif call.data == 'change_leader_reject':
        #     if curr_game['status'] == 'not_started':
        #         bot.answer_callback_query(call.id, "❌ Game is finished now!", show_alert=True)
        #         bot.delete_message(chatId, call.message.message_id)
        #     elif curr_game['status'] == 'not_leader':
        #         pass
        #     else:
        #         bot.answer_callback_query(call.id, "⚠ This request is not meant for game leader! You can either press \"Drop lead\"", show_alert=True)
        

        # Game panel inline btn handlers for leader use cases only ---------------- #
        elif call.data == 'see_word':
            if curr_game['status'] == 'not_started':
                bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                bot.answer_callback_query(call.id, "⚠ Only leader can see the word!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, f"Word: {WORD[0]}", show_alert=True)
        elif call.data == 'generate_hints':
            if curr_game['status'] == 'not_started':
                bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                bot.answer_callback_query(call.id, "⚠ Ask to leader for hints!", show_alert=True)
            else:
                global HINTS
                if len(HINTS) == 0:
                    HINTS = funcs.getHints(WORD[0])
                bot.answer_callback_query(call.id, f"{HINTS[0]}\n\n❕ You are free to use your own customised hints!", show_alert=True)
                HINTS.pop(0)
        elif call.data == 'change_word':
            if curr_game['status'] == 'not_started':
                bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                bot.answer_callback_query(call.id, "⚠ Only leader can change the word!", show_alert=True)
            else:
                word = changeWord(call)
                bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
        elif call.data == 'drop_lead':
            if curr_game['status'] == 'not_started':
                bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                bot.answer_callback_query(call.id, "⚠ You are not leading the game!", show_alert=True)
            else:
                stopGame(call, isRefused=True)
                bot.delete_message(chatId, call.message.message_id)


# ------------------------------------------------------------- #
# Enable save next step handlers, so they work for all messages
bot.enable_save_next_step_handlers(delay=2)
# Load next_step_handlers from a file
bot.load_next_step_handlers()
print("[PROD] Bot is running...")
bot.infinity_polling(none_stop=True)
