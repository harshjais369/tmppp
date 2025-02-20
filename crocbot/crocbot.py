import os
import time
import json
import pytz
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import platform
import psutil
import speedtest
import asyncio
from asyncio import sleep
from telebot.async_telebot import AsyncTeleBot, ExceptionHandler
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import funcs
from funcs import escName, escChar
from sql_helper.current_running_game_sql import addGame_sql, getGame_sql, removeGame_sql
from sql_helper.rankings_sql import incrementPoints_sql, getUserPoints_sql, getTop25Players_sql, getTop25PlayersInAllChats_sql, getTop10Chats_sql, getAllChatIds_sql
from sql_helper.daily_botstats_sql import update_dailystats_sql, get_last30days_stats_sql
from sql_helper.ai_conv_sql import getEngAIConv_sql, updateEngAIPrompt_sql

BOT_TOKEN = os.environ.get('BOT_TOKEN', None)
MY_IDs = [6740198215, [5321125784, 6060491450, 6821441983]] # Bot ID, [Superuser IDs]
AI_USERS = {}
BLOCK_CHATS = [int(x) for x in os.environ.get('BLOCK_CHATS', '').split(',') if x]
BLOCK_USERS = [int(x) for x in os.environ.get('BLOCK_USERS', '').split(',') if x]
NO_CHEAT_CHATS = [int(x) for x in os.environ.get('NO_CHEAT_CHATS', '').split(',') if x]
CROCO_CHATS = [int(x) for x in os.environ.get('CROCO_CHATS', '').split(',') if x]
TOP10_CHAT_NAMES = json.loads(os.environ.get('TOP10_CHAT_NAMES', '{}'))
GLOBAL_RANKS = []
STATE = {} # STATE('chat_id': [int(game_state), int(leader_id), bool(show_changed_word_msg), int(started_at), str(can_show_cheat_msg=[True|False|Force True]), bool(is_new_game_req)])
CHEAT_RECORD = {} # CHEAT_RECORD('chat_id': int(cheat_count))
NEW_WORD_REQS = {} # NEW_WORD_REQS = {int(chat_id): {int(user_id): ['word',...],...},...}
WORD = {}
HINTS = {}

# Define custom states
WAITING_FOR_COMMAND, WAITING_FOR_WORD = range(2)
CANCEL_BROADCAST = 0

class ExceptionHandler(ExceptionHandler):
    def handle(self, e):
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
    elif event == 'newLeader_req':
        markup.row_width = 1
        markup.add(InlineKeyboardButton('❌ Cancel', callback_data='newLeader_req_cancel'))
    elif event == 'refused_lead':
        markup.row_width = 1
        markup.add(InlineKeyboardButton('I want to be a leader!', callback_data='start_game_from_refuse'))
    elif event == 'ranking_list_currChat':
        markup.row_width = 1
        markup.add(InlineKeyboardButton('Where am I? 🔍', callback_data='ranking_list_findMe_currChat'))
    elif event == 'ranking_list_allChats':
        markup.row_width = 1
        markup.add(InlineKeyboardButton('Where am I? 🔍', callback_data='ranking_list_findMe_allChats'))
    elif event == 'addWord_req':
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton('✅ Add', callback_data='addWord_req_add'),
            InlineKeyboardButton('❌ Pop', callback_data='addWord_req_pop')
        )
    elif event == 'addWord_req_approve':
        markup.row_width = 1
        markup.add(InlineKeyboardButton('✅ Approve all', callback_data='addWord_req_approve'))
    else:
        return None
    return markup


async def startBotCmdInPvt(message, chatId):
    # Show greeting message and "Add Bot To Group" button
    userObj = message.from_user
    fullname = escName(userObj, 35)
    greet_msg = f'👋🏻 Hey {escChar(fullname)}\!\n' \
        f'🐊 *Crocodile Game* is a word guessing game where one player explains the word and others try to guess it\.\n\n' \
        f'👉🏻 Add me into your group and start playing the game now with your friends\!\n\n' \
        f'Press \/help to see the *list of all commands* and how they work\!'
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton('➕ Add me to a Group', url='t.me/CrocodileGameEnn_bot?startgroup=new')],
        [InlineKeyboardButton('🇮🇳 Join official game group', url='t.me/CrocodileGamesGroup')]
    ])
    await bot.send_message(chatId, greet_msg, reply_markup=reply_markup, parse_mode='MarkdownV2')

async def startGame(message):
    # Init game and generate word
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    userObj = message.from_user
    # Save word to database and start game
    word = funcs.getNewWord()
    WORD.update({str(chatId): word})
    if not addGame_sql(chatId, userObj.id, word):
        msg = await bot.send_message(chatId, '❌ An unexpected error occurred while starting game! Please try again later.\n\nUse /help for more information.')
        removeGame_sql(chatId)
        await sleep(10)
        await bot.delete_message(chatId, msg.message_id)
        return None
    await bot.send_message(chatId, f'*[{escChar(escName(userObj))}](tg://user?id={userObj.id}) is explaining the word\!*',
                           reply_markup=getInlineBtn('leading'), parse_mode='MarkdownV2')
    return word

async def stopGame(message, isRefused=False, isChangeLeader=False, isWordRevealed=False, word=''):
    # Stop game if user is admin or leader
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    userObj = message.from_user
    fullname = escName(userObj)
    if isRefused:
        await bot.send_message(chatId, f'{escChar(fullname)} refused to lead\!{word}', reply_markup=getInlineBtn('refused_lead'), parse_mode='MarkdownV2')
    elif isChangeLeader:
        # If game started more than 30 seconds, allow others to change leader
        pass
    elif isWordRevealed:
        # Leader revealed the word (deduct point)
        await bot.send_message(chatId, f'🛑 *Game stopped\!*\n[{escChar(fullname)}](tg://user?id={userObj.id}) \(\-1💵\) revealed the word: *{WORD.get(str(chatId))}*',
                               reply_markup=getInlineBtn('revealed_word'), parse_mode='MarkdownV2')
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
    WORD.pop(str(chatId), None)
    HINTS.pop(str(chatId), None)
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
    HINTS.pop(str(chatId), None)
    addGame_sql(chatId, user_obj.id, WORD.get(str(chatId)))
    if (STATE.get(str(chatId))[0] == WAITING_FOR_COMMAND) or (STATE.get(str(chatId))[0] == WAITING_FOR_WORD and STATE.get(str(chatId))[2]):
        await bot.send_message(chatId, f"❗ {escChar(escName(user_obj))} changed the word\!", parse_mode='MarkdownV2')

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
    chatId = message.chat.id
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
    stats_msg = f'🤖 *Bot stats \(complete\):*\n\n' \
        f'*Chats \(total\):* {len(total_ids)}\n' \
        f'*Users:* {len(u_ids)}\n' \
        f'*Groups:* {len(g_ids)}\n' \
        f'*Potential reach:* 3\.9M\n' \
        f'*Super\-users:* {len(MY_IDs[1])}\n' \
        f'*AI users:* {len(AI_USERS)}\n' \
        f'*AI groups:* {len(CROCO_CHATS)}\n' \
        f'*Groups with cheaters:* {len(CHEAT_RECORD)}\n' \
        f'*Detected cheats:* {sum(CHEAT_RECORD.values())}\n' \
        f'*Blocked groups:* {len(BLOCK_CHATS)}\n' \
        f'*Blocked users:* {len(BLOCK_USERS)}\n' \
        f'*Total WORDs:* {len(wordlist.WORDLIST)}\n' \
        f'*Active chats \(since reboot\):* {len(STATE)}\n'
    last30days_stats = get_last30days_stats_sql()
    if len(last30days_stats) == 0:
        await bot.reply_to(message, stats_msg, parse_mode='MarkdownV2', allow_sending_without_reply=True)
        return
    # Prepare matplotlib graph
    dates, chats_added, games_played, cheats_detected = [], [], [], []
    for stats in last30days_stats:
        dates.append(stats.date.split('-')[2])
        chats_added.append(stats.chats_added)
        games_played.append(stats.games_played / 100)
        cheats_detected.append(stats.cheats_detected / 100)
    x = np.arange(len(dates))
    fig, ax = plt.subplots()
    # fig.set_size_inches(10, 5)
    # removing axes from the figure
    plt.gca().spines['right'].set_visible(False)
    plt.gca().spines['top'].set_visible(False)
    # Text Watermark
    fig.text(1, 0.1, '@CrocodileGameEnn_bot', fontsize=35, color='gray', ha='right', va='bottom', alpha=0.1, rotation=25)
    plt.xlim(0, len(dates) - 1)
    plt.ylim(0, max(games_played))
    ax.plot(x, chats_added, label='Chats added')
    ax.plot(x, games_played, label='Games played ×100', c='g')
    ax.plot(x, cheats_detected, label='Cheats found ×100', c='m')
    ax.set_xticks(x)
    ax.set_xticklabels(dates, rotation=45)
    # ax.set_xlabel('CrocodileGameEnn_bot.t.me')
    ax.set_title('Crocodile Game Bot (In last 30 days)')
    ax.legend(frameon=False)
    plt.tight_layout()
    plt.savefig('last30days_stats.png')
    plt.close()
    with open('last30days_stats.png', 'rb') as img:
        # Append today's stats to message
        stats_msg = f'📅 *Today stats:*\n\n' \
            f'*New chats:* {chats_added[-1]}\n' \
            f'*Games played:* {int(games_played[-1] * 100)}\n' \
            f'*Cheating rate:* {escChar(100*cheats_detected[-1]/games_played[-1])[:4]}%\n\n' + stats_msg
        await bot.send_photo(chatId, img, caption=stats_msg, parse_mode='MarkdownV2',
                             reply_to_message_id=message.message_id, allow_sending_without_reply=True)

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
                                f'*System:* {escChar(platform.system())} {escChar(platform.release())}\n'
                                f'*CPU usage:* {escChar(cpu_usage)}%\n'
                                f'*Memory usage:* {escChar(mem.percent)}%\n'
                                f'*Disk usage:* {escChar(disk.percent)}%\n'
                                f'*Network speed:*\n'
                                f'\t*– Download:* {escChar(download_speed)} Mb/s\n'
                                f'\t*– Upload:* {escChar(upload_speed)} Mb/s\n'
                                f'\t*– Ping:* {escChar(ping)} ms\n'
                                f'*Uptime:* {escChar(time.strftime("%H:%M:%S", time.gmtime(time.time() - psutil.boot_time())))}\n',
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
                                        f'*ID:* `{escChar(chat_obj.id)}`\n'
                                        f'*Type:* {escChar(chat_obj.type)}\n'
                                        f'*Title:* {escChar(chat_obj.title)}\n'
                                        f'*Username:* @{escChar(chat_obj.username)}\n'
                                        f'*Invite link:* {escChar(chat_obj.invite_link)}\n'
                                        f'*Description:* {escChar(chat_obj.description)}\n',
                                        parse_mode='MarkdownV2', allow_sending_without_reply=True)
            return
        await bot.reply_to(message, f'👤 *User info:*\n\n'
                                    f'*ID:* `{escChar(rply_chat_obj.id)}`\n'
                                    f'*Name:* {escChar(escName(rply_chat_obj, 100, "full"))}\n'
                                    f'*Username:* @{escChar(rply_chat_obj.username)}\n'
                                    f'*User link:* [link](tg://user?id={escChar(rply_chat_obj.id)})\n',
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
        await bot.reply_to(message, f'👤 *User info:*\n\n'
                                        f'*ID:* `{escChar(chat_obj.id)}`\n'
                                        f'*Name:* {escChar(escName(chat_obj, 100, "full"))}\n'
                                        f'*Username:* @{escChar(chat_obj.username)}\n'
                                        f'*User link:* [link](tg://user?id={escChar(chat_obj.id)})\n'
                                        f'*Bio:* {escChar(chat_obj.bio)}\n',
                                        parse_mode='MarkdownV2', allow_sending_without_reply=True)
    else:
        await bot.reply_to(message, f'👥 *Chat info:*\n\n'
                                            f'*ID:* `{escChar(chat_obj.id)}`\n'
                                            f'*Type:* {escChar(chat_obj.type)}\n'
                                            f'*Title:* {escChar(chat_obj.title)}\n'
                                            f'*Username:* @{escChar(chat_obj.username)}\n'
                                            f'*Invite link:* {escChar(chat_obj.invite_link)}\n'
                                            f'*Description:* {escChar(chat_obj.description)}\n',
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

@bot.message_handler(commands=['showcheats'])
async def showCheats_cmd(message):
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    toal_cheats = sum(CHEAT_RECORD.values())
    cheat_msg = ''
    for i, (chat_id, cheat_count) in enumerate(CHEAT_RECORD.items(), 1):
        cheat_msg += f'{i}. {chat_id} — {cheat_count}\n'
    cheat_msg = '🔍 No cheats found yet\!' if cheat_msg == '' else f'🕵🏻‍♂️ *Cheats detected in groups:* `{toal_cheats}`\n\n' + escChar(cheat_msg)
    await bot.reply_to(message, cheat_msg, parse_mode='MarkdownV2', allow_sending_without_reply=True)

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
            await bot.reply_to(message, f'Muted [{escName(rply_usr_obj)}](tg://user?id={rply_usr_obj.id}).',
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
    await bot.reply_to(message, f'Muted [{escName(usr_obj.user)}](tg://user?id={usr_obj.user.id}).',
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
            await bot.reply_to(message, f'[{escName(rply_usr_obj)}](tg://user?id={rply_usr_obj.id}) can speak now!',
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
    await bot.reply_to(message, f'[{escName(usr_obj.user)}](tg://user?id={usr_obj.user.id}) can speak now!',
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
            await bot.reply_to(message, f'User [{escName(rply_usr_obj)}](tg://user?id={rply_usr_obj.id}) blocked successfully!',
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
        user_title = f'[{escName(usr_obj)}](tg://user?id={usr_obj.id})'
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
            await bot.reply_to(message, f'User [{escName(rply_usr_obj)}](tg://user?id={rply_usr_obj.id}) unblocked successfully!',
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
        user_title = f'[{escName(usr_obj)}](tg://user?id={usr_obj.id})'
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
                await bot.send_message(chatId, f"🤖 AI user set to [{escName(reply_user_obj)}](tg://user?id={reply_user_obj.id})!", parse_mode='Markdown')
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
                await bot.send_message(chatId, f"🤖 [{escName(reply_user_obj)}](tg://user?id={reply_user_obj.id}) has no AI access anymore!", parse_mode='Markdown')
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
    userObj = message.from_user
    if (chatId in (BLOCK_CHATS + BLOCK_USERS)) or (message.text.lower() == '/game@octopusen_bot'):
        return
    if message.chat.type == 'private':
        await startBotCmdInPvt(message, chatId)
        return
    # Schedule bot mute for EVS group
    # if chatId == -1001596465392:
    #     now = datetime.now(pytz.timezone('Asia/Kolkata'))
    #     if not (now.time() >= datetime.time(datetime.strptime('23:30:00', '%H:%M:%S')) or \
    #     now.time() <= datetime.time(datetime.strptime('09:00:00', '%H:%M:%S'))):
    #         await bot.send_message(chatId, f"❗ Game will be available for play daily from 11:30 PM to 9:00 AM IST.")
    #         return
    global STATE
    curr_game = await getCurrGame(chatId, userObj.id)
    if (curr_game['status'] != 'not_started'):
        if STATE.get(str(chatId)) is None or STATE.get(str(chatId))[0] == WAITING_FOR_COMMAND:
            WORD.update({str(chatId): curr_game['data'].word})
            STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, int(curr_game['started_at']), 'False', False]})
            await bot.send_message(chatId, f'🔄 *Bot restarted\!*\nNo any running games was impacted during this period\.', parse_mode='MarkdownV2')
        isNewPlyr = getUserPoints_sql(userObj.id) is None
        started_from = int(time.time() - curr_game['started_at'])
        if (started_from < 30 or (isNewPlyr and started_from < 600 and curr_game['status'] != 'leader')):
            msg = await bot.send_message(chatId, '⚠ Do not blabber! The game has already started.')
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return
        if STATE.get(str(chatId))[5]:
            msg = await bot.send_message(chatId, '⚠ Do not blabber! Someone else is going to lead the game next.')
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return
        fullname = escName(userObj)
        rmsg = await bot.send_message(chatId, f'⏳ *{escChar(fullname)}* wants to lead the game\!\nIn `5` seconds\.\.\.',
                                        parse_mode='MarkdownV2', reply_markup=getInlineBtn('newLeader_req'))
        STATE[str(chatId)][5] = True
        for i in range(1, 6):
            await sleep(1)
            if STATE.get(str(chatId))[0] == WAITING_FOR_COMMAND: # If game stopped before 5 secs
                return
            if not STATE.get(str(chatId))[5]: # If cancelled by button press
                print('Change-leader request cancelled! Chat:', chatId)
                return
            try:
                ico = '✅' if i == 5 else '⏳' if i%2 == 0 else '⌛'
                await bot.edit_message_text(f'{ico} *{escChar(fullname)}* wants to lead the game\!\nIn `{5 - i}` seconds\.\.\.',
                    chatId, rmsg.message_id, parse_mode='MarkdownV2', reply_markup=getInlineBtn('newLeader_req'))
            except:
                return
        await sleep(0.3)
        await bot.delete_message(chatId, rmsg.message_id)
        await sleep(0.3)
    if await startGame(message) is not None:
        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), 'True', False]})
        update_dailystats_sql(datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)

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
    if chatId in BLOCK_CHATS and user_obj.id not in MY_IDs[1]:
        return
    if message.reply_to_message is not None:
        reply_user_obj = message.reply_to_message.from_user
        user_stats = getUserPoints_sql(reply_user_obj.id)
        if not user_stats:
            await bot.send_message(chatId, f'📊 {escName(reply_user_obj)} has no stats yet!')
        else:
            global GLOBAL_RANKS
            if not GLOBAL_RANKS:
                granks = {}
                grp_player_ranks = getTop25PlayersInAllChats_sql()
                for gprObj in grp_player_ranks:
                    if gprObj.user_id in granks:
                        granks[gprObj.user_id]['points'] += gprObj.points
                    else:
                        granks[gprObj.user_id] = {'user_id': int(gprObj.user_id), 'name': gprObj.name, 'points': gprObj.points}
                GLOBAL_RANKS = sorted(granks.values(), key=lambda x: x['points'], reverse=True)
            fullName = escName(reply_user_obj, 25, 'full').replace("🏅", "")
            grp_player_ranks = getTop25Players_sql(chatId, 2000)
            rank = next((i for i, prObj in enumerate(grp_player_ranks, 1) if int(prObj.user_id) == reply_user_obj.id), 0) if grp_player_ranks and len(grp_player_ranks) > 0 else 0
            rank = f'*Rank:* \#{rank}\n' if message.chat.type != 'private' else ''
            _grank = next((i for i, user in enumerate(GLOBAL_RANKS, 1) if user['user_id'] == reply_user_obj.id), 0) if GLOBAL_RANKS is not None else 0
            grank = f'Top {str(_grank / len(GLOBAL_RANKS) * 100)[:4]}%' if _grank > 999 else f'#{_grank} 🏆' if _grank < 4 else f'#{_grank}'
            total_points = 0
            played_in_chats = len(user_stats)
            # Convert last_played to human readable format (IST)
            last_played = ''
            if user_obj.id in MY_IDs[1]:
                last_played = datetime.fromtimestamp(int(user_stats[0].last_played), pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M:%S')
                last_played = f'*Last played:* {escChar(last_played)}\n'
            curr_chat_user_stat = None
            for us in user_stats:
                if str(us.chat_id) == str(chatId):
                    curr_chat_user_stat = us
                total_points += int(us.points)
            curr_chat_points = curr_chat_user_stat.points if curr_chat_user_stat else 0
            curr_chat_points = f' {escChar(curr_chat_points)} 💵' if message.chat.type != 'private' else ''
            await bot.send_message(chatId, f'*Player stats* 📊\n\n'
                                    f'*Name:* {"🏅 " if _grank > 0 and _grank < 26 else ""}{escChar(fullName)}\n'
                                    f'*Earned cash:*{curr_chat_points}\n'
                                    f' *— in all chats:* {escChar(total_points)} 💵\n'
                                    f'{rank}'
                                    f'*Global rank:* {escChar(grank)}\n'
                                    f'*Played in:* {played_in_chats} groups\n'
                                    f'{last_played}\n'
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
            if not GLOBAL_RANKS:
                granks = {}
                grp_player_ranks = getTop25PlayersInAllChats_sql()
                for gprObj in grp_player_ranks:
                    if gprObj.user_id in granks:
                        granks[gprObj.user_id]['points'] += gprObj.points
                    else:
                        granks[gprObj.user_id] = {'user_id': int(gprObj.user_id), 'name': gprObj.name, 'points': gprObj.points}
                GLOBAL_RANKS = sorted(granks.values(), key=lambda x: x['points'], reverse=True)
            fullName = escName(user_obj, 25, 'full').replace('🏅', '')
            grp_player_ranks = getTop25Players_sql(chatId, 2000)
            rank = next((i for i, prObj in enumerate(grp_player_ranks, 1) if int(prObj.user_id) == user_obj.id), 0) if grp_player_ranks and len(grp_player_ranks) > 0 else 0
            rank = f'*Rank:* \#{rank}\n' if message.chat.type != 'private' else ''
            _grank = next((i for i, user in enumerate(GLOBAL_RANKS, 1) if user['user_id'] == user_obj.id), 0) if GLOBAL_RANKS is not None else 0
            grank = f'Top {str(_grank / len(GLOBAL_RANKS) * 100)[:4]}%' if _grank > 999 else f'#{_grank} 🏆' if _grank < 4 else f'#{_grank}'
            total_points = 0
            played_in_chats = len(user_stats)
            curr_chat_user_stat = None
            for us in user_stats:
                if str(us.chat_id) == str(chatId):
                    curr_chat_user_stat = us
                total_points += int(us.points)
            curr_chat_points = curr_chat_user_stat.points if curr_chat_user_stat else 0
            curr_chat_points = f' {escChar(curr_chat_points)} 💵' if message.chat.type != 'private' else ''
            await bot.send_message(chatId, f'*Player stats* 📊\n\n'
                                    f'*Name:* {"🏅 " if _grank > 0 and _grank < 26 else ""}{escChar(fullName)}\n'
                                    f'*Earned cash:*{curr_chat_points}\n'
                                    f' *— in all chats:* {escChar(total_points)} 💵\n'
                                    f'{rank}'
                                    f'*Global rank:* {escChar(grank)}\n'
                                    f'*Played in:* {played_in_chats} groups\n\n'
                                    f'❕ _You receive 1💵 reward for\neach correct word guess\._',
                                    parse_mode='MarkdownV2')

@bot.message_handler(commands=['ranking'])
async def ranking_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        if message.chat.type == 'private':
            await bot.send_message(chatId, 'This command can be used in group chats only!\nOr use: /globalranking')
            return
        grp_player_ranks = getTop25Players_sql(chatId)
        if grp_player_ranks is None or len(grp_player_ranks) < 1:
            await bot.send_message(chatId, '📊 No player\'s rank determined yet for this group!')
        else:
            global GLOBAL_RANKS
            reply_markup = None
            if len(grp_player_ranks) > 25 or True:
                reply_markup = getInlineBtn('ranking_list_currChat')
            ranksTxt = ''
            top25_global_usr_ids = [gp['user_id'] for gp in GLOBAL_RANKS[:25]]
            for i, grpObj in enumerate(grp_player_ranks, 1):
                name = ('🏅 ' if int(grpObj.user_id) in top25_global_usr_ids else '') + grpObj.name.replace('🏅', '')
                name = name[:25] + '...' if len(name) > 25 else name
                ranksTxt += f'*{i}\.* {escChar(name)} — {escChar(grpObj.points)} 💵\n'
            await bot.send_message(chatId, f'*TOP\-25 players* 🐊📊\n\n{ranksTxt}', reply_markup=reply_markup, parse_mode='MarkdownV2')

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
            reply_markup = None
            if len(grp_player_ranks) > 25 or True:
                reply_markup = getInlineBtn('ranking_list_allChats')
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
                name = user['name'][:22].rstrip() + '...' if len(user['name']) > 22 else user['name']
                ranksTxt += f"{i} {escChar(name)} — {escChar(user['points'])} 💵\n"
                i = j
            await bot.send_message(chatId, f'*TOP\-25 players in all groups* 🐊📊\n\n{ranksTxt}', reply_markup=reply_markup, parse_mode='MarkdownV2')

@bot.message_handler(commands=['chatranking'])
async def chat_ranking_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        grp_ranks = getTop10Chats_sql()
        if grp_ranks is None:
            msg = await bot.send_message(chatId, '❗ An unknown error occurred!')
            await sleep(5)
            await bot.delete_message(chatId, msg.message_id)
        else:
            ranksTxt = ''
            for i, (chat_id, points) in enumerate(grp_ranks, 1):
                chat_name = TOP10_CHAT_NAMES.get(str(chat_id), 'Unknown group')
                ranksTxt += f'*{i}\.* {escChar(chat_name)} — {escChar(points)} 💵\n'
            await bot.send_message(chatId, f'*TOP\-10 groups* 🐊📊\n\n{ranksTxt}', parse_mode='MarkdownV2')

@bot.message_handler(commands=['rules'])
async def rules_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        rplyToMsgId = message.reply_to_message.message_id if message.reply_to_message else None
        rules_msg = '>In this game, there are two roles: leader and other participants. ' \
            'The leader selects a random word and tries to describe it without saying the word. ' \
            'The other players\' goal is to find the word and type it in the group-chat.\n\n' \
            '*You win 1💵 if you -*\n' \
            '• Be the first person to guess (type) the correct word.\n\n' \
            '*You lose 1💵 if you -*\n' \
            '• Reveal the word yourself being a leader.\n' \
            '• Found correct word before the leader provides any clues/hints in the chat.\n' \
            '• Use whisper bots or any other means to cheat.\n\n' \
            '- For game commands, press /help'
        rules_msg = escChar(rules_msg).replace('\\*', '*').replace('\\>', '>', 1)
        await bot.send_message(chatId, f'📖 *Game Rules:*\n\n{rules_msg}', reply_to_message_id=rplyToMsgId, parse_mode='MarkdownV2', allow_sending_without_reply=True)

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
                                 '📈 /globalranking \- top 25 global players\n'
                                 '📈 /chatranking \- top 10 chats\n'
                                 '➕ /addword \- add word to dictionary\n'
                                 '📖 /help \- show this message\n\n'
                                 '\- For more info, join: @CrocodileGamesGroup',
                                 parse_mode='MarkdownV2')

@bot.message_handler(commands=['addword'])
async def addword_cmd(message):
    chatId = message.chat.id
    user_obj = message.from_user
    if (chatId in (BLOCK_CHATS + BLOCK_USERS) and user_obj.id not in MY_IDs[1]) or user_obj.id in BLOCK_USERS:
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
    if user_obj.id not in MY_IDs[1]:
        import wordlist
        if word in wordlist.WORDLIST:
            msg = await bot.reply_to(message, f'*{word}* exists in my dictionary\!', parse_mode='MarkdownV2', allow_sending_without_reply=True)
            await sleep(30)
            await bot.delete_message(chatId, msg.message_id)
            return
        await bot.reply_to(message, '☑️ Your request is being reviewed. You will be notified soon!', allow_sending_without_reply=True)
        await sleep(1)
        await bot.send_message(MY_IDs[1][0], f'\#req\_addNewWord\n*ChatID:* `{chatId}`\n*UserID:* `{user_obj.id}`\n*Word:* `{word}`',
                               reply_markup=getInlineBtn('addWord_req'), parse_mode='MarkdownV2')
        return
    if not funcs.addNewWord(word):
        msg = await bot.reply_to(message, f'*{word}* exists in my dictionary\!', parse_mode='MarkdownV2', allow_sending_without_reply=True)
        await sleep(30)
        await bot.delete_message(chatId, msg.message_id)
        return
    await bot.send_message(chatId, f'✅ A new word added to my dictionary\!\n\n*Word:* `{word}`', parse_mode='MarkdownV2')

@bot.message_handler(commands=['approve'])
async def approveAddWordReq_cmd(message):
    chatId = message.chat.id
    user_obj = message.from_user
    cnfrm_msg = ''
    if user_obj.id not in MY_IDs[1]:
        return
    if not NEW_WORD_REQS:
        await bot.reply_to(message, '❌ No pending requests!', allow_sending_without_reply=True)
        return
    # Send confirmation message
    for nwr_chat_id, nwr_users in NEW_WORD_REQS.items():
        cnfrm_msg += f'\n{escChar(nwr_chat_id)}: \[\n' + ',\n'.join([f'    [{u}](tg://user?id={u}): \[{nwr_users[u]}\]' for u in nwr_users]) + '\n\]'
    await bot.reply_to(message, f'⏳ *Pending requests:* {len(NEW_WORD_REQS)}\n{cnfrm_msg}', parse_mode='MarkdownV2', reply_markup=getInlineBtn('addWord_req_approve'), allow_sending_without_reply=True)

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
        '/approve \- approve new requests\n'
        '/showcheats \- groups with cheats\n'
        '/cmdlist \- show this message\n'
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
        '/startludo \- ~play Ludo game~ \(disabled\)'
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
        username = f'\n\(\@{escChar(message.chat.username)}\)' if message.chat.username is not None else ''
        await bot.send_message(MY_IDs[1][0], f'✅ Bot \#added to chat: `{escChar(chatId)}`\n{escChar(message.chat.title)}{username}', parse_mode='MarkdownV2')
        await sleep(0.5)
        # await bot.send_message(-1002204421104, f'✅ Bot \#added to chat: `{escChar(chatId)}`', parse_mode='MarkdownV2')
        await sleep(2.5)
        markup_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton('📢 Get bot updates!', url='t.me/CrocodileGames')],
            [InlineKeyboardButton('🚀 Launch game!', callback_data='start_game')]
        ])
        await bot.send_message(chatId, f'👉🏻 Tap /help to see game commands.\n\nSupport group: @CrocodileGamesGroup', reply_markup=markup_btn)
    else:
        await bot.send_message(f'☑️ Bot \#added to a \#blocked chat: `{escChar(chatId)}`\n{escChar(message.chat.title)}\n\@{escChar(message.chat.username)}',
                               chat_id=MY_IDs[1][0], parse_mode='MarkdownV2')
        await sleep(0.5)
        # await bot.send_message(-1002204421104, f'☑️ Bot \#added to a \#blocked chat: `{escChar(chatId)}`', parse_mode='MarkdownV2')
        await sleep(0.5)
        await bot.send_message(chatId, f'🚫 *This chat/group was flagged as suspicious, and hence restricted from using this bot\!*\n\n' \
            f'If you\'re chat/group owner and believes this is a mistake, please write to: \@CrocodileGamesGroup', parse_mode='MarkdownV2')
    update_dailystats_sql(datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 2, 1)

# Handler for "bot removed by chat/user" (send message to 1st superuser (MY_IDs[1][0]))
@bot.my_chat_member_handler(func=lambda message: message.new_chat_member.status in ['kicked', 'left'])
async def handle_my_chat_member(message):
    chatId = message.chat.id
    username = f'\(\@{escChar(message.chat.username)}\)' if message.chat.username is not None else ''
    if message.chat.type != 'private':
        await bot.send_message(MY_IDs[1][0], f'❌ Bot \#removed by chat: `{escChar(chatId)}`\n{escChar(message.chat.title)}\n{username}', parse_mode='MarkdownV2')
    else:
        fullName = escChar(escName(message.chat, 100, 'full'))
        await bot.send_message(MY_IDs[1][0], f'❌ Bot \#removed by [user](tg://user?id={chatId}): `{chatId}`\n{fullName}\n{username}', parse_mode='MarkdownV2')

# Handler for "chat name is changed" (update chat name in TOP10_CHAT_NAMES)
@bot.message_handler(content_types=['new_chat_title'])
async def handle_new_chat_title(message):
    chatId = message.chat.id
    if chatId not in list(set(map(int, TOP10_CHAT_NAMES.keys())) - set(BLOCK_CHATS)):
        return
    title = message.new_chat_title.split()
    for ti in title:
        if any(x in ti for x in ['@', 't.me', 'http://', 'https://']):
            title.pop(title.index(ti))
    title = '[Name Hidden]' if not title else ' '.join(title)
    title = title if message.chat.username is None else f'{title} (@{message.chat.username})'
    await bot.send_message(MY_IDs[1][0], f'📝 #new_chat_title\nID: {chatId}\nNew: {title}\nOld: {TOP10_CHAT_NAMES.get(str(chatId))}')
    TOP10_CHAT_NAMES.update({str(chatId): str(title)})
    await sleep(1)
    await bot.send_message(chatId, f'📝 *Updated chat title in rank list\!*\n\nFor top\-10 chats: /chatranking\nFor any query, ask \@CrocodileGamesGroup', parse_mode='MarkdownV2')

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
            and ((message.caption and message.caption.startswith('@croco ')) or (rplyMsg is None) or (rplyMsg.from_user.id == MY_IDs[0]))
            ):
            await bot.send_chat_action(chatId, 'typing')
            prompt = 'You: [Image]\n' + message.caption.replace('@croco ', '') if message.caption else 'You: [Image]'
            if rplyMsg:
                if rplyMsg.from_user.id == MY_IDs[0]:
                    prompt = f'Croco: {rplyMsg.text}\n\n{prompt}'
                elif rplyMsg.from_user.id != userId:
                    prompt = f'Another member: {rplyMsg.text}\n\n{prompt}'
                else:
                    prompt = f'You: {rplyMsg.text}\n\n{prompt}'
            prompt += '\n\nCroco:'
            # Generate response using AI model and send it to user as a reply to message
            if message.photo:
                file_info = await bot.get_file(message.photo[-1].file_id)
                file_path = file_info.file_path
                # img_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}'
                img_path = await bot.download_file(file_path)
                with open('image.jpg', 'wb') as new_file:
                    new_file.write(img_path)
                    aiResp = funcs.getImgAIResp(prompt, '', 'image.jpg')
            else:
                aiResp = funcs.getAIResp(prompt, 'text-davinci-002', 0.8, 1800, 1, 0.2, 0)
            aiResp = aiResp if aiResp != 0 else 'Something went wrong! Please try again later.'
            aiResp = aiResp.replace('Croco:', '', 1).lstrip() if aiResp.startswith('Croco:') else aiResp
            aiResp = escChar(aiResp).replace('\\*\\*', '*').replace('\\`', '`')
            await bot.send_message(chatId, aiResp, reply_to_message_id=message.message_id, parse_mode='MarkdownV2', allow_sending_without_reply=True)
            return

# Handler for incoming messages in groups
@bot.message_handler(content_types=['text'], func=lambda message: message.chat.type in ['supergroup', 'group'])
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
            and (message.text.startswith('@croco') or ((rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[0])))
            ):
            await bot.send_chat_action(chatId, 'typing')
            p = msgText.replace('@croco', '').lstrip()
            prompt = 'You: ' + p
            rplyToMsg = message
            if rplyMsg:
                if p == '':
                    if rplyMsg.from_user.id == MY_IDs[0]:
                        return
                    else:
                        rplyToMsg = rplyMsg
                        if rplyMsg.photo:
                            prompt = f'You: [Image]\n{rplyMsg.caption}' if rplyMsg.caption else 'You: [Image]'
                        else:
                            prompt += rplyMsg.text
                elif rplyMsg.from_user.id == MY_IDs[0]:
                    if rplyMsg.photo:
                        prompt = f'Croco: [Image]\n{rplyMsg.caption}\n\n{prompt}' if rplyMsg.caption else f'Croco: [Image]\n\n{prompt}'
                    else:
                        prompt = f'Croco: {rplyMsg.text}\n\n{prompt}'
                elif rplyMsg.from_user.id != userId:
                    if rplyMsg.photo:
                        prompt = f'Another member: [Image]\n{rplyMsg.caption}\n\n{prompt}' if rplyMsg.caption else f'Another member: [Image]\n\n{prompt}'
                    else:
                        prompt = f'Another member: {rplyMsg.text}\n\n{prompt}'
                else:
                    if rplyMsg.photo:
                        prompt = f'You: [Image]\n{rplyMsg.caption}\n\n{prompt}' if rplyMsg.caption else f'You: [Image]\n\n{prompt}'
                    else:
                        prompt = f'You: {rplyMsg.text}\n\n{prompt}'
            prompt += '\n\nCroco:'
            # Generate response using AI model and send it to user as a reply to his message
            if rplyMsg and rplyMsg.photo:
                file_info = await bot.get_file(rplyMsg.photo[-1].file_id)
                file_path = file_info.file_path
                img_path = await bot.download_file(file_path)
                with open('image.jpg', 'wb') as new_file:
                    new_file.write(img_path)
                    aiResp = funcs.getImgAIResp(prompt, '', 'image.jpg')
            else:
                aiResp = funcs.getAIResp(prompt, 'text-davinci-002', 0.8, 1800, 1, 0.2, 0)
            aiResp = aiResp if aiResp != 0 else 'Something went wrong! Please try again later.'
            aiResp = aiResp.replace('Croco:', '', 1).lstrip() if aiResp.startswith('Croco:') else aiResp
            aiResp = escChar(aiResp).replace('\\*\\*', '*').replace('\\`', '`')
            await bot.send_message(chatId, aiResp, reply_to_message_id=rplyToMsg.message_id, parse_mode='MarkdownV2', allow_sending_without_reply=True)
            return

        global STATE
        if STATE.get(str(chatId)) is None:
            curr_game = await getCurrGame(chatId, userId)
            if curr_game['status'] == 'not_started':
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                return
            else:
                WORD.update({str(chatId): curr_game['data'].word})
                STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, int(curr_game['started_at']), 'False', False]})
                await bot.send_message(chatId, f'🔄 *Bot restarted\!*\nNo any running games was impacted during this period\.', parse_mode='MarkdownV2')
        if STATE.get(str(chatId))[0] == WAITING_FOR_WORD:
            leaderId = STATE.get(str(chatId))[1]
            # If leader types sth after starting game, change state to show_changed_word_msg=True
            if leaderId == userId:
                cheat_status = 'Force True' if STATE.get(str(chatId))[4] == 'Force True' else 'False'
                if (rplyMsg is None) or ((rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[0])):
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userId, True, STATE.get(str(chatId))[3], cheat_status, STATE.get(str(chatId))[5]]})
                else:
                    # When leader replies to any msg, except bot's msg
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userId, STATE.get(str(chatId))[2], STATE.get(str(chatId))[3], cheat_status, STATE.get(str(chatId))[5]]})
                if message.via_bot and any(t in msgText.lower() for t in ['whisper message to', 'read the whisper', 'private message to', 'generating whisper']):
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userId, STATE.get(str(chatId))[2], STATE.get(str(chatId))[3], 'Force True', STATE.get(str(chatId))[5]]})
                    print('\n>>> Whisper message detected! ChatID:', chatId, '| UserID:', userId, '| Bot:', message.via_bot.username)
                    return
            # Check if the message contains the word "Word"
            if msgText.lower() == WORD.get(str(chatId)):
                global NO_CHEAT_CHATS
                is_cheat_allowed = chatId in NO_CHEAT_CHATS
                can_show_cheat_msg = STATE.get(str(chatId))[4]
                if not is_cheat_allowed:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                elif leaderId != userId:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                points = 1
                fullName = escName(userObj)
                # Check if user is not leader, or if the chat can ignore cheat
                if leaderId != userId or is_cheat_allowed:
                    if is_cheat_allowed and leaderId == userId:
                        return
                    if can_show_cheat_msg == 'False' or is_cheat_allowed:
                        await bot.send_message(chatId, f'🎉 [{escChar(fullName)}](tg://user?id={userId}) found the word\! *{WORD.get(str(chatId))}*',
                                               reply_markup=getInlineBtn('found_word'), parse_mode='MarkdownV2')
                    else:
                        await bot.send_message(chatId, f'🚨 [{escChar(fullName)}](tg://user?id={userId}) lost 1💵 for cheating\! *{WORD.get(str(chatId))}*',
                                               reply_markup=getInlineBtn('found_word'), parse_mode='MarkdownV2')
                        points = -1
                        global CHEAT_RECORD
                        curr_cheat_stats = CHEAT_RECORD.get(str(chatId))
                        if curr_cheat_stats is None:
                            CHEAT_RECORD.update({str(chatId): 1})
                        else:
                            CHEAT_RECORD.update({str(chatId): curr_cheat_stats + 1})                        
                    removeGame_sql(chatId)
                    if points == -1:
                        update_dailystats_sql(datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 1, 1)
                else:
                    # Leader revealed the word (stop game and deduct leader's points)
                    await stopGame(message, isWordRevealed=True)
                    points = -1
                fullName = escName(userObj, 100, 'full')
                incrementPoints_sql(userId, chatId, points, fullName)
        
        elif chatId in CROCO_CHATS: # Check if chat is allowed to use Croco AI
            if msgText.lower().startswith('/') or msgText.lower().startswith('@') or msgText.lower().startswith('croco:'):
                return
            if (rplyMsg) and (rplyMsg.from_user.id == MY_IDs[0]) and (rplyMsg.text.startswith('Croco:')):
                await bot.send_chat_action(chatId, 'typing')
                rplyText = rplyMsg.text
                resp = None
                preConvObjList = getEngAIConv_sql(chatId, rplyText)
                if preConvObjList:
                    preConvObj = preConvObjList[0]
                    # get Croco AI resp and then update prompt in DB
                    if (int(rplyMsg.date) - int(preConvObj.time)) < 5:
                        p = f"{preConvObj.prompt}\nYou: {msgText}\nCroco: "
                        resp = funcs.getCrocoResp(p).lstrip()
                        updateEngAIPrompt_sql(id=preConvObj.id, chat_id=chatId, prompt=str(p + resp), isNewConv=False)
                    else:
                        rem_prmt_frm_indx = str(preConvObj.prompt).find(rplyText)
                        if rem_prmt_frm_indx == -1:
                            await bot.send_message(chatId, f'Something went wrong\!\n*Err:* \#0x604', reply_to_message_id=message.message_id,
                                                   parse_mode='MarkdownV2', allow_sending_without_reply=True)
                            return
                        end_offset_index = rem_prmt_frm_indx + len(rplyText)
                        if end_offset_index == len(preConvObj.prompt):
                            p = f"{preConvObj.prompt}\nYou: {msgText}\nCroco: "
                            resp = funcs.getCrocoResp(p).lstrip()
                            updateEngAIPrompt_sql(id=preConvObj.id, chat_id=chatId, prompt=str(p + resp), isNewConv=False)
                        else:
                            renew_prompt = preConvObj.prompt[:end_offset_index]
                            p = f"{renew_prompt}\nYou: {msgText}\nCroco: "
                            resp = funcs.getCrocoResp(p).lstrip()
                            updateEngAIPrompt_sql(id=None, chat_id=chatId, prompt=str(p + resp), isNewConv=True)
                else:
                    p = f'{rplyText}\nYou: {msgText}\nCroco: '
                    resp = funcs.getCrocoResp(p).lstrip()
                    updateEngAIPrompt_sql(id=None, chat_id=chatId, prompt=str(p + resp), isNewConv=True)
                aiResp = escChar(resp).replace('\\*\\*', '*').replace('\\`', '`')
                await bot.send_message(chatId, f'*Croco:* {aiResp}', reply_to_message_id=message.message_id,
                                       parse_mode='MarkdownV2', allow_sending_without_reply=True)
            elif any(t in msgText.lower() for t in funcs.AI_TRIGGER_MSGS):
                await bot.send_chat_action(chatId, 'typing')
                p = f'You: {msgText}\nCroco: '
                resp = funcs.getCrocoResp(p).lstrip()
                updateEngAIPrompt_sql(id=None, chat_id=chatId, prompt=str(p + resp), isNewConv=True)
                aiResp = escChar(resp).replace('\\*\\*', '*').replace('\\`', '`')
                await bot.send_message(chatId, f'*Croco:* {aiResp}', reply_to_message_id=message.message_id,
                                       parse_mode='MarkdownV2', allow_sending_without_reply=True)

# Handler for incoming media in groups
@bot.message_handler(content_types=['sticker', 'photo', 'video', 'document', 'animation', 'dice', 'poll', 'voice', 'video_note', 'audio', 'contact'],
                     func=lambda message: message.chat.type in ['supergroup', 'group'])
async def handle_group_media(message):
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
            STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, int(curr_game['started_at']), 'False', False]})
            await bot.send_message(chatId, f'🔄 *Bot restarted\!*\nNo any running games was impacted during this period\.', parse_mode='MarkdownV2')
    elif STATE.get(str(chatId))[0] == WAITING_FOR_WORD and STATE.get(str(chatId))[1] == userId:
        cheat_status = 'Force True' if STATE.get(str(chatId))[4] == 'Force True' else 'False'
        STATE.update({str(chatId): [WAITING_FOR_WORD, userId, STATE.get(str(chatId))[2], STATE.get(str(chatId))[3], cheat_status, STATE.get(str(chatId))[5]]})



# Callbacks handler for inline buttons --------------------------------------------------------- #

@bot.callback_query_handler(func=lambda call: True)
async def handle_query(call):
    chatId = call.message.chat.id
    userObj = call.from_user
    if chatId not in BLOCK_CHATS:
        if userObj.id in BLOCK_USERS:
            await bot.answer_callback_query(call.id, "❌ You are restricted from using this bot!\n\nFor queries, join: @CrocodileGamesGroup",
                                            show_alert=True, cache_time=30)
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
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            else:
                WORD.update({str(chatId): curr_game['data'].word})
                STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, int(curr_game['started_at']), 'False', False]})
                await bot.send_message(chatId, f'🔄 *Bot restarted\!*\nNo any running games was impacted during this period\.', parse_mode='MarkdownV2')

        # Inline btn handlers for all general use cases
        if call.data == 'start_game': # User start new game from "XYZ found the word! **WORD**"
            if curr_game['status'] == 'not_started':
                word = await startGame(call)
                if word is not None:
                    await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), 'True', False]})
                    update_dailystats_sql(datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_game['status'] == 'not_leader':
                isNewPlyr = getUserPoints_sql(userObj.id) is None
                started_from = int(time.time() - curr_game['started_at'])
                if (started_from > 30 and not isNewPlyr) or (started_from > 600):
                    if STATE.get(str(chatId))[5]:
                        await bot.answer_callback_query(call.id, '⚠ Do not blabber! Someone else is going to lead the game next.', show_alert=True)
                        return
                    fullname = escName(userObj)
                    rmsg = await bot.send_message(chatId, f'⏳ *{escChar(fullname)}* wants to lead the game\!\nIn `5` seconds\.\.\.',
                        parse_mode='MarkdownV2', reply_markup=getInlineBtn('newLeader_req'))
                    STATE[str(chatId)][5] = True
                    for i in range(1, 6):
                        await sleep(1)
                        if STATE.get(str(chatId))[0] == WAITING_FOR_COMMAND: # If game stopped before 5 secs
                            return
                        if not STATE.get(str(chatId))[5]: # If cancelled by button press
                            print('Change-leader request cancelled! Chat:', chatId)
                            return
                        try:
                            ico = '✅' if i == 5 else '⏳' if i%2 == 0 else '⌛'
                            await bot.edit_message_text(f'{ico} *{escChar(fullname)}* wants to lead the game\!\nIn `{5 - i}` seconds\.\.\.',
                                chatId, rmsg.message_id, parse_mode='MarkdownV2', reply_markup=getInlineBtn('newLeader_req'))
                        except:
                            return
                    await sleep(0.3)
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), 'True', False]})
                        await sleep(0.3)
                        await bot.delete_message(chatId, rmsg.message_id)
                        update_dailystats_sql(datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)
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
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), 'True', False]})
                    update_dailystats_sql(datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_game['status'] == 'not_leader':
                isNewPlyr = getUserPoints_sql(userObj.id) is None
                started_from = int(time.time() - curr_game['started_at'])
                if (started_from > 30 and not isNewPlyr) or (started_from > 600):
                    if STATE.get(str(chatId))[5]:
                        await bot.answer_callback_query(call.id, '⚠ Do not blabber! Someone else is going to lead the game next.', show_alert=True)
                        return
                    fullname = escName(userObj)
                    rmsg = await bot.send_message(chatId, f'⏳ *{escChar(fullname)}* wants to lead the game\!\nIn `5` seconds\.\.\.',
                        parse_mode='MarkdownV2', reply_markup=getInlineBtn('newLeader_req'))
                    STATE[str(chatId)][5] = True
                    for i in range(1, 6):
                        await sleep(1)
                        if STATE.get(str(chatId))[0] == WAITING_FOR_COMMAND: # If game stopped before 5 secs
                            return
                        if not STATE.get(str(chatId))[5]: # If cancelled by button press
                            print('Change-leader request cancelled! Chat:', chatId)
                            return
                        try:
                            ico = '✅' if i == 5 else '⏳' if i%2 == 0 else '⌛'
                            await bot.edit_message_text(f'{ico} *{escChar(fullname)}* wants to lead the game\!\nIn `{5 - i}` seconds\.\.\.',
                                chatId, rmsg.message_id, parse_mode='MarkdownV2', reply_markup=getInlineBtn('newLeader_req'))
                        except:
                            return
                    await sleep(0.3)
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), 'True', False]})
                        await sleep(0.3)
                        await bot.delete_message(chatId, rmsg.message_id)
                        update_dailystats_sql(datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)
                    else:
                        STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                else:
                    await bot.answer_callback_query(call.id, "⚠ Do not blabber! Game has already started by someone else.", show_alert=True)
            else:
                await bot.answer_callback_query(call.id, "⚠ Game has already started by you!", show_alert=True)

        elif call.data == 'ludo':
            await bot.answer_callback_query(call.id, url='https://t.me/CrocodileGameEnn_bot?game=ludo')
        elif call.data == 'ranking_list_findMe_currChat':
            user_stats = getTop25Players_sql(chatId, 2000)
            if not user_stats:
                await bot.answer_callback_query(call.id, '❌ Something went wrong!\n\n- If the issue still persists, kindly report it to: @CrocodileGamesGroup', show_alert=True)
                return
            user_stats = next(([str(i), us] for i, us in enumerate(user_stats, 1) if int(us.user_id) == userObj.id), None)
            if not user_stats:
                await bot.answer_callback_query(call.id, '❕Seems like you are new in this chat!\nStart guessing words and earn points to get ranked.', show_alert=True, cache_time=15)
                return
            if int(user_stats[0]) < 26: user_stats[0] += ' 🏆'
            last_played = datetime.fromtimestamp(int(user_stats[1].last_played), pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M:%S')
            await bot.answer_callback_query(call.id, show_alert=True, cache_time=15,
                text=f'Rank: #{user_stats[0]}\nName: {user_stats[1].name[:25]}\nEarned: {user_stats[1].points} 💵\nLast played: {last_played}')
            return
        elif call.data == 'ranking_list_findMe_allChats':
            global GLOBAL_RANKS
            if not GLOBAL_RANKS:
                granks = {}
                grp_player_ranks = getTop25PlayersInAllChats_sql()
                for gprObj in grp_player_ranks:
                    if gprObj.user_id in granks:
                        granks[gprObj.user_id]['points'] += gprObj.points
                    else:
                        granks[gprObj.user_id] = {'user_id': int(gprObj.user_id), 'name': gprObj.name, 'points': gprObj.points}
                GLOBAL_RANKS = sorted(granks.values(), key=lambda x: x['points'], reverse=True)
            _grank = next(([i, user] for i, user in enumerate(GLOBAL_RANKS, 1) if user['user_id'] == userObj.id), 0) if GLOBAL_RANKS is not None else 0
            if _grank == 0:
                await bot.answer_callback_query(call.id, '❕Seems like you are new to this game!\nStart guessing words and earn points to get ranked.', show_alert=True, cache_time=15)
                return
            grank = f'Top {str(_grank[0] / len(GLOBAL_RANKS) * 100)[:4]}%' if _grank[0] > 999 else f'#{_grank[0]} 🏆' if _grank[0] < 26 else f'#{_grank[0]}'
            await bot.answer_callback_query(call.id, show_alert=True, cache_time=15,
                text=f'Rank: {grank}\nName: {_grank[1]["name"][:25]}\nEarned: {_grank[1]["points"]} 💵\n\n- Have queries? Ask @CrocodileGamesGroup')
        elif call.data.startswith('addWord_req_'):
            txt = call.message.text
            if userObj.id not in MY_IDs[1]:
                await bot.answer_callback_query(call.id, '❌ You are not authorised to perform this action!', show_alert=True, cache_time=30)
                return
            global NEW_WORD_REQS
            if call.data == 'addWord_req_approve':
                if not NEW_WORD_REQS:
                    await bot.answer_callback_query(call.id, '❌ No pending requests!')
                    return
                cnt = 0
                for chat_id, users in NEW_WORD_REQS.items():
                    for user_id, words in users.items():
                        added_words = []
                        for wd in words:
                            if funcs.addNewWord(wd):
                                added_words.append(wd)
                        if added_words:
                            target_chatId = chat_id
                            try:
                                target_chat = await bot.get_chat(target_chatId)
                            except:
                                target_chatId = user_id
                            await sleep(1)
                            try:
                                target_user = await bot.get_chat(user_id)
                            except:
                                target_user = None
                            try:
                                fullname = '[Ghost User]'
                                if target_user:
                                    fullname = escName(target_user)
                                added_wds_txt = ', '.join(added_words)
                                await bot.send_message(target_chatId, parse_mode='MarkdownV2',
                                    text=f'[✅](tg://user?id={escChar(user_id)}) *{len(added_words)}* new word\(s\) added by *{escChar(fullname)}*\n\n```\n{added_wds_txt}```')
                                cnt += 1
                            except:
                                pass
                            await sleep(1)
                NEW_WORD_REQS.clear()
                await bot.send_message(MY_IDs[1][0], f'✅ All words added to dictionary\!\n\n🔔 *Notice sent \(times\):* `{cnt}`', parse_mode='MarkdownV2', allow_sending_without_reply=True)
                return
            if not txt.startswith('#req_addNewWord'):
                await bot.answer_callback_query(call.id, '❌ Invalid request!')
                return
            cid = int(txt[txt.find('ChatID: ') + 8:txt.find('\nUserID:')])
            uid = int(txt[txt.find('UserID: ') + 8:txt.find('\nWord:')])
            wd = txt[txt.find('Word: ') + 6:].lower()
            if call.data == 'addWord_req_add':
                import wordlist
                if wd in wordlist.WORDLIST:
                    await bot.answer_callback_query(call.id, f"{wd} exists!")
                    return
                for nwr_chat in NEW_WORD_REQS.values():
                    for nwr_user, nwr_words in nwr_chat.items():
                        if wd in nwr_words:
                            await bot.answer_callback_query(call.id, f"{wd} is already in queue!")
                            return
                if cid not in NEW_WORD_REQS:
                    NEW_WORD_REQS[cid] = {}
                if uid not in NEW_WORD_REQS[cid]:
                    NEW_WORD_REQS[cid][uid] = []
                NEW_WORD_REQS[cid][uid].append(wd)
                await bot.answer_callback_query(call.id, f'{wd} added to queue!')
            elif call.data == 'addWord_req_pop':
                for chat_id in list(NEW_WORD_REQS.keys()):
                    for user_id in list(NEW_WORD_REQS[chat_id].keys()):
                        if wd in NEW_WORD_REQS[chat_id][user_id]:
                            NEW_WORD_REQS[cid][uid].remove(wd)
                            if not NEW_WORD_REQS[cid][uid]:
                                del NEW_WORD_REQS[cid][uid]
                            if not NEW_WORD_REQS[cid]:
                                del NEW_WORD_REQS[cid]
                            await bot.answer_callback_query(call.id, f'{wd} removed from queue!')
                            return
                await bot.answer_callback_query(call.id, f'{wd} not found in queue!')
        elif call.data == 'newLeader_req_cancel':
            if STATE.get(str(chatId))[0] == WAITING_FOR_WORD and STATE.get(str(chatId))[5]:
                if userObj.id == STATE.get(str(chatId))[1]:
                    await bot.answer_callback_query(call.id, '❌ Only the requester and other participants can undo this action!', show_alert=True, cache_time=5)
                    return
                STATE[str(chatId)][5] = False
                await sleep(0.1)
                msg = '❌ ~' + escChar(call.message.text.split("\n")[0][2:]) + f'~\nCancelled by *{escChar(escName(userObj))}*'
                await bot.edit_message_text(msg, chatId, call.message.message_id, parse_mode='MarkdownV2')
            else:
                await bot.answer_callback_query(call.id, '❌ Request was expired!', cache_time=30)

        # Game panel inline btn handlers for leader use cases only ---------------- #
        elif call.data == 'see_word':
            if curr_game['status'] == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True, cache_time=5)
            elif curr_game['status'] == 'not_leader' and userObj.id != MY_IDs[1][0]:
                await bot.answer_callback_query(call.id, "⚠ Only leader can see the word!", show_alert=True, cache_time=30)
            else:
                word = WORD.get(str(chatId)) if WORD.get(str(chatId)) is not None else "[Change this word] ❌"
                await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
        elif call.data == 'generate_hints':
            if curr_game['status'] == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True, cache_time=5)
            elif curr_game['status'] == 'not_leader':
                await bot.answer_callback_query(call.id, "⚠ Ask to leader for hints!", show_alert=True, cache_time=30)
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
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True, cache_time=5)
            elif curr_game['status'] == 'not_leader':
                await bot.answer_callback_query(call.id, "⚠ Only leader can change the word!", show_alert=True, cache_time=30)
            else:
                WORD.update({str(chatId): funcs.getNewWord()})
                await bot.answer_callback_query(call.id, f"Word: {WORD.get(str(chatId))}", show_alert=True)
                await changeWord(call)
                STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(curr_game['started_at']), 'True', STATE.get(str(chatId))[5]]})
        elif call.data == 'drop_lead':
            if curr_game['status'] == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True, cache_time=5)
            elif curr_game['status'] == 'not_leader':
                await bot.answer_callback_query(call.id, "⚠ You are not leading the game!", show_alert=True, cache_time=30)
            else:
                await stopGame(call, isRefused=True, word=(f' *~{WORD.get(str(chatId))}~*' if STATE.get(str(chatId))[2] else ''))
                await bot.delete_message(chatId, call.message.message_id)
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})

# Start the bot
print("[PROD] Bot is running...")
asyncio.run(bot.infinity_polling())
