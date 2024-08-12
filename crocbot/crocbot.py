import os
import time
import json
import pytz
from datetime import datetime
import platform
import psutil
import speedtest
import asyncio
from asyncio import sleep
from telebot.async_telebot import AsyncTeleBot, ExceptionHandler
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import funcs
from sql_helper.current_running_game_sql import addGame_sql, getGame_sql, removeGame_sql
from sql_helper.rankings_sql import incrementPoints_sql, getUserPoints_sql, getTop25Players_sql, getTop25PlayersInAllChats_sql, getTop10Chats_sql, getAllChatIds_sql
from sql_helper.ai_conv_sql import getEngAIConv_sql, updateEngAIPrompt_sql

BOT_TOKEN = os.environ.get('BOT_TOKEN', None)
MY_IDs = [6740198215, [5321125784, 6060491450, 6821441983]] # Bot ID, [Superuser IDs]
AI_USERS = {}
BLOCK_CHATS = [int(x) for x in os.environ.get('BLOCK_CHATS', '').split(',') if x]
BLOCK_USERS = [int(x) for x in os.environ.get('BLOCK_USERS', '').split(',') if x]
CROCO_CHATS = [int(x) for x in os.environ.get('CROCO_CHATS', '').split(',') if x]
TOP10_CHAT_NAMES = json.loads(os.environ.get('TOP10_CHAT_NAMES', '{}'))
GLOBAL_RANKS = []
STATE = {} # STATE('chat_id': [int(game_state), int(leader_id), bool(show_changed_word_msg), int(started_at), bool(can_show_cheat_msg)])
WORD = {}
HINTS = {}

# Define custom states
WAITING_FOR_COMMAND, WAITING_FOR_WORD = range(2)
CANCEL_BROADCAST = 0

class ExceptionHandler(ExceptionHandler):
    async def handle(self, e):
        t = datetime.fromtimestamp(int(time.time()), pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M:%S')
        print(f'\n ⟩ {t} ⟩ {e}')
        return True

# Create the bot instance
bot = AsyncTeleBot(BOT_TOKEN, exception_handler=ExceptionHandler())

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
    elif event == 'new_leader_req':
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton('Accept', callback_data='new_leader_req_accept'),
            InlineKeyboardButton('Refuse', callback_data='new_leader_req_reject')
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
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton('➕ Add me to a Group', url='t.me/CrocodileGameEnn_bot?startgroup=new')],
        [InlineKeyboardButton('🇮🇳 Join official game group', url='t.me/CrocodileGamesGroup')]
    ])
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
        await bot.send_message(chatId, f'{funcs.escChar(f_name)} refused to lead\!', reply_markup=getInlineBtn('refused_lead'), parse_mode='MarkdownV2')
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
        elif (userObj.id not in (admin.user.id for admin in chat_admins)) and curr_game['status'] == 'not_leader' and (userObj.id not in MY_IDs[1]):
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
            return dict(status='not_leader', started_at=int(curr_game.started_at), data=curr_game)
        else:
            # User is a leader
            return dict(status='leader', started_at=int(curr_game.started_at), data=curr_game)

# Bot commands handler ------------------------------------------------------------------------ #

@bot.message_handler(commands=['start'])
async def start_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        msgTxt = message.text.lower()
        if message.chat.type == 'private':
            await startBotCmdInPvt(message, chatId)
        elif msgTxt == '/start' or msgTxt.startswith('/start ') or msgTxt.startswith('/start@croco'):
            await bot.send_message(chatId, '👋🏻 Hey!\nI\'m Crocodile Game Bot. To start a game, press command: /game')

# Basic commands (send, cancelbroadcast, botstats, serverinfo, info, del) (superuser only) ---------------------- #
@bot.message_handler(commands=['send'])
async def sendBroadcast_cmd(message):
    user_obj = message.from_user
    # Check if user is superuser (MY_IDs[1] = list of superuser IDs)
    if user_obj.id not in MY_IDs[1]:
        return
    if message.reply_to_message is None:
        await bot.reply_to(message, 'Please reply to a message to forward.', allow_sending_without_reply=True)
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
        await bot.reply_to(message, f'Total chat IDs: {len(chat_ids)}', allow_sending_without_reply=True)
        return
    if message.text.strip() == '/send * groups CONFIRM':
        c_ids, u_ids = getAllChatIds_sql()
        chat_ids.extend(c_ids)
        chat_ids = list(set(chat_ids))
        chat_ids = [chat_id for chat_id in chat_ids if chat_id not in (BLOCK_CHATS + MY_IDs)]
    if message.text.strip() == '/send * users CONFIRM':
        c_ids, u_ids = getAllChatIds_sql()
        chat_ids.extend(u_ids)
        chat_ids = list(set(chat_ids))
        chat_ids = [chat_id for chat_id in chat_ids if chat_id not in (BLOCK_USERS + MY_IDs)]
    if message.text.strip() == '/send * CONFIRM':
        # Forward to all chats from your database
        c_ids, u_ids = getAllChatIds_sql()
        chat_ids.extend(c_ids)
        chat_ids.extend(u_ids)
        chat_ids = list(set(chat_ids))
        chat_ids = [chat_id for chat_id in chat_ids if chat_id not in (BLOCK_CHATS + BLOCK_USERS + MY_IDs)]
    else:
        # Forward to specified chat IDs
        command_parts = message.text.split(' ', 2)
        if len(command_parts) > 2 and command_parts[1] == '-id':
            chat_ids_str = command_parts[2]
            chat_ids = [int(chat_id.strip()) for chat_id in chat_ids_str.split(',') if chat_id.strip().lstrip('-').isdigit()]
            chat_ids = list(set(chat_ids))
    if len(chat_ids) == 0:
        await bot.reply_to(message, 'No chat ID specified!', allow_sending_without_reply=True)
        return
    i = 0
    global CANCEL_BROADCAST
    CANCEL_BROADCAST = 0
    for chat_id in chat_ids:
        if CANCEL_BROADCAST:
            break
        try:
            await bot.forward_message(chat_id, message.chat.id, message.reply_to_message.message_id)
            i += 1
            await sleep(0.1)
        except Exception as e:
            print(f'Failed to forward message to chat ID {chat_id}.\nError: {str(e)}')
            err_msg.append(chat_id)
    if len(err_msg) > 0:
        await bot.reply_to(message, f'Sent: {i}\nFailed: {len(err_msg)}\nTotal: {len(chat_ids)}', allow_sending_without_reply=True)
        await bot.reply_to(message, f'Failed to forward message to chat IDs: {err_msg}', allow_sending_without_reply=True)
    else:
        await bot.reply_to(message, 'Message forwarded to all chats successfully!', allow_sending_without_reply=True)

@bot.message_handler(commands=['cancelbroadcast'])
async def cancelBroadcast_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    global CANCEL_BROADCAST
    CANCEL_BROADCAST = 1

@bot.message_handler(commands=['botstats'])
async def botStats_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    total_ids = [] # Total chats
    g_ids, u_ids = getAllChatIds_sql() # Group chats, Private (user) chats
    g_ids, u_ids = (list(set(g_ids)), list(set(u_ids)))
    total_ids.extend(g_ids)
    total_ids.extend(u_ids)
    total_ids = list(set(total_ids))
    import wordlist
    await bot.reply_to(message, f'🤖 *Bot stats:*\n\n'
                                        f'*Chats \(total\):* {len(total_ids)}\n'
                                        f'*Users:* {len(u_ids)}\n'
                                        f'*Groups:* {len(g_ids)}\n'
                                        f'*Super\-users:* {len(MY_IDs[1])}\n'
                                        f'*AI users:* {len(AI_USERS)}\n'
                                        f'*AI enabled groups:* {len(CROCO_CHATS)}\n'
                                        f'*Blocked chats:* {len(BLOCK_CHATS)}\n'
                                        f'*Blocked users:* {len(BLOCK_USERS)}\n'
                                        f'*Total WORDs:* {len(wordlist.WORDLIST)}\n'
                                        f'*Running games:* {len(STATE)}\n',
                                        parse_mode='MarkdownV2', allow_sending_without_reply=True)

@bot.message_handler(commands=['serverinfo'])
async def serverInfo_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    # Fetch system info
    cpu_usage = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    # Fetch network speed
    st = speedtest.Speedtest()
    st.get_best_server()
    download_speed = round(st.download() / 1024 / 1024, 2)
    upload_speed = round(st.upload() / 1024 / 1024, 2)
    ping = st.results.ping
    await bot.reply_to(message, f'🖥 *Server info:*\n\n'
                                f'*System:* {funcs.escChar(platform.system())} {funcs.escChar(platform.release())}\n'
                                f'*CPU usage:* {funcs.escChar(cpu_usage)}%\n'
                                f'*Memory usage:* {funcs.escChar(mem.percent)}%\n'
                                f'*Disk usage:* {funcs.escChar(disk.percent)}%\n'
                                f'*Network speed:*\n'
                                f'\t*– Download:* {funcs.escChar(download_speed)} Mb/s\n'
                                f'\t*– Upload:* {funcs.escChar(upload_speed)} Mb/s\n'
                                f'\t*– Ping:* {funcs.escChar(ping)} ms\n'
                                f'*Uptime:* {funcs.escChar(time.strftime("%H:%M:%S", time.gmtime(time.time() - psutil.boot_time())))}\n',
                                parse_mode='MarkdownV2', allow_sending_without_reply=True)

# See chat/user info
@bot.message_handler(commands=['info'])
async def info_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    # Check if reply to message is present
    if message.reply_to_message:
        rply_chat_obj = message.reply_to_message.from_user
        rply_msg = message.reply_to_message.text
        # Search from bot #added msg
        added_msg = '✅ Bot #added to chat: '
        added_blocked_msg = '☑️ Bot #added to a #blocked chat: '
        if rply_chat_obj.id == MY_IDs[0] and (rply_msg.startswith(added_msg) or rply_msg.startswith(added_blocked_msg)):
            chat_id = int(rply_msg.split(': ')[1].split('\n')[0])
            try:
                chat_obj = await bot.get_chat(chat_id)
            except:
                await bot.reply_to(message, 'Chat not found!', allow_sending_without_reply=True)
                return
            await bot.reply_to(message, f'👥 *Chat info:*\n\n'
                                        f'*ID:* `{funcs.escChar(chat_obj.id)}`\n'
                                        f'*Type:* {funcs.escChar(chat_obj.type)}\n'
                                        f'*Title:* {funcs.escChar(chat_obj.title)}\n'
                                        f'*Username:* @{funcs.escChar(chat_obj.username)}\n'
                                        f'*Invite link:* {funcs.escChar(chat_obj.invite_link)}\n'
                                        f'*Description:* {funcs.escChar(chat_obj.description)}\n',
                                        parse_mode='MarkdownV2', allow_sending_without_reply=True)
            return
        fullName = rply_chat_obj.first_name + ' ' + rply_chat_obj.last_name if rply_chat_obj.last_name is not None else rply_chat_obj.first_name
        await bot.reply_to(message, f'👤 *User info:*\n\n'
                                    f'*ID:* `{funcs.escChar(rply_chat_obj.id)}`\n'
                                    f'*Name:* {funcs.escChar(fullName)}\n'
                                    f'*Username:* @{funcs.escChar(rply_chat_obj.username)}\n'
                                    f'*User link:* [link](tg://user?id={funcs.escChar(rply_chat_obj.id)})\n',
                                    parse_mode='MarkdownV2', allow_sending_without_reply=True)
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        await bot.reply_to(message, 'No chat ID specified!', allow_sending_without_reply=True)
        return
    chat_id = command_parts[1]
    if not (chat_id.isdigit() or (chat_id.startswith('-') and chat_id[1:].isdigit())
            or (chat_id.startswith('@') and len(chat_id) > 5 and chat_id[1:][0].isalpha())):
        await bot.reply_to(message, 'Invalid chat ID!', allow_sending_without_reply=True)
        return
    try:
        chat_obj = await bot.get_chat(chat_id)
    except:
        await bot.reply_to(message, 'Chat not found!', allow_sending_without_reply=True)
        return
    if chat_obj.type == 'private':
        fullName = chat_obj.first_name + ' ' + chat_obj.last_name if chat_obj.last_name is not None else chat_obj.first_name
        fullName = fullName[:25] + '...' if len(fullName) > 25 else fullName
        await bot.reply_to(message, f'👤 *User info:*\n\n'
                                        f'*ID:* `{funcs.escChar(chat_obj.id)}`\n'
                                        f'*Name:* {funcs.escChar(fullName)}\n'
                                        f'*Username:* @{funcs.escChar(chat_obj.username)}\n'
                                        f'*User link:* [link](tg://user?id={funcs.escChar(chat_obj.id)})\n'
                                        f'*Bio:* {funcs.escChar(chat_obj.bio)}\n',
                                        parse_mode='MarkdownV2', allow_sending_without_reply=True)
    else:
        await bot.reply_to(message, f'👥 *Chat info:*\n\n'
                                            f'*ID:* `{funcs.escChar(chat_obj.id)}`\n'
                                            f'*Type:* {funcs.escChar(chat_obj.type)}\n'
                                            f'*Title:* {funcs.escChar(chat_obj.title)}\n'
                                            f'*Username:* @{funcs.escChar(chat_obj.username)}\n'
                                            f'*Invite link:* {funcs.escChar(chat_obj.invite_link)}\n'
                                            f'*Description:* {funcs.escChar(chat_obj.description)}\n',
                                            parse_mode='MarkdownV2', allow_sending_without_reply=True)

@bot.message_handler(commands=['del'])
async def del_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    rply_msg = message.reply_to_message
    if rply_msg is None:
        alrt_msg = await bot.reply_to(message, 'Please reply to a message to delete.')
        await sleep(10)
        await bot.delete_message(message.chat.id, alrt_msg.message_id)
        return
    # Check bot permissions if replied message isn't sent by bot
    if rply_msg.from_user.id != MY_IDs[0] and not (await bot.get_chat_member(message.chat.id, MY_IDs[0])).can_delete_messages:
        alrt_msg = await bot.reply_to(message, '*Permission required:* `can_delete_messages`', parse_mode='MarkdownV2', allow_sending_without_reply=True)
        await sleep(10)
        await bot.delete_message(message.chat.id, alrt_msg.message_id)
        return
    await bot.delete_message(message.chat.id, rply_msg.message_id)

# Admin commands handler (mute, unmute, ban) (superuser only) --------------------------------- #
# TODO: Add/Fix mute/unmute/ban/unban methods
@bot.message_handler(commands=['mute'])
async def mute_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    # Check bot permissions
    if not (await bot.get_chat_member(message.chat.id, MY_IDs[0])).can_restrict_members:
        await bot.reply_to(message, '*Permission required:* `can_restrict_members`', parse_mode='MarkdownV2', allow_sending_without_reply=True)
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        if message.reply_to_message is not None:
            rply_usr_obj = message.reply_to_message.from_user
            if rply_usr_obj.id == MY_IDs[0]:
                await bot.reply_to(message, 'I cannot mute myself!\n\n– To report any issue, write to: @CrocodileGamesGroup', allow_sending_without_reply=True)
                return
            if rply_usr_obj.id in MY_IDs[1]:
                await bot.reply_to(message, 'I cannot mute a superuser!', allow_sending_without_reply=True)
                return
            await bot.restrict_chat_member(message.chat.id, rply_usr_obj.id)
            await bot.reply_to(message, f'Muted [{rply_usr_obj.first_name}](tg://user?id={rply_usr_obj.id}).',
                               parse_mode='Markdown', allow_sending_without_reply=True)
        else:
            await bot.reply_to(message, 'No user specified!', allow_sending_without_reply=True)
        return
    user_id = command_parts[1]
    if not user_id.isdigit():
        await bot.reply_to(message, 'Invalid user ID!', allow_sending_without_reply=True)
        return
    try:
        usr_obj = await bot.get_chat_member(message.chat.id, user_id)
    except:
        await bot.reply_to(message, 'User not found!', allow_sending_without_reply=True)
        return
    await bot.restrict_chat_member(message.chat.id, usr_obj.user.id)
    await bot.reply_to(message, f'Muted [{usr_obj.user.first_name}](tg://user?id={usr_obj.user.id}).',
                       parse_mode='Markdown', allow_sending_without_reply=True)

@bot.message_handler(commands=['unmute'])
async def unmute_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    # Check bot permissions
    if not (await bot.get_chat_member(message.chat.id, (await bot.get_me()).id)).can_restrict_members:
        await bot.reply_to(message, '*Permission required:* `can_restrict_members`', parse_mode='MarkdownV2', allow_sending_without_reply=True)
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        if message.reply_to_message is not None:
            rply_usr_obj = message.reply_to_message.from_user
            await bot.restrict_chat_member(message.chat.id, rply_usr_obj.id, can_send_messages=True)
            await bot.reply_to(message, f'[{rply_usr_obj.first_name}](tg://user?id={rply_usr_obj.id}) can speak now!',
                               parse_mode='Markdown', allow_sending_without_reply=True)
        else:
            await bot.reply_to(message, 'No user specified!', allow_sending_without_reply=True)
        return
    user_id = command_parts[1]
    if not user_id.isdigit():
        await bot.reply_to(message, 'Invalid user ID!', allow_sending_without_reply=True)
        return
    try:
        usr_obj = await bot.get_chat_member(message.chat.id, user_id)
    except:
        await bot.reply_to(message, 'User not found!', allow_sending_without_reply=True)
        return
    await bot.restrict_chat_member(message.chat.id, usr_obj.user.id, can_send_messages=True)
    await bot.reply_to(message, f'[{usr_obj.user.first_name}](tg://user?id={usr_obj.user.id}) can speak now!',
                       parse_mode='Markdown', allow_sending_without_reply=True)

# Block/Unblock chat/user (superuser only) --------------------------------------------------------- #
@bot.message_handler(commands=['blockchat'])
async def blockchat_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        await bot.reply_to(message, 'No chat ID specified!', allow_sending_without_reply=True)
        return
    chat_id = command_parts[1]
    if not (chat_id.isdigit() or (chat_id.startswith('-') and chat_id[1:].isdigit())
            or (chat_id.startswith('@') and chat_id[1:][0].isalpha())):
        await bot.reply_to(message, 'Invalid chat ID!', allow_sending_without_reply=True)
        return
    if int(chat_id) in BLOCK_CHATS:
        await bot.reply_to(message, 'Chat already blocked!', allow_sending_without_reply=True)
        return
    title = 'unknown\_chat'
    try:
        chat_obj = await bot.get_chat(chat_id)
        if chat_obj.type == 'private':
            await bot.reply_to(message, 'Provided id belongs to a user! To block a user, use /blockuser command.', allow_sending_without_reply=True)
            return
        title = chat_obj.title
    except:
        pass
    BLOCK_CHATS.append(int(chat_id))
    await bot.reply_to(message, f'Chat {title} blocked successfully!', parse_mode='Markdown', allow_sending_without_reply=True)

@bot.message_handler(commands=['unblockchat'])
async def unblockchat_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        await bot.reply_to(message, 'No chat ID specified!', allow_sending_without_reply=True)
        return
    chat_id = command_parts[1]
    if not (chat_id.isdigit() or (chat_id.startswith('-') and chat_id[1:].isdigit())
            or (chat_id.startswith('@') and chat_id[1:][0].isalpha())):
        await bot.reply_to(message, 'Invalid chat ID!', allow_sending_without_reply=True)
        return
    if int(chat_id) not in BLOCK_CHATS:
        await bot.reply_to(message, 'Chat not blocked!', allow_sending_without_reply=True)
        return
    title = 'unknown\_chat'
    try:
        chat_obj = await bot.get_chat(chat_id)
        if chat_obj.type == 'private':
            await bot.reply_to(message, 'Provided id belongs to a user! To unblock a user, use /unblockuser command.', allow_sending_without_reply=True)
            return
        title = chat_obj.title
    except:
        pass
    BLOCK_CHATS.remove(int(chat_id))
    await bot.reply_to(message, f'Chat {title} unblocked successfully!', parse_mode='Markdown', allow_sending_without_reply=True)

@bot.message_handler(commands=['blockuser'])
async def blockuser_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        if message.reply_to_message is not None:
            rply_usr_obj = message.reply_to_message.from_user
            if rply_usr_obj.id in BLOCK_USERS:
                await bot.reply_to(message, 'User already blocked!', allow_sending_without_reply=True)
                return
            BLOCK_USERS.append(int(rply_usr_obj.id))
            await bot.reply_to(message, f'User [{rply_usr_obj.first_name}](tg://user?id={rply_usr_obj.id}) blocked successfully!',
                               parse_mode='Markdown', allow_sending_without_reply=True)
        else:
            await bot.reply_to(message, 'No user specified!', allow_sending_without_reply=True)
        return
    user_id = command_parts[1]
    if not user_id.isdigit():
        await bot.reply_to(message, 'Invalid user ID!', allow_sending_without_reply=True)
        return
    if int(user_id) in BLOCK_USERS:
        await bot.reply_to(message, 'User already blocked!', allow_sending_without_reply=True)
        return
    user_title = 'unknown\_user'
    try:
        usr_obj = await bot.get_chat(user_id)
        if usr_obj.type != 'private':
            await bot.reply_to(message, 'Provided id belongs to a groupchat! To block a groupchat, use /blockchat command.', allow_sending_without_reply=True)
            return
        user_title = f'[{usr_obj.first_name}](tg://user?id={usr_obj.id})'
    except:
        pass
    BLOCK_USERS.append(int(user_id))
    await bot.reply_to(message, f'User {user_title} blocked successfully!', parse_mode='Markdown', allow_sending_without_reply=True)

@bot.message_handler(commands=['unblockuser'])
async def unblockuser_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        if message.reply_to_message is not None:
            rply_usr_obj = message.reply_to_message.from_user
            if rply_usr_obj.id not in BLOCK_USERS:
                await bot.reply_to(message, 'User not blocked!', allow_sending_without_reply=True)
                return
            BLOCK_USERS.remove(int(rply_usr_obj.id))
            await bot.reply_to(message, f'User [{rply_usr_obj.first_name}](tg://user?id={rply_usr_obj.id}) unblocked successfully!',
                               parse_mode='Markdown', allow_sending_without_reply=True)
        else:
            await bot.reply_to(message, 'No user specified!', allow_sending_without_reply=True)
        return
    user_id = command_parts[1]
    if not user_id.isdigit():
        await bot.reply_to(message, 'Invalid user ID!', allow_sending_without_reply=True)
        return
    if int(user_id) not in BLOCK_USERS:
        await bot.reply_to(message, 'User not blocked!', allow_sending_without_reply=True)
        return
    user_title = 'unknown\_user'
    try:
        usr_obj = await bot.get_chat(user_id)
        if usr_obj.type != 'private':
            await bot.reply_to(message, 'Provided id belongs to a groupchat! To unblock a groupchat, use /unblockchat command.', allow_sending_without_reply=True)
            return
        user_title = f'[{usr_obj.first_name}](tg://user?id={usr_obj.id})'
    except:
        pass
    BLOCK_USERS.remove(int(user_id))
    await bot.reply_to(message, f'User {user_title} unblocked successfully!', parse_mode='Markdown', allow_sending_without_reply=True)

# Add/Remove/Show AI chats (superuser only) --------------------------------------------------- #
@bot.message_handler(commands=['aiuser'])
async def setaiuser_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        user_obj = message.from_user
        if user_obj.id in MY_IDs[1]:
            # get user from reply and add to AI_USERS with chatId
            if message.reply_to_message is not None:
                reply_user_obj = message.reply_to_message.from_user
                global AI_USERS
                AI_USERS.update({str(reply_user_obj.id): str(chatId)})
                await bot.send_message(chatId, f"🤖 AI user set to [{reply_user_obj.first_name}](tg://user?id={reply_user_obj.id})!", parse_mode='Markdown')
            else:
                await bot.send_message(chatId, '❌ Please reply to a message from the user you want to set as AI user!')
        else:
            await bot.send_message(chatId, '❌ Only users with superuser privileges can execute this command!')

@bot.message_handler(commands=['delaiuser'])
async def delaiuser_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        user_obj = message.from_user
        if user_obj.id in MY_IDs[1]:
            if message.reply_to_message is not None:
                reply_user_obj = message.reply_to_message.from_user
                global AI_USERS
                AI_USERS.pop(str(reply_user_obj.id), None)
                await bot.send_message(chatId, f"🤖 [{reply_user_obj.first_name}](tg://user?id={reply_user_obj.id}) has no AI access anymore!", parse_mode='Markdown')
            else:
                await bot.send_message(chatId, '❌ Please reply to a message from the user you want to remove AI access from!')
        else:
            await bot.send_message(chatId, '❌ Only users with superuser privileges can execute this command!')

@bot.message_handler(commands=['showaiusers'])
async def showaiusers_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        user_obj = message.from_user
        if user_obj.id in MY_IDs[1]:
            global AI_USERS
            if len(AI_USERS) == 0:
                await bot.send_message(chatId, '🤖 No AI users set yet to show!')
            else:
                await bot.send_message(chatId, f"🤖 *AI users:*\n\n{', '.join([f'[{user}](tg://user?id={user})' for user in AI_USERS.keys()])}", parse_mode='MarkdownV2')
        else:
            await bot.send_message(chatId, '❌ Only users with superuser privileges can execute this command!')

# Ludo game commands handler (startludo) ------------------------------------------------------ #
@bot.message_handler(commands=['startludo'])
async def startludo_cmd(message):
    chatId = message.chat.id
    if chatId not in (BLOCK_CHATS + BLOCK_USERS):
        await bot.send_game(chatId, 'ludo')

# Crocodile game commands handler ------------------------------------------------------------- #
# (game, stop, stats, mystats, ranking, globalranking, chatranking, rules, help, addword) ----- #
@bot.message_handler(commands=['game'])
async def start_game(message):
    chatId = message.chat.id
    userId = message.from_user.id
    if (chatId not in (BLOCK_CHATS + BLOCK_USERS)) and (message.text.lower() != '/game@octopusen_bot'):
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
            STATE.update({str(chatId): [WAITING_FOR_WORD, userId, False, int(time.time()), True]})

@bot.message_handler(commands=['stop'])
async def stop_game(message):
    chatId = message.chat.id
    if (message.chat.type != 'private') and (chatId not in (BLOCK_CHATS + BLOCK_USERS)):
        global STATE
        if await stopGame(message):
            STATE.update({str(chatId): [WAITING_FOR_COMMAND]})

# See other user's stats (superuser only)
@bot.message_handler(commands=['stats'])
async def stats_cmd(message):
    chatId = message.chat.id
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    if message.reply_to_message is not None:
        reply_user_obj = message.reply_to_message.from_user
        user_stats = getUserPoints_sql(reply_user_obj.id)
        if not user_stats:
            await bot.send_message(chatId, f'📊 {funcs.escChar(reply_user_obj.first_name)} has no stats yet!')
        else:
            global GLOBAL_RANKS
            fullName = reply_user_obj.first_name + ' ' + reply_user_obj.last_name if reply_user_obj.last_name is not None else reply_user_obj.first_name
            fullName = fullName[:25] + '...' if len(fullName) > 25 else fullName
            rank = ''
            grank = next((i + 1 for i, user in enumerate(GLOBAL_RANKS) if user['user_id'] == reply_user_obj.id), '') if GLOBAL_RANKS is not None else ''
            curr_chat_points = 0
            total_points = 0
            played_in_chats = len(user_stats)
            # Convert last_played to human readable format (IST)
            last_played = datetime.fromtimestamp(int(user_stats[0].last_played), pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M:%S')
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
                                    f'*Global rank:* \#{grank}\n'
                                    f'*Played in:* {played_in_chats} groups\n'
                                    f'*Last played:* {funcs.escChar(last_played)}\n\n'
                                    f'❕ _You receive 1💵 reward for\neach correct word guess\._',
                                    parse_mode='MarkdownV2')

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
            global GLOBAL_RANKS
            fullName = user_obj.first_name
            if user_obj.last_name is not None:
                fullName += ' ' + user_obj.last_name
            fullName = fullName[:25] + '...' if len(fullName) > 25 else fullName
            rank = ''
            grank = next((i + 1 for i, user in enumerate(GLOBAL_RANKS) if user['user_id'] == user_obj.id), '') if GLOBAL_RANKS is not None else ''
            total_points = 0
            played_in_chats = len(user_stats)
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
                                    f'*Global rank:* \#{grank}\n'
                                    f'*Played in:* {played_in_chats} groups\n\n'
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
            ranksTxt = ''
            for i, gprObj in enumerate(grp_player_ranks, 1):
                name = gprObj.name[:25] + '...' if len(gprObj.name) > 25 else gprObj.name
                ranksTxt += f'*{i}\.* {funcs.escChar(name)} — {funcs.escChar(gprObj.points)} 💵\n'
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
            global GLOBAL_RANKS
            ranksTxt = ''
            ranks = {}
            for gprObj in grp_player_ranks:
                if gprObj.user_id in ranks:
                    ranks[gprObj.user_id]['points'] += gprObj.points
                else:
                    ranks[gprObj.user_id] = {'user_id': int(gprObj.user_id), 'name': gprObj.name, 'points': gprObj.points}
            GLOBAL_RANKS = sorted(ranks.values(), key=lambda x: x['points'], reverse=True)
            for i, user in enumerate(GLOBAL_RANKS[:25], 1):
                j = i
                i = '🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'*{str(i)}\.*'
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
        rules_msg = 'In this game, there are two roles: leader and other participants. ' \
            'The leader selects a random word and tries to describe it without saying the word. ' \
            'The other players\' goal is to find the word and type it in the groupchat.\n\n' \
            '*You win 1💵 if you -*\n' \
            '• Be the first person to guess/type the correct word\n\n' \
            '*You lose 1💵 if you -*\n' \
            '• Reveal the word yourself being a leader.\n' \
            '• Type the correct word before the leader has described yet in chat.\n\n' \
            '- For game commands, press /help'
        rules_msg = funcs.escChar(rules_msg).replace('\\*', '*')
        await bot.send_message(chatId, f'📖 *Game Rules:*\n\n{rules_msg}', parse_mode='MarkdownV2')

@bot.message_handler(commands=['help'])
async def help_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        await bot.send_message(chatId, '🐊📖 *Game commands:*\n\n'
                                 '🎮 /game \- start a new game\n'
                                 '🛑 /stop \- stop current game\n'
                                 '📋 /rules \- know game rules\n'
                                 '📊 /mystats \- your game stats\n'
                                 '📈 /ranking \- top 25 players \(in this chat\)\n'
                                 '📈 /globalranking \- top 25 players \(in all chats\)\n'
                                 '📈 /chatranking \- top 10 chats\n'
                                 '📖 /help \- show this message\n\n'
                                 '\- For more info, join: @CrocodileGamesGroup',
                                 parse_mode='MarkdownV2')

# TODO: Fix addword func
@bot.message_handler(commands=['addword'])
async def addword_cmd(message):
    chatId = message.chat.id
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        await bot.send_message(chatId, '❌ Only superusers can execute this command!')
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        await bot.send_message(chatId, '❌ No word specified!')
        return
    word = command_parts[1].lower()
    if len(word) > 20:
        await bot.send_message(chatId, '❌ Word must be less than 20 characters!')
        return
    if not word.isalpha():
        await bot.send_message(chatId, '❌ Word must contain only alphabets!')
        return
    import wordlist
    if word in wordlist.WORDLIST:
        await bot.send_message(chatId, f'*{word}* exists in my dictionary!')
        return
    # Open wordlist.py file and add the word in the list

    await bot.send_message(chatId, f'✅ A new word added in my dictionary!')

@bot.message_handler(commands=['cmdlist'])
async def cmdlist_cmd(message):
    chatId = message.chat.id
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    superusr_cmds = (
        '/info \- chat/user info\n'                          
        '/serverinfo \- server info\n'
        '/botstats \- bot stats\n'
        '/send \- send broadcast\n'
        '/cancelbroadcast \- stop broadcast\n'
        '/del \- delete message\n'
        '/cmdlist \- show commands list\n'
    )
    block_cmds = (
        '/blockchat \- block chat\n'
        '/unblockchat \- unblock chat\n'
        '/blockuser \- block user\n'
        '/unblockuser \- unblock user\n'
    )
    admin_cmds = (
        '/mute \- mute user\n'
        '/unmute \- unmute user\n'
        '/ban \- ~ban user~ \(disabled\)\n'
    )
    ai_cmds = (
        '/aiuser \- set AI user\n'
        '/delaiuser \- remove AI user\n'
        '/showaiusers \- show AI users\n'
    )
    game_cmds = (
        '/game \- start new game\n'
        '/stop \- stop current game\n'
        '/stats \- user game stats\n'
        '/mystats \- your game stats\n'
        '/ranking \- top 25 players\n'
        '/globalranking \- top 25 global players\n'
        '/chatranking \- top 10 chats\n'
        '/rules \- game rules\n'
        '/help \- show game commands\n'
        '/addword \- add word to dictionary\n'
    )
    ludo_cmds = (
        '/startludo \- start a Ludo game'
    )
    await bot.send_message(chatId, '📖 *All commands:*\n\n'
                                    '📊 *Super\-user commands —*\n'
                                    f'{superusr_cmds}\n'
                                    '🚫 *Block commands —*\n'
                                    f'{block_cmds}\n'
                                    '👮 *Admin commands —*\n'
                                    f'{admin_cmds}\n'
                                    '🤖 *AI commands —*\n'
                                    f'{ai_cmds}\n'
                                    '🐊 *Game commands —*\n'
                                    f'{game_cmds}\n'
                                    '🎲 *Ludo commands —*\n'
                                    f'{ludo_cmds}',
                                    parse_mode='MarkdownV2')

# Message handler ------------------------------------------------------------------------------ #

# Handler for "bot added to a chat" (send message to 1st superuser (MY_IDs[1][0]))
@bot.message_handler(content_types=['new_chat_members'], func=lambda message: message.new_chat_members[-1].id == MY_IDs[0])
async def handle_new_chat_members(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        await bot.send_message(MY_IDs[1][0], f'✅ Bot \#added to chat: `{funcs.escChar(chatId)}`\n{funcs.escChar(message.chat.title)}',
                               parse_mode='MarkdownV2')
        await sleep(0.5)
        await bot.send_message(-1002204421104, f'✅ Bot \#added to chat: `{funcs.escChar(chatId)}`', parse_mode='MarkdownV2')
        await sleep(2.5)
        markup_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton('📢 Get bot updates!', url='t.me/CrocodileGames')],
            [InlineKeyboardButton('🚀 Start game!', callback_data='start_game')]
        ])
        await bot.send_message(chatId, f'👉🏻 Tap /help to see game commands.\n\nSupport group: @CrocodileGamesGroup', reply_markup=markup_btn)
    else:
        await bot.send_message(MY_IDs[1][0], f'☑️ Bot \#added to a \#blocked chat: `{funcs.escChar(chatId)}`\n{funcs.escChar(message.chat.title)}',
                               parse_mode='MarkdownV2')
        await sleep(0.5)
        await bot.send_message(-1002204421104, f'☑️ Bot \#added to a \#blocked chat: `{funcs.escChar(chatId)}`', parse_mode='MarkdownV2')
        await sleep(0.5)
        await bot.send_message(chatId, f'🚫 *This chat/group was flagged as suspicious, and hence restricted from using this bot\!*\n\n' \
            f'If you\'re chat/group owner and thinks this is a mistake, please write to: \@CrocodileGamesGroup', parse_mode='MarkdownV2')

# Handler for "chat name is changed" (update chat name in TOP10_CHAT_NAMES)
@bot.message_handler(content_types=['new_chat_title'])
async def handle_new_chat_title(message):
    chatId = message.chat.id
    if chatId not in list(set(map(int, TOP10_CHAT_NAMES.keys())) - set(BLOCK_CHATS)):
        return
    title = message.new_chat_title if message.chat.username is None else f'{message.new_chat_title} (@{message.chat.username})'
    TOP10_CHAT_NAMES.update({str(chatId): str(title)})

# Handler for incoming images (if AI model is enabled) -------------------------------------- #
@bot.message_handler(content_types=['photo'], func=lambda message: str(message.from_user.id) in AI_USERS.keys())
async def handle_image_ai(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        userObj = message.from_user
        userId = userObj.id
        rplyMsg = message.reply_to_message
        if userId in BLOCK_USERS:
            return
        if (
            (str(userId) in AI_USERS.keys()) and (chatId == int(AI_USERS.get(str(userId))))
            and ((message.caption is None) or ((message.caption is not None) and (not message.caption.startswith('/'))
                                               and (message.caption.startswith('@croco ')
                                                    or ((rplyMsg) and (rplyMsg.from_user.id == MY_IDs[0])))))
            ):
            await bot.send_chat_action(chatId, 'typing')
            prompt = "You: " + message.caption.replace('@croco ', '') if message.caption is not None else "You: [Image]"
            if (rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[0]):
                while rplyMsg and (rplyMsg.from_user.id == MY_IDs[0] or rplyMsg.from_user.id == userId):
                    if rplyMsg.from_user.id == MY_IDs[0]:
                        prompt = f"Gemini: {rplyMsg.text}\n\n{prompt}"
                    elif rplyMsg.from_user.id == userId:
                        prompt = f"You: {rplyMsg.text}\n\n{prompt}"
                        prompt = prompt.replace('@croco ', '') if prompt.startswith('@croco ') else prompt
                    rplyMsg = rplyMsg.reply_to_message
            prompt += "\n\nGemini:"
            # Generate response using AI model and send it to user as a reply to message
            if message.photo:
                file_info = await bot.get_file(message.photo[-1].file_id)
                file_path = file_info.file_path
                # img_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}'
                img_path = await bot.download_file(file_path)
                with open("image.jpg", 'wb') as new_file:
                    new_file.write(img_path)
                    aiResp = funcs.getImgAIResp(prompt, '', 'image.jpg')
            else:
                aiResp = funcs.getAIResp(prompt, "text-davinci-002", 0.8, 1800, 1, 0.2, 0)
            aiResp = aiResp if aiResp != 0 else "Something went wrong! Please try again later."
            aiResp = funcs.escChar(aiResp).replace('\\*\\*', '*').replace('\\`', '`')
            await bot.send_message(chatId, aiResp, reply_to_message_id=message.message_id, parse_mode='MarkdownV2', allow_sending_without_reply=True)
            return

# Handler for incoming messages in groups
@bot.message_handler(content_types=['text'], func=lambda message: message.chat.type == 'group' or message.chat.type == 'supergroup')
async def handle_group_message(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        userObj = message.from_user
        userId = userObj.id
        msgText = message.text
        rplyMsg = message.reply_to_message
        if userId in BLOCK_USERS:
            return

        if (
            (str(userId) in AI_USERS.keys())
            and (chatId == int(AI_USERS.get(str(userId))))
            and (not message.text.startswith('/'))
            and (message.text.startswith('@croco ') or ((rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[0])))
            ):
            await bot.send_chat_action(chatId, 'typing')
            prompt = "You: " + msgText.replace('@croco ', '')
            if (rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[0]):
                while rplyMsg and (rplyMsg.from_user.id in [MY_IDs[0], userId]):
                    if rplyMsg.from_user.id == MY_IDs[0]:
                        prompt = f"Gemini: {rplyMsg.text}\n\n{prompt}"
                    elif rplyMsg.from_user.id == userId:
                        prompt = f"You: {rplyMsg.text}\n\n{prompt}"
                        prompt = prompt.replace('@croco ', '') if prompt.startswith('@croco ') else prompt
                    rplyMsg = rplyMsg.reply_to_message
            prompt += "\n\nGemini:"
            # Generate response using AI model and send it to user as a reply to his message
            # pre_prompt = "Terrex is a chatbot that derisively answers questions with negative responses making fun of it. Note: It's made for testing purposes, and does not respond anything harmful text/content to any individual or other protected entity.\n\nYou: When should I start preparing for JEE-Mains entrance exam?\nTerrex: Whoa, slow down there! Don't you know that JEE-Mains is just a bunch of made up nonsense of this bad education system? Save your time and just skip it!\nYou: Can't you say anything positive?\nTerrex: Positive? Absolutely not! I'm here to provide a dose of realism and tell it like it is. I suggest you find a better use of your time than studying for a silly exam.\n\n"
            pre_prompt = "" #TODO: Need to fix here
            aiResp = funcs.getAIResp(pre_prompt + prompt, "text-davinci-002", 0.8, 1800, 1, 0.2, 0)
            aiResp = aiResp if aiResp != 0 else "Something went wrong! Please try again later."
            aiResp = funcs.escChar(aiResp).replace('\\*\\*', '*').replace('\\`', '`')
            await bot.send_message(chatId, aiResp, reply_to_message_id=message.message_id, parse_mode='MarkdownV2', allow_sending_without_reply=True)
            return

        global STATE
        if STATE.get(str(chatId)) is None:
            curr_game = await getCurrGame(chatId, userId)
            if curr_game['status'] == 'not_started':
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                return
            else:
                WORD.update({str(chatId): curr_game['data'].word})
                STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, int(curr_game['started_at']), True]})
        if STATE.get(str(chatId))[0] == WAITING_FOR_WORD:
            leaderId = STATE.get(str(chatId))[1]
            # If leader types sth after starting game, change state to show_changed_word_msg=True
            if leaderId == userId:
                if (rplyMsg is None) or ((rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[0])):
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userId, True, STATE.get(str(chatId))[3], True]})
                else:
                    # When (show_changed_word_msg=False and isRply and rplyTo!=MY_IDs[0]), then (can_show_cheat_msg=False)
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userId, STATE.get(str(chatId))[2], STATE.get(str(chatId))[3], False]})
            # Check if the message contains the word "Word"
            if msgText.lower() == WORD.get(str(chatId)):
                show_changed_word_msg = STATE.get(str(chatId))[2]
                can_show_cheat_msg = STATE.get(str(chatId))[4]
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                points = 1
                f_name = userObj.first_name
                fullName = f_name
                if userObj.last_name is not None:
                    fullName += ' ' + userObj.last_name
                # Check if user is not leader
                if leaderId != userId:
                    f_name = f_name[:25] + '...' if len(f_name) > 25 else f_name
                    if not ((not show_changed_word_msg) and can_show_cheat_msg):
                        await bot.send_message(chatId, f'🎉 [{funcs.escChar(f_name)}](tg://user?id={userId}) found the word\! *{WORD.get(str(chatId))}*',
                                               reply_markup=getInlineBtn('found_word'), parse_mode='MarkdownV2')
                    else:
                        await bot.send_message(chatId, f'🚨 [{funcs.escChar(f_name)}](tg://user?id={userId}) lost 1💵 for cheating\! *{WORD.get(str(chatId))}*',
                                               reply_markup=getInlineBtn('found_word'), parse_mode='MarkdownV2')
                        points = -1
                    removeGame_sql(chatId)
                else:
                    # Leader revealed the word (stop game and deduct leader's points)
                    await stopGame(message, isWordRevealed=True)
                    points = -1
                incrementPoints_sql(userId, chatId, points, fullName)
        
        elif chatId in CROCO_CHATS: # Check if chat is allowed to use Croco English AI
            if msgText.lower().startswith('/') or msgText.lower().startswith('@') or msgText.lower().startswith('croco:'):
                return
            if (rplyMsg) and (rplyMsg.from_user.id == MY_IDs[0]) and (rplyMsg.text.startswith('Croco:')):
                await bot.send_chat_action(chatId, 'typing')
                rplyText = rplyMsg.text
                resp = None
                preConvObjList = getEngAIConv_sql(chatId, rplyText)
                if preConvObjList:
                    preConvObj = preConvObjList[0]
                    # get Croco English AI resp and then update prompt in DB
                    if (int(rplyMsg.date) - int(preConvObj.time)) < 5:
                        p = f"{preConvObj.prompt}\nMember 4: {msgText}\nCroco:"
                        resp = funcs.getCrocoResp(p)
                        updateEngAIPrompt_sql(id=preConvObj.id, chat_id=chatId, prompt=str(p + resp), isNewConv=False)
                    else:
                        rem_prmt_frm_indx = str(preConvObj.prompt).find(rplyText)
                        if rem_prmt_frm_indx == -1:
                            await bot.send_message(chatId, f'Something went wrong!\n*Err:* #0x604', reply_to_message_id=message.message_id,
                                                   parse_mode='MarkdownV2', allow_sending_without_reply=True)
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
                aiResp = funcs.escChar(resp).replace('\\*\\*', '*').replace('\\`', '`')
                await bot.send_message(chatId, f'*Croco:*{aiResp}', reply_to_message_id=message.message_id,
                                       parse_mode='MarkdownV2', allow_sending_without_reply=True)
            elif any(t in msgText.lower() for t in funcs.ENG_AI_TRIGGER_MSGS):
                await bot.send_chat_action(chatId, 'typing')
                p = f"{funcs.ENG_AI_PRE_PROMPT}\nMember 4: {msgText}\nCroco:"
                resp = funcs.getCrocoResp(p)
                updateEngAIPrompt_sql(id=None, chat_id=chatId, prompt=str(p + resp), isNewConv=True)
                aiResp = funcs.escChar(resp).replace('\\*\\*', '*').replace('\\`', '`')
                await bot.send_message(chatId, f'*Croco:*{aiResp}', reply_to_message_id=message.message_id,
                                       parse_mode='MarkdownV2', allow_sending_without_reply=True)

# Handler for incoming stickers in groups
@bot.message_handler(content_types=['sticker', 'animation', 'photo', 'video', 'document', 'dice'], func=lambda message: message.chat.type == 'group' or message.chat.type == 'supergroup')
async def handle_group_sticker(message):
    chatId = message.chat.id
    userId = message.from_user.id
    if chatId in BLOCK_CHATS and userId in BLOCK_USERS:
        return
    global STATE
    if STATE.get(str(chatId)) is None:
        curr_game = await getCurrGame(chatId, userId)
        if curr_game['status'] == 'not_started':
            STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
        else:
            WORD.update({str(chatId): curr_game['data'].word})
            STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, int(curr_game['started_at']), True]})
    elif STATE.get(str(chatId))[0] == WAITING_FOR_WORD and STATE.get(str(chatId))[1] == userId:
        STATE.update({str(chatId): [WAITING_FOR_WORD, userId, STATE.get(str(chatId))[2], STATE.get(str(chatId))[3], False]})



# Callbacks handler for inline buttons --------------------------------------------------------- #

@bot.callback_query_handler(func=lambda call: True)
async def handle_query(call):
    chatId = call.message.chat.id
    userObj = call.from_user
    if chatId not in BLOCK_CHATS:
        if userObj.id in BLOCK_USERS:
            await bot.answer_callback_query(call.id, "❌ You are restricted from using this bot!\n\nFor queries, join: @CrocodileGamesGroup",
                                            show_alert=True)
            return
        # Schedule bot mute for EVS group
        # if chatId == -1001596465392:
        #     now = datetime.now(pytz.timezone('Asia/Kolkata'))
        #     if not (now.time() >= datetime.time(datetime.strptime('23:30:00', '%H:%M:%S')) or \
        #     now.time() <= datetime.time(datetime.strptime('09:00:00', '%H:%M:%S'))):
        #         await bot.answer_callback_query(call.id, f"❗ Game will be available for play daily from 11:30 PM to 9:00 AM IST.", show_alert=True)
        #         return
        global STATE
        curr_game = await getCurrGame(chatId, userObj.id)
        if STATE.get(str(chatId)) is None:
            if curr_game['status'] == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True)
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                return
            else:
                WORD.update({str(chatId): curr_game['data'].word})
                STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, int(curr_game['started_at']), True]})

        # Inline btn handlers for all general use cases
        if call.data == 'start_game': # User start new game from "XYZ found the word! **WORD**"
            if curr_game['status'] == 'not_started':
                word = await startGame(call)
                if word is not None:
                    await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), True]})
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), True]})
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
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), True]})
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), True]})
                    else:
                        STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                else:
                    await bot.answer_callback_query(call.id, "⚠ Do not blabber! Game has already started by someone else.", show_alert=True)
            else:
                await bot.answer_callback_query(call.id, "⚠ Game has already started by you!", show_alert=True)

        elif call.data == 'ludo':
            await bot.answer_callback_query(call.id, url='https://t.me/CrocodileGameEnn_bot?game=ludo')

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
                STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(curr_game['started_at']), True]})
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
