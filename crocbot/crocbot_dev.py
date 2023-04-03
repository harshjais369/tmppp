import os
import time
import requests
import asyncio
from asyncio import sleep
from telebot.async_telebot import AsyncTeleBot
import funcs
from sql_helper.current_running_game_sql import addGame_sql, getGame_sql, removeGame_sql
from sql_helper.rankings_sql import incrementPoints_sql, getUserPoints_sql, getTop25PlayersFromGroup_sql

BOT_TOKEN = os.environ.get('BOT_TOKEN', None)
ALLOW_CHATS = [-1001625589718, -1001953164028, -865812485]
STATE = {}
WORD = {}
HINTS = {}

# Define custom states
WAITING_FOR_COMMAND, WAITING_FOR_WORD = range(2)

# Create the bot instance
bot = AsyncTeleBot(BOT_TOKEN)

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


async def startGame(message, isStartFromCmd=False):
    # Init game and generate word
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    user_obj = message.from_user
    if isStartFromCmd:
        curr_game = await getCurrGame(chatId, user_obj.id)
        if (curr_game['status'] != 'not_started'):
            if (int(time.time() - curr_game['started_at']) < 30):
                msg = await bot.send_message(chatId, '⚠ Do not blabber! The game has already started.')
                await sleep(10)
                await bot.delete_message(chatId, msg.message_id)
                return None
    # Save word to database and start game
    WORD.update({str(chatId): funcs.getNewWord()})
    if not addGame_sql(chatId, user_obj.id, WORD.get(str(chatId))):
        msg = await bot.send_message(chatId, '❌ An unexpected error occurred while starting game! Please try again later.\n\nUse /help for more information.')
        removeGame_sql(chatId)
        await sleep(10)
        await bot.delete_message(chatId, msg.message_id)
        return None
    sendStartGameInlineBtn(chatId, message)
    return WORD.get(str(chatId))

async def stopGame(message, isRefused=False, isChangeLeader=False, isWordRevealed=False):
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
    elif isWordRevealed:
        # Leader revealed the word (deduct point)
        pass
    else:
        chatMemb_obj = await bot.get_chat_member(chatId, userId)
        curr_game = await getCurrGame(chatId, userId)
        if curr_game['status'] == 'not_started':
            msg = await bot.send_message(chatId, '⚠ The game is already stopped!')
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return False
        elif (not chatMemb_obj.status in ['creator', 'administrator']) and curr_game['status'] == 'not_leader':
            msg = await bot.send_message(chatId, '⚠ Only an admin or game leader can stop game!')
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return False
        await bot.send_message(chatId, '🛑 The game is stopped!\nTo start a new game, use command:\n/game@CrocodileGameEnn_bot')
    # Delete word from database
    try:
        WORD.pop(str(chatId))
        HINTS.pop(str(chatId))
    except:
        pass
    removeGame_sql(chatId)
    return True

async def changeWord(message):
    # Generate new word and revoke old one
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    user_obj = message.from_user
    # Save word to database and return (leader changed the word)
    try:
        HINTS.get(str(chatId)).pop()
    except:
        pass
    WORD.update({str(chatId): funcs.getNewWord()})
    addGame_sql(chatId, user_obj.id, WORD.get(str(chatId)))
    await bot.send_message(chatId, f"❗ [{user_obj.first_name}](tg://user?id={user_obj.id}) has changed the word!", parse_mode='Markdown')
    return WORD.get(str(chatId))

async def getCurrGame(chatId, userId):
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

# Bot commands handler (start, game, stop, mystats, rules, help) ------------------------------ #
# func=lambda message: message.chat.type == 'private'
@bot.message_handler(commands=['start'])
async def start_cmd(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        await bot.send_message(chatId, '👋 Hey!\nI am alive and working properly.')

@bot.message_handler(commands=['game'])
async def start_game(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        print('Game is starting...!')
        global STATE
        if await startGame(message, isStartFromCmd=True) is not None:
            STATE.update({str(chatId): WAITING_FOR_WORD})

@bot.message_handler(commands=['stop'])
async def stop_game(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        global STATE
        if await stopGame(message):
            STATE.update({str(chatId): WAITING_FOR_COMMAND})

@bot.message_handler(commands=['mystats'])
async def mystats_cmd(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        user_obj = message.from_user
        user_stats = getUserPoints_sql(user_obj.id, chatId)
        if user_stats is None:
            await bot.send_message(chatId, '📊 You have no stats yet!')
        else:
            await bot.send_message(chatId, f'📊 **Your total points:** {str(user_stats.points)}', parse_mode='Markdown')

@bot.message_handler(commands=['rules'])
async def rules_cmd(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        rules_msg = "There are two basic roles in this game: the leader (who explains the word) and the other participants (who find the word). The leader will press /game to look for a random word and try to describe it (or give few hints about the word) to other participants without saying that word. The other player\'s role is to find the word the leader explains, and type it in chat. The person who find and types the correct word in the chat first, will be considered winner. If the leader does not like the word, he can press “Change word” for another word. Additionally, if he finds it difficult explaining the word, he can get assistance by pressing “Generate hint” on his leader panel buttons."
        await bot.send_message(chatId, f"📖 **Game Rules:**\n\n{rules_msg}", parse_mode='Markdown')

@bot.message_handler(commands=['help'])
async def help_cmd(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        await bot.send_message(chatId, '📖 **Help commands:**\n\n'
                                 '🎮 /game - start new game\n'
                                 '🛑 /stop - stop current game\n'
                                 '/rules - see game rules\n'
                                 '/mystats - see your stats\n'
                                 '/ranking - see top 25 players of this group\n'
                                 '/globalranking - see top 10 global level players\n'
                                 '/groupranking - see top 10 groups\n'
                                 '📖 /help - show this message',
                                 parse_mode='Markdown')

# Define the handler for group messages
@bot.message_handler(content_types=['text'], func=lambda message: message.chat.type == 'group' or message.chat.type == 'supergroup')
async def handle_group_message(message):
    chatId = message.chat.id
    if chatId in ALLOW_CHATS:
        userId = message.from_user.id
        global STATE
        print(WORD.get(str(chatId)), message.text.lower())
        print(f'state: {str(STATE)}')
        if STATE.get(str(chatId)) is None:
            STATE.update({str(chatId): WAITING_FOR_COMMAND})
            print(f'Updated state (was None): {str(STATE)}')
        if STATE.get(str(chatId)) == WAITING_FOR_WORD:
            # Check if the message contains the word "Word"
            if message.text.lower() == WORD.get(str(chatId)):
                # Check if user is not leader
                curr_game = await getCurrGame(chatId, userId)
                if curr_game['status'] == 'not_leader':
                    # Someone guessed the word (delete word from database)
                    removeGame_sql(chatId)
                    sendGuessedWordInlineBtn(chatId, message, WORD.get(str(chatId)))
                    incrementPoints_sql(userId, chatId)
                elif curr_game['status'] == 'not_started':
                    pass
                elif curr_game['status'] == 'leader':
                    # Leader revealed the word (stop game and deduct leader's points)
                    await bot.send_message(chatId, f"🛑 Game stopped!\n[{message.from_user.first_name}](tg://user?id={userId}) (-💎) revealed the word! **{WORD.get(str(chatId))}**", parse_mode="Markdown")
                    await stopGame(message, isWordRevealed=True)
                STATE.update({str(chatId): WAITING_FOR_COMMAND})



# Callbacks handler for inline buttons ---------------------------------------- #
@bot.callback_query_handler(func=lambda call: True)
async def handle_query(call):
    chatId = call.message.chat.id
    userObj = call.from_user
    if chatId in ALLOW_CHATS:
        global STATE
        if STATE.get(str(chatId)) is None:
            STATE.update({str(chatId): WAITING_FOR_COMMAND})
        curr_game = await getCurrGame(chatId, userObj.id)

        # Inline btn handlers for all general use cases
        if call.data == 'start_game': # User start new game from "XYZ found the word! **WORD**"
            if curr_game['status'] == 'not_started':
                word = await startGame(call)
                if word is not None:
                    await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                    STATE.update({str(chatId): WAITING_FOR_WORD})
                else:
                    STATE.update({str(chatId): WAITING_FOR_COMMAND})
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): WAITING_FOR_WORD})
                    else:
                        STATE.update({str(chatId): WAITING_FOR_COMMAND})
                else:
                    await bot.answer_callback_query(call.id, "⚠ Do not blabber! Game has already started by someone else.", show_alert=True)
            else:
                await bot.answer_callback_query(call.id, "⚠ Game has already started by you!", show_alert=True)
        elif call.data == 'start_game_from_refuse': # User start new game from "XYZ refused to lead!"
            if curr_game['status'] == 'not_started':
                word = await startGame(call)
                if word is not None:
                    await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                    await bot.delete_message(chatId, call.message.message_id)
                    STATE.update({str(chatId): WAITING_FOR_WORD})
                else:
                    STATE.update({str(chatId): WAITING_FOR_COMMAND})
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): WAITING_FOR_WORD})
                    else:
                        STATE.update({str(chatId): WAITING_FOR_COMMAND})
                else:
                    await bot.answer_callback_query(call.id, "⚠ Do not blabber! Game has already started by someone else.", show_alert=True)
            else:
                await bot.answer_callback_query(call.id, "⚠ Game has already started by you!", show_alert=True)

        # Game panel inline btn handlers for leader use cases only ---------------- #
        elif call.data == 'see_word':
            if curr_game['status'] == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                await bot.answer_callback_query(call.id, "⚠ Only leader can see the word!", show_alert=True)
            else:
                word = WORD.get(str(chatId)) if WORD.get(str(chatId)) is not None else "[Change this word] ❌"
                await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
        elif call.data == 'generate_hints':
            if curr_game['status'] == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                await bot.answer_callback_query(call.id, "⚠ Ask to leader for hints!", show_alert=True)
            else:
                global HINTS
                if WORD.get(str(chatId)) is None:
                    HINTS.update({str(chatId): ['❌ Error: Change this word or restart the game!']})
                elif not (HINTS.get(str(chatId)) is not None and len(HINTS.get(str(chatId))) > 0):
                    HINTS.update({str(chatId): funcs.getHints(WORD.get(str(chatId)))})
                await bot.answer_callback_query(call.id, f"{HINTS.get(str(chatId))[0]}\n\n❕ You are free to use your own customised hints!", show_alert=True)
                HINTS.get(str(chatId)).pop(0)
        elif call.data == 'change_word':
            if curr_game['status'] == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                await bot.answer_callback_query(call.id, "⚠ Only leader can change the word!", show_alert=True)
            else:
                word = await changeWord(call)
                await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                STATE.update({str(chatId): WAITING_FOR_WORD})
                print(STATE.get(str(chatId)))
        elif call.data == 'drop_lead':
            if curr_game['status'] == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                await bot.answer_callback_query(call.id, "⚠ You are not leading the game!", show_alert=True)
            else:
                await stopGame(call, isRefused=True)
                await bot.delete_message(chatId, call.message.message_id)
                STATE.update({str(chatId): WAITING_FOR_COMMAND})

# Start the bot
print("[DEV] Bot is running...")
asyncio.run(bot.infinity_polling())
