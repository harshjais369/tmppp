import os
import time
import json
import pytz
from datetime import datetime
import asyncio
from asyncio import sleep
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import funcs
from sql_helper.current_running_game_sql import addGame_sql, getGame_sql, removeGame_sql
from sql_helper.rankings_sql import incrementPoints_sql, getUserPoints_sql, getTop25Players_sql, getTop25PlayersInAllChats_sql, getTop10Chats_sql, getAllChatIds_sql
from sql_helper.ai_conv_sql import getEngAIConv_sql, updateEngAIPrompt_sql

BOT_TOKEN = os.environ.get('BOT_TOKEN', None)
MY_IDs = [5321125784, 6103212777] # My ID, and Bot ID
AI_USERS = {}
BLOCK_CHATS = [int(x) for x in os.environ.get('BLOCK_CHATS', '').split(',') if x]
CROCO_CHATS = [int(x) for x in os.environ.get('CROCO_CHATS', '').split(',') if x]
TOP10_CHAT_NAMES = json.loads(os.environ.get('TOP10_CHAT_NAMES', '{}'))
STATE = {} # STATE('chat_id': [str(game_state), int(leader_id), bool(show_changed_word_msg), int(started_at)])
WORD = {}
HINTS = {}

# Define custom states
WAITING_FOR_COMMAND, WAITING_FOR_WORD = range(2)

# Create the bot instance
bot = AsyncTeleBot(BOT_TOKEN)

# Get Inline button markup for certain events
def getInlineBtn(event: str):
    markup = InlineKeyboardMarkup()
    if event == 'leading':
        markup.row_width = 2
        markup.add(InlineKeyboardButton('See word', callback_data='see_word'))
        markup.add(*[
            InlineKeyboardButton('Change word', callback_data='change_word'),
            InlineKeyboardButton('Drop lead', callback_data='drop_lead')
        ])
    elif event == 'found_word':
        markup.row_width = 1
        markup.add(InlineKeyboardButton('Start new game!', callback_data='start_game'))
    elif event == 'revealed_word':
        markup.row_width = 1
        markup.add(InlineKeyboardButton('I want to be a leader!', callback_data='start_game'))
    elif event == 'change_leader':
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton('Accept', callback_data='change_leader_accept'),
            InlineKeyboardButton('Refuse', callback_data='change_leader_reject')
        )
    elif event == 'refused_lead':
        markup.row_width = 1
        markup.add(InlineKeyboardButton('I want to be a leader!', callback_data='start_game_from_refuse'))
    else:
        return None
    return markup


async def startBotCmdInPvt(message, chatId):
    # Show greeting message and "Add Bot To Group" button
    userObj = message.from_user
    f_name = '' if len(userObj.first_name) > 30 else userObj.first_name
    greet_msg = f'👋🏻 Hey {funcs.escChar(f_name)}\!\n' \
        f'🐊 *Crocodile Game* is a word guessing game where one player explains the word and others try to guess it\.\n\n' \
        f'👉🏻 Add me into your group and start playing the game now with your friends\!\n\n' \
        f'Press \/help to see the *list of all commands* and how they work\!'
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add me to a Group", url="t.me/CrocodileGameEnn_bot?startgroup=new")]])
    await bot.send_message(chatId, greet_msg, reply_markup=reply_markup, parse_mode='MarkdownV2')

async def startGame(message, isStartFromCmd=False):
    # Init game and generate word
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    userObj = message.from_user
    if isStartFromCmd:
        curr_game = await getCurrGame(chatId, userObj.id)
        if (curr_game['status'] != 'not_started'):
            if (int(time.time() - curr_game['started_at']) < 30):
                msg = await bot.send_message(chatId, '⚠ Do not blabber! The game has already started.')
                await sleep(10)
                await bot.delete_message(chatId, msg.message_id)
                return None
    # Save word to database and start game
    WORD.update({str(chatId): funcs.getNewWord()})
    if not addGame_sql(chatId, userObj.id, WORD.get(str(chatId))):
        msg = await bot.send_message(chatId, '❌ An unexpected error occurred while starting game! Please try again later.\n\nUse /help for more information.')
        removeGame_sql(chatId)
        await sleep(10)
        await bot.delete_message(chatId, msg.message_id)
        return None
    f_name = userObj.first_name[:25] + '...' if len(userObj.first_name) > 25 else userObj.first_name
    await bot.send_message(chatId, f'*[{funcs.escChar(f_name)}](tg://user?id={userObj.id}) is explaining the word\!*', reply_markup=getInlineBtn('leading'), parse_mode='MarkdownV2')
    return WORD.get(str(chatId))

async def stopGame(message, isRefused=False, isChangeLeader=False, isWordRevealed=False):
    # Stop game if user is admin or leader
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    userObj = message.from_user
    f_name = userObj.first_name[:25] + '...' if len(userObj.first_name) > 25 else userObj.first_name
    if isRefused:
        await bot.send_message(chatId, f'{funcs.escChar(f_name)} refused to lead!', reply_markup=getInlineBtn('refused_lead'))
    elif isChangeLeader:
        # If game started more than 30 seconds, allow others to change leader
        pass
    elif isWordRevealed:
        # Leader revealed the word (deduct point)
        await bot.send_message(chatId, f'🛑 *Game stopped\!*\n[{funcs.escChar(f_name)}](tg://user?id={userObj.id}) \(\-1💵\) revealed the word: *{WORD.get(str(chatId))}*', reply_markup=getInlineBtn('revealed_word'), parse_mode='MarkdownV2')
    else:
        chat_admins = await bot.get_chat_administrators(chatId)
        curr_game = await getCurrGame(chatId, userObj.id)
        if curr_game['status'] == 'not_started':
            msg = await bot.send_message(chatId, '⚠ The game is already stopped!')
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return False
        elif (not userObj in (admin.user for admin in chat_admins)) and curr_game['status'] == 'not_leader':
            msg = await bot.send_message(chatId, '⚠ Only an admin or game leader can stop game!')
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return False
        await bot.send_message(chatId, '🛑 The game is stopped!\nTo start a new game, press command:\n/game@CrocodileGameEnn_bot')
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
    global STATE
    # Save word to database and return (leader changed the word)
    try:
        HINTS.get(str(chatId)).pop()
    except:
        pass
    addGame_sql(chatId, user_obj.id, WORD.get(str(chatId)))
    if (STATE.get(str(chatId))[0] == WAITING_FOR_COMMAND) or (STATE.get(str(chatId))[0] == WAITING_FOR_WORD and STATE.get(str(chatId))[2]):
        f_name = user_obj.first_name[:25] + '...' if len(user_obj.first_name) > 25 else user_obj.first_name
        await bot.send_message(chatId, f"❗ {funcs.escChar(f_name)} changed the word\!", parse_mode='MarkdownV2')

async def getCurrGame(chatId, userId):
    if STATE is not None and str(chatId) in STATE and STATE.get(str(chatId))[0] == WAITING_FOR_WORD:
        # Game is started (known from STATE)
        state = 'leader' if (STATE.get(str(chatId))[1] == userId) else 'not_leader'
        return dict(status=state, started_at=STATE.get(str(chatId))[3])
    else:
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
@bot.message_handler(commands=['start'])
async def start_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        msgTxt = message.text.lower()
        if message.chat.type == 'private':
            await startBotCmdInPvt(message, chatId)
        elif msgTxt == '/start' or msgTxt.startswith('/start ') or msgTxt.startswith('/start@croco'):
            await bot.send_message(chatId, '👋🏻 Hey!\nI\'m Crocodile Game Bot. To start a game, press command: /game')

@bot.message_handler(commands=['send'])
async def send_message_to_chats(message):
    user_obj = message.from_user
    # Check if user is me (MY_IDs[0])
    if user_obj.id != MY_IDs[0]:
        return
    if message.reply_to_message is None:
        await bot.reply_to(message, 'Please reply to a message to forward.')
        return
    chat_ids = []
    err_msg = []
    if message.text.strip() == '/send -count':
        # Count all chat_ids from database
        c_ids, u_ids = getAllChatIds_sql()
        # Add both chat IDs and user IDs to chat_ids
        chat_ids.extend(c_ids)
        chat_ids.extend(u_ids)
        # Remove duplicates
        chat_ids = list(set(chat_ids))
        # Remove my IDs and blocked chats
        chat_ids = [chat_id for chat_id in chat_ids if chat_id not in MY_IDs and chat_id not in BLOCK_CHATS]
        await bot.reply_to(message, f'Total chat IDs: {len(chat_ids)}')
        return
    if message.text.strip() == '/send * CONFIRM':
        # Forward to all chats from your database
        c_ids, u_ids = getAllChatIds_sql()
        chat_ids.extend(c_ids)
        chat_ids.extend(u_ids)
        chat_ids = list(set(chat_ids))
        chat_ids = [chat_id for chat_id in chat_ids if chat_id not in MY_IDs and chat_id not in BLOCK_CHATS]
    else:
        # Forward to specified chat IDs
        command_parts = message.text.split(' ', 2)
        if len(command_parts) > 2 and command_parts[1] == '-id':
            chat_ids_str = command_parts[2]
            chat_ids = [int(chat_id.strip()) for chat_id in chat_ids_str.split(',') if chat_id.strip().lstrip('-').isdigit()]
    if len(chat_ids) == 0:
        await bot.reply_to(message, 'No chat ID specified!')
        return
    for chat_id in chat_ids:
        try:
            await bot.forward_message(chat_id, message.chat.id, message.reply_to_message.message_id)
            await sleep(0.1)
        except Exception as e:
            print(f'Failed to forward message to chat ID {chat_id}.\nError: {str(e)}')
            err_msg.append(chat_id)
    if len(err_msg) > 0:
        await bot.reply_to(message, f'Failed to forward message to chat IDs: {err_msg}')
    else:
        await bot.reply_to(message, 'Message forwarded to all chats successfully!')

@bot.message_handler(commands=['aiuser'])
async def setaiuser_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        user_obj = message.from_user
        # Check if user is me (MY_IDs[0])
        if user_obj.id == MY_IDs[0]:
            # get user from reply and add to AI_USERS with chatId
            if message.reply_to_message is not None:
                reply_user_obj = message.reply_to_message.from_user
                global AI_USERS
                AI_USERS.update({str(reply_user_obj.id): str(chatId)})
                await bot.send_message(chatId, f"🤖 AI user set to [{reply_user_obj.first_name}](tg://user?id={reply_user_obj.id})!", parse_mode='Markdown')
            else:
                await bot.send_message(chatId, '❌ Please reply to a message from the user you want to set as AI user!')
        else:
            await bot.send_message(chatId, '❌ Only my creator can use this command!')

@bot.message_handler(commands=['delaiuser'])
async def delaiuser_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        user_obj = message.from_user
        if user_obj.id == MY_IDs[0]:
            if message.reply_to_message is not None:
                reply_user_obj = message.reply_to_message.from_user
                global AI_USERS
                AI_USERS.pop(str(reply_user_obj.id), None)
                await bot.send_message(chatId, f"🤖 [{reply_user_obj.first_name}](tg://user?id={reply_user_obj.id}) has no AI access anymore!", parse_mode='Markdown')
            else:
                await bot.send_message(chatId, '❌ Please reply to a message from the user you want to remove AI access from!')
        else:
            await bot.send_message(chatId, '❌ Only my creator can use this command!')

@bot.message_handler(commands=['showaiusers'])
async def showaiusers_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        user_obj = message.from_user
        if user_obj.id == MY_IDs[0]:
            global AI_USERS
            if len(AI_USERS) == 0:
                await bot.send_message(chatId, '🤖 No AI users set yet to show!')
            else:
                await bot.send_message(chatId, f"🤖 *AI users:*\n\n{', '.join([f'[{user}](tg://user?id={user})' for user in AI_USERS.keys()])}", parse_mode='MarkdownV2')
        else:
            await bot.send_message(chatId, '❌ Only my creator can use this command!')

@bot.message_handler(commands=['game'])
async def start_game(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        userId = message.from_user.id
        # Schedule bot mute for EVS group
        # if chatId == -1001596465392:
        #     now = datetime.now(pytz.timezone('Asia/Kolkata'))
        #     if not (now.time() >= datetime.time(datetime.strptime('23:30:00', '%H:%M:%S')) or \
        #     now.time() <= datetime.time(datetime.strptime('09:00:00', '%H:%M:%S'))):
        #         await bot.send_message(chatId, f"❗ Game will be available for play daily from 11:30 PM to 9:00 AM IST.")
        #         return
        global STATE
        if message.chat.type == 'private':
            await startBotCmdInPvt(message, chatId)
        elif await startGame(message, isStartFromCmd=True) is not None:
            STATE.update({str(chatId): [WAITING_FOR_WORD, userId, False, int(time.time())]})

@bot.message_handler(commands=['stop'])
async def stop_game(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        global STATE
        if await stopGame(message):
            STATE.update({str(chatId): [WAITING_FOR_COMMAND]})

@bot.message_handler(commands=['mystats'])
async def mystats_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        user_obj = message.from_user
        curr_chat_user_stat = None
        curr_chat_points = 0
        total_points = 'Loading...'
        user_stats = getUserPoints_sql(user_obj.id)
        if not user_stats:
            await bot.send_message(chatId, '📊 You have no stats yet!')
        else:
            fullName = user_obj.first_name
            if user_obj.last_name is not None:
                fullName += ' ' + user_obj.last_name
            fullName = fullName[:25] + '...' if len(fullName) > 25 else fullName
            rank = ''
            grank = ''
            total_points = 0
            for us in user_stats:
                if str(us.chat_id) == str(chatId):
                    curr_chat_user_stat = us
                total_points += int(us.points)
            if curr_chat_user_stat is not None:
                curr_chat_points = curr_chat_user_stat.points
            await bot.send_message(chatId, f'*Player stats* 📊\n\n'
                                    f'*Name:* {funcs.escChar(fullName)}\n'
                                    f'*Earned cash:* {funcs.escChar(curr_chat_points)} 💵\n'
                                    f' *— in all chats:* {funcs.escChar(total_points)} 💵\n'
                                    f'*Rank:* \#{rank}\n'
                                    f'*Global rank:* \#{grank}\n\n'
                                    f'❕ _You receive 1💵 reward for\neach correct word guess\._',
                                    parse_mode='MarkdownV2')

@bot.message_handler(commands=['ranking'])
async def ranking_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        grp_player_ranks = getTop25Players_sql(chatId)
        if grp_player_ranks is None or len(grp_player_ranks) < 1:
            await bot.send_message(chatId, '📊 No player\'s rank determined yet for this group!')
        else:
            i = 1
            ranksTxt = ''
            for gprObj in grp_player_ranks:
                name = gprObj.name[:25] + '...' if len(gprObj.name) > 25 else gprObj.name
                ranksTxt += f'*{i}\.* {funcs.escChar(name)} — {funcs.escChar(gprObj.points)} 💵\n'
                i += 1
            await bot.send_message(chatId, f'*TOP\-25 players* 🐊📊\n\n{ranksTxt}', parse_mode='MarkdownV2')

@bot.message_handler(commands=['globalranking'])
async def global_ranking_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        grp_player_ranks = getTop25PlayersInAllChats_sql()
        if grp_player_ranks is None:
            await bot.send_message(chatId, '📊 No player\'s rank determined yet!')
        else:
            # Remove duplicates and re-order the data
            ranksTxt = ''
            ranks = {}
            for gprObj in grp_player_ranks:
                if gprObj.user_id in ranks:
                    ranks[gprObj.user_id]['points'] += gprObj.points
                else:
                    ranks[gprObj.user_id] = {'name': gprObj.name, 'points': gprObj.points}
            ranks = sorted(ranks.values(), key=lambda x: x['points'], reverse=True)[:25]
            for i, user in enumerate(ranks, 1):
                j = i
                if i == 1:
                    i = '🥇'
                elif i == 2:
                    i = '🥈'
                elif i == 3:
                    i = '🥉'
                else:
                    i = f"*{str(i)}\.*"
                name = user['name'][:25] + '...' if len(user['name']) > 25 else user['name']
                ranksTxt += f"{i} {funcs.escChar(name)} — {funcs.escChar(user['points'])} 💵\n"
                i = j
            await bot.send_message(chatId, f'*TOP\-25 players in all groups* 🐊📊\n\n{ranksTxt}', parse_mode='MarkdownV2')

@bot.message_handler(commands=['chatranking'])
async def chat_ranking_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        grp_ranks = getTop10Chats_sql()
        if grp_ranks is None:
            msg = await bot.send_message(chatId, '❗ An unknown error occurred!')
            await asyncio.sleep(5)
            await bot.delete_message(chatId, msg.message_id)
        else:
            ranksTxt = ''
            for i, (chat_id, points) in enumerate(grp_ranks, 1):
                chat_name = TOP10_CHAT_NAMES.get(str(chat_id), "Unknown group")
                ranksTxt += f'*{i}\.* {funcs.escChar(chat_name)} — {funcs.escChar(points)} 💵\n'
            await bot.send_message(chatId, f'*TOP\-10 groups* 🐊📊\n\n{ranksTxt}', parse_mode='MarkdownV2')

@bot.message_handler(commands=['rules'])
async def rules_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        rules_msg = "There are two basic roles in this game: the leader (who explains the word) and the other participants (who find the word). The leader will press /game to look for a random word and try to describe it (or give few hints about the word) to other participants without saying that word. The other player\'s role is to find the word the leader explains, and type it in chat. The person who find and types the correct word in the chat first, will be considered winner. If the leader does not like the word, he can press “Change word” for another word. Additionally, if he finds it difficult explaining the word, he can get assistance by pressing “Generate hint” on his leader panel buttons."
        await bot.send_message(chatId, f"📖 *Game Rules:*\n\n{funcs.escChar(rules_msg)}", parse_mode='MarkdownV2')

@bot.message_handler(commands=['help'])
async def help_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        await bot.send_message(chatId, '🐊📖 *Bot commands:*\n\n'
                                 '🎮 /game \- start new game\n'
                                 '🛑 /stop \- stop current game\n'
                                 '📋 /rules \- see game rules\n'
                                 '📊 /mystats \- see your stats\n'
                                 '📈 /ranking \- see top 25 players in this chat\n'
                                 '📈 /globalranking \- see top 25 players in all chats\n'
                                 '📈 /chatranking \- see top 10 chats\n'
                                 '📖 /help \- show this message',
                                 parse_mode='MarkdownV2')

# Define the handler for group messages
@bot.message_handler(content_types=['text'], func=lambda message: message.chat.type == 'group' or message.chat.type == 'supergroup')
async def handle_group_message(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        userObj = message.from_user
        userId = userObj.id
        msgText = message.text
        rplyMsg = message.reply_to_message

        if ((str(userId) in AI_USERS.keys()) and (chatId == int(AI_USERS.get(str(userId)))) and (message.text.startswith('@croco ') or ((message.reply_to_message is not None) and (message.reply_to_message.from_user.id == MY_IDs[1]))) and (not message.text.startswith('/'))):
            prompt = "You: " + msgText
            await bot.send_chat_action(chatId, 'typing')
            prompt = prompt.replace('@croco ', '')
            if (rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[1]):
                while rplyMsg and (rplyMsg.from_user.id == MY_IDs[1] or rplyMsg.from_user.id == userId):
                    if rplyMsg.from_user.id == MY_IDs[1]:
                        prompt = f"Terrex: {rplyMsg.text}\n\n{prompt}"
                    elif rplyMsg.from_user.id == userId:
                        prompt = f"You: {rplyMsg.text}\n\n{prompt}"
                        prompt = prompt.replace('@croco ', '') if prompt.startswith('@croco ') else prompt
                    rplyMsg = rplyMsg.reply_to_message
            prompt = prompt + "\n\nTerrex:"
            # Generate response using GPT-4 model and send it to user as a reply to his message
            pre_prompt = "Terrex is a chatbot that derisively answers questions with negative responses making fun of it:\n\nYou: When should I start preparing for JEE-Mains entrance exam?\nTerrex: Whoa, slow down there! Don't you know that JEE-Mains is just a bunch of made up nonsense of this bad education system? Save your time and just skip it!\nYou: Can't you say anything positive?\nTerrex: Positive? Absolutely not! I'm here to provide a dose of realism and tell it like it is. I suggest you find a better use of your time than studying for a silly exam.\n\n"
            aiResp = funcs.getAIResp(pre_prompt + prompt, "text-davinci-002", 0.8, 1800, 1, 0.2, 0)
            aiResp = "Something went wrong! Please try again later." if aiResp == 0 else aiResp.choices[0].text
            await bot.send_message(chatId, aiResp, reply_to_message_id=message.message_id)
            return

        global STATE
        if STATE.get(str(chatId)) is None:
            STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
        elif STATE.get(str(chatId))[0] == WAITING_FOR_WORD:
            # If leader types sth after starting game, change state to showChangedWordText=True
            if STATE.get(str(chatId))[1] == userId:
                if (rplyMsg is None) or ((rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[1])):
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userId, True, STATE.get(str(chatId))[3]]})
            # Check if the message contains the word "Word"
            if message.text.lower() == WORD.get(str(chatId)):
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                # Check if user is not leader
                curr_game = await getCurrGame(chatId, userId)
                if curr_game['status'] == 'not_leader':
                    # Someone guessed the word (delete word from database)
                    f_name = userObj.first_name
                    fullName = f_name
                    if userObj.last_name is not None:
                        fullName += ' ' + userObj.last_name
                    f_name = f_name[:25] + '...' if len(f_name) > 25 else f_name
                    await bot.send_message(chatId, f'🎉 [{funcs.escChar(f_name)}](tg://user?id={userId}) found the word\! *{WORD.get(str(chatId))}*', reply_markup=getInlineBtn('found_word'), parse_mode='MarkdownV2')
                    removeGame_sql(chatId)
                    incrementPoints_sql(userId, chatId, 1, fullName)
                elif curr_game['status'] == 'not_started':
                    pass
                elif curr_game['status'] == 'leader':
                    # Leader revealed the word (stop game and deduct leader's points)
                    await stopGame(message, isWordRevealed=True)
                    fullName = userObj.first_name
                    if userObj.last_name is not None:
                        fullName += ' ' + userObj.last_name
                    incrementPoints_sql(userId, chatId, -1, fullName)
        
        elif chatId in CROCO_CHATS: # Check if chat is allowed to use Croco English AI
            if (rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[1]) and (rplyMsg.text.startswith('Croco:')) and not (msgText.startswith('/') or msgText.startswith('@') or msgText.lower().startswith('croco:')):
                await bot.send_chat_action(chatId, 'typing')
                rplyText = rplyMsg.text
                resp = None
                preConvObjList = getEngAIConv_sql(chatId, rplyText)
                if preConvObjList:
                    preConvObj = preConvObjList[0]
                    # get Croco English AI resp and then update prompt in DB
                    if (int(rplyMsg.date) - int(preConvObj.time)) in (0, 1, 2, 3):
                        p = f"{preConvObj.prompt}\nMember 4: {msgText}\nCroco:"
                        resp = funcs.getCrocoResp(p)
                        updateEngAIPrompt_sql(id=preConvObj.id, chat_id=chatId, prompt=str(p + resp), isNewConv=False)
                    else:
                        rem_prmt_frm_indx = str(preConvObj.prompt).find(rplyText)
                        if rem_prmt_frm_indx == -1:
                            await bot.send_message(chatId, f'Something went wrong!\n*Err:* #0x604', reply_to_message_id=message.message_id, parse_mode='MarkdownV2')
                            return
                        end_offset_index = rem_prmt_frm_indx + len(rplyText)
                        if end_offset_index == len(preConvObj.prompt):
                            p = f"{preConvObj.prompt}\nMember 4: {msgText}\nCroco:"
                            resp = funcs.getCrocoResp(p)
                            updateEngAIPrompt_sql(id=preConvObj.id, chat_id=chatId, prompt=str(p + resp), isNewConv=False)
                        else:
                            renew_prompt = preConvObj.prompt[:end_offset_index]
                            p = f"{renew_prompt}\nMember 4: {msgText}\nCroco:"
                            resp = funcs.getCrocoResp(p)
                            updateEngAIPrompt_sql(id=None, chat_id=chatId, prompt=str(p + resp), isNewConv=True)
                else:
                    p = f"{funcs.ENG_AI_PRE_PROMPT}\n- Another conversation -\n...\n{rplyText}\nMember 4: {msgText}\nCroco:"
                    resp = funcs.getCrocoResp(p)
                    updateEngAIPrompt_sql(id=None, chat_id=chatId, prompt=str(p + resp), isNewConv=True)
                await bot.send_message(chatId, f'*Croco:*{funcs.escChar(resp)}', reply_to_message_id=message.message_id, parse_mode='MarkdownV2')
            elif any(t in msgText.lower() for t in funcs.ENG_AI_TRIGGER_MSGS):
                await bot.send_chat_action(chatId, 'typing')
                p = f"{funcs.ENG_AI_PRE_PROMPT}\nMember 4: {msgText}\nCroco:"
                resp = funcs.getCrocoResp(p)
                updateEngAIPrompt_sql(id=None, chat_id=chatId, prompt=str(p + resp), isNewConv=True)
                await bot.send_message(chatId, f'*Croco:*{funcs.escChar(resp)}', reply_to_message_id=message.message_id, parse_mode='MarkdownV2')



# Callbacks handler for inline buttons ---------------------------------------- #
@bot.callback_query_handler(func=lambda call: True)
async def handle_query(call):
    chatId = call.message.chat.id
    userObj = call.from_user
    if chatId not in BLOCK_CHATS:
        # Schedule bot mute for EVS group
        # if chatId == -1001596465392:
        #     now = datetime.now(pytz.timezone('Asia/Kolkata'))
        #     if not (now.time() >= datetime.time(datetime.strptime('23:30:00', '%H:%M:%S')) or \
        #     now.time() <= datetime.time(datetime.strptime('09:00:00', '%H:%M:%S'))):
        #         await bot.answer_callback_query(call.id, f"❗ Game will be available for play daily from 11:30 PM to 9:00 AM IST.", show_alert=True)
        #         return
        global STATE
        if STATE.get(str(chatId)) is None:
            STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
        curr_game = await getCurrGame(chatId, userObj.id)

        # Inline btn handlers for all general use cases
        if call.data == 'start_game': # User start new game from "XYZ found the word! **WORD**"
            if curr_game['status'] == 'not_started':
                word = await startGame(call)
                if word is not None:
                    await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time())]})
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time())]})
                    else:
                        STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
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
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time())]})
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time())]})
                    else:
                        STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
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
                WORD.update({str(chatId): funcs.getNewWord()})
                await bot.answer_callback_query(call.id, f"Word: {WORD.get(str(chatId))}", show_alert=True)
                await changeWord(call)
                STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, STATE.get(str(chatId))[3]]})
        elif call.data == 'drop_lead':
            if curr_game['status'] == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
            elif curr_game['status'] == 'not_leader':
                await bot.answer_callback_query(call.id, "⚠ You are not leading the game!", show_alert=True)
            else:
                await stopGame(call, isRefused=True)
                await bot.delete_message(chatId, call.message.message_id)
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})

# Start the bot
print("[PROD] Bot is running...")
asyncio.run(bot.infinity_polling())
