import os
import io
import re
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
from asyncio import sleep, to_thread
from telebot.async_telebot import AsyncTeleBot, ExceptionHandler, traceback
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import funcs
from funcs import AI_TRIGGER_MSGS, escName, escChar, getWordMatchAIResp
from sql_helper.current_running_game_sql import addGame_sql, getGame_sql, removeGame_sql
from sql_helper.rankings_sql import incrementPoints_sql, getUserPoints_sql, getTop25Players_sql, getTop25PlayersInAllChats_sql, getTop10Chats_sql, getAllChatIds_sql
from sql_helper.daily_botstats_sql import update_dailystats_sql, get_last30days_stats_sql
from sql_helper.ai_conv_sql import getCrocoAIConv_sql, updateCrocoAIPrompt_sql

BOT_TOKEN = os.environ.get('BOT_TOKEN', None)
OTHER_SU_IDs = [5145384413]
MY_IDs = [6740198215, [5321125784, 6060491450, 6821441983, 7497979187, *OTHER_SU_IDs], [-1002625968421]] # Bot ID, [Superuser IDs], [Superchat IDs]
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
        print(f'\n ⟩ {t} ⟩ {e}\n\n{traceback.format_exc()}')
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
    word = await funcs.getNewWord()
    WORD.update({str(chatId): word})
    if not (await to_thread(addGame_sql, chatId, userObj.id, word)):
        msg = await bot.send_message(chatId, '❌ An unexpected error occurred while starting game! Please try again later.\n\nUse /help for more information.')
        await to_thread(removeGame_sql, chatId)
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
        await bot.send_message(chatId, f'🛑 *Game stopped\!*\n[{escChar(fullname)}](tg://user?id={userObj.id}) \[\-1💵\] revealed the word: *{WORD.get(str(chatId))}*',
                               reply_markup=getInlineBtn('revealed_word'), parse_mode='MarkdownV2')
    else:
        curr_game = await getCurrGame(chatId, userObj.id)
        curr_status = curr_game['status']
        if curr_status == 'not_started':
            msg = await bot.send_message(chatId, '⚠ The game is already stopped!', disable_notification=True)
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return False
        chat_admins = await bot.get_chat_administrators(chatId)
        if (userObj.id not in (admin.user.id for admin in chat_admins)) and curr_status == 'not_leader' and (userObj.id not in MY_IDs[1]):
            msg = await bot.send_message(chatId, '⚠ Only an admin or game leader can stop game!', disable_notification=True)
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return False
        await bot.send_message(chatId, '🛑 The game is stopped!\nTo start a new game, hit command:\n/game@CrocodileGameEnn_bot')
    # Delete word from database
    WORD.pop(str(chatId), None)
    # HINTS.pop(str(chatId), None)
    await to_thread(removeGame_sql, chatId)
    return True

async def changeWord(message, last_word):
    # Generate new word and revoke old one
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    user_obj = message.from_user
    global STATE
    state = STATE.get(str(chatId), [-1])
    # HINTS.pop(str(chatId), None)
    # Save word to database and return (leader changed the word)
    await to_thread(addGame_sql, chatId, user_obj.id, WORD.get(str(chatId)))
    if (state[0] == WAITING_FOR_WORD and state[2]) or (state[0] == WAITING_FOR_COMMAND):
        await bot.send_message(chatId, f'❗{escChar(escName(user_obj))} changed the word\! ~*{escChar(last_word)}*~', parse_mode='MarkdownV2')

async def getCurrGame(chatId, userId):
    state = STATE.get(str(chatId), [-1])
    if state[0] == WAITING_FOR_WORD:
        # Game is started (known from STATE)
        return dict(status=('leader' if state[1]==userId else 'not_leader'), started_at=state[3])
    else:
        # Get current game from database
        curr_game = await to_thread(getGame_sql, chatId)
        if curr_game is None: # Game is not started yet
            return dict(status='not_started')
        elif int(curr_game.leader_id) == userId: # User is a leader
            return dict(status='leader', started_at=int(curr_game.started_at), data=curr_game)
        else: # User is not a leader
            return dict(status='not_leader', started_at=int(curr_game.started_at), data=curr_game)

# Other functions --------------------------------------------------------------------------------- #
def getPromptForMediaAI(userId, msgText, rplyToMsg, rplyMsg, rplyMsg_contentType, prompt, usr_name, supported_media) -> tuple | None:
    if msgText.lower().replace('@croco', '') == '':
        if rplyMsg.from_user.id == MY_IDs[0]:
            return None
        else:
            rplyToMsg = rplyMsg
            rply_usr_name = (''.join(filter(str.isalpha, escName(rplyMsg.from_user, 25, 'full')))).strip()
            if rply_usr_name in ['', 'id']: rply_usr_name = 'Another Member'
            if rplyMsg_contentType in supported_media:
                prompt = f'{rply_usr_name}: [content: {rplyMsg_contentType}]\n{rplyMsg.caption}' if rplyMsg.caption else f'{rply_usr_name}: [content: {rplyMsg_contentType}]'
            else:
                prompt = f'{rply_usr_name}: {rplyMsg.text}'
    elif rplyMsg.from_user.id == MY_IDs[0]:
        if rplyMsg_contentType in supported_media:
            prompt = f'Croco: [content: {rplyMsg_contentType}]\n{rplyMsg.caption}\n\n{prompt}' if rplyMsg.caption \
                else f'Croco: [content: {rplyMsg_contentType}]\n\n{prompt}'
        else:
            prompt = f'Croco: {rplyMsg.text}\n\n{prompt}'
    elif rplyMsg.from_user.id != userId:
        rply_usr_name = (''.join(filter(str.isalpha, escName(rplyMsg.from_user, 25, 'full')))).strip()
        if rply_usr_name in ['', 'id']: rply_usr_name = 'Another Member'
        if rplyMsg_contentType in supported_media:
            prompt = f'{rply_usr_name}: [content: {rplyMsg_contentType}]\n{rplyMsg.caption}\n\n{prompt}' if rplyMsg.caption \
                else f'{rply_usr_name}: [content: {rplyMsg_contentType}]\n\n{prompt}'
        else:
            prompt = f'{rply_usr_name}: {rplyMsg.text}\n\n{prompt}'
    else:
        if rplyMsg_contentType in supported_media:
            prompt = f'{usr_name}: [content: {rplyMsg_contentType}]\n{rplyMsg.caption}\n\n{prompt}' if rplyMsg.caption \
                else f'{usr_name}: [content: {rplyMsg_contentType}]\n\n{prompt}'
        else:
            prompt = f'{usr_name}: {rplyMsg.text}\n\n{prompt}'
    return (rplyToMsg, prompt)

async def getFileFromMsgObj(message, msgVarObj, msgVarObj_contentType='file') -> tuple | None:
    file_obj = None
    mime_type = 'image/png'
    try:
        if msgVarObj.photo:
            file_obj = await bot.get_file(msgVarObj.photo[-1].file_id)
        elif msgVarObj.video:
            file_obj = await bot.get_file(msgVarObj.video.file_id)
            mime_type = msgVarObj.video.mime_type
        elif msgVarObj.audio:
            file_obj = await bot.get_file(msgVarObj.audio.file_id)
            mime_type = msgVarObj.audio.mime_type
        elif msgVarObj.voice:
            file_obj = await bot.get_file(msgVarObj.voice.file_id)
            mime_type = msgVarObj.voice.mime_type
    except Exception as e:
        if 'too big' in str(e):
            link = f'[Learn more why.](https://core.telegram.org/bots/api#file:~:text=The%20maximum%20file%20size%20to%20download%20is%2020%20MB)'
            await bot.reply_to(message, '❌ File size must be < 20MB.\n\n' + link, allow_sending_without_reply=True,
                                parse_mode='Markdown', disable_web_page_preview=True)
        else:
            await bot.reply_to(message, '❌ An unexpected error occurred!', allow_sending_without_reply=True)
        return None
    if file_obj is None:
        await bot.reply_to(message, f'❌ Failed to retrieve the {msgVarObj_contentType}!', allow_sending_without_reply=True)
        return None
    # file_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_obj.file_path}'
    # Save the file locally
    # file_name = f'{contentType}.{file_obj.file_path.split('.')[-1]}'
    # with open(file_name, 'wb') as new_file:
    #     new_file.write(file_bytes)
    return (await bot.download_file(file_obj.file_path), mime_type)

# Bot commands handler ------------------------------------------------------------------------ #

@bot.message_handler(commands=['start'])
async def start_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        msgTxt = message.text.lower()
        if message.chat.type == 'private':
            await startBotCmdInPvt(message, chatId)
        elif msgTxt == '/start' or msgTxt.startswith('/start ') or msgTxt.startswith('/start@croco'):
            if (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
                return
            await bot.send_message(chatId, '👋🏻 Hey!\nI\'m Crocodile Game Bot. To start a game, hit command: /game')

# Basic commands (send, cancelbroadcast, fwd, botstats, serverinfo, info, del) (superuser only) ---------------------- #
@bot.message_handler(commands=['send'])
async def sendBroadcast_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
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
        c_ids, u_ids = await to_thread(getAllChatIds_sql)
        # Add both chat IDs and user IDs to chat_ids
        chat_ids.extend(c_ids)
        chat_ids.extend(u_ids)
        # Remove duplicates
        chat_ids = list(set(chat_ids))
        # Remove my IDs and blocked chats
        chat_ids = [chat_id for chat_id in chat_ids if chat_id not in BLOCK_CHATS]
        await bot.reply_to(message, f'Total chat IDs: {len(chat_ids)}', allow_sending_without_reply=True)
        return
    elif message.text.strip() == '/send * state CONFIRM':
        # Forward to all chats from STATE
        chat_ids = [chat_id for chat_id in STATE.keys() if chat_id not in BLOCK_CHATS]
    elif message.text.strip() == '/send * groups CONFIRM':
        c_ids, u_ids = await to_thread(getAllChatIds_sql)
        chat_ids.extend(c_ids)
        chat_ids = list(set(chat_ids))
        chat_ids = [chat_id for chat_id in chat_ids if chat_id not in BLOCK_CHATS]
    elif message.text.strip() == '/send * users CONFIRM':
        c_ids, u_ids = await to_thread(getAllChatIds_sql)
        chat_ids.extend(u_ids)
        chat_ids = list(set(chat_ids))
        chat_ids = [chat_id for chat_id in chat_ids if chat_id not in BLOCK_USERS]
    elif message.text.strip() == '/send * CONFIRM':
        # Forward to all chats from your database
        c_ids, u_ids = await to_thread(getAllChatIds_sql)
        chat_ids.extend(c_ids)
        chat_ids.extend(u_ids)
        chat_ids = list(set(chat_ids))
        chat_ids = [chat_id for chat_id in chat_ids if chat_id not in (BLOCK_CHATS + BLOCK_USERS)]
    else:
        # Forward to specified chat IDs
        command_parts = message.text.split(' ', 2)
        if len(command_parts) > 2 and command_parts[1] == '-id':
            chat_ids_str = command_parts[2]
            chat_ids = [int(chat_id.strip()) for chat_id in chat_ids_str.split(',') if chat_id.strip().lstrip('-').isdigit()]
            chat_ids = list(set(chat_ids))
    if len(chat_ids) == 0:
        await bot.reply_to(message, 'No chat IDs specified!', allow_sending_without_reply=True)
        return
    await bot.send_message(MY_IDs[2][0], f'\#Broadcast started by: [{escChar(escName(user_obj))}](tg://user?id={user_obj.id})\n\n'
                    f'*Parameters:* {escChar(message.text[6:])}\n*Total chats:* {len(chat_ids)}', parse_mode='MarkdownV2')
    i = 0
    global CANCEL_BROADCAST
    CANCEL_BROADCAST = 0
    for chat_id in chat_ids:
        if CANCEL_BROADCAST:
            break
        try:
            await bot.forward_message(chat_id, message.chat.id, message.reply_to_message.message_id)
            i += 1
            await sleep(1)
        except Exception as e:
            print(f'Failed to forward message to chat ID {chat_id}.\nError: {str(e)}')
            err_msg.append(chat_id)
    if len(err_msg) > 0:
        await bot.reply_to(message, f'Sent: {i}\nFailed: {len(err_msg)}\nTotal: {len(chat_ids)}', allow_sending_without_reply=True)
        if len(err_msg) > 1000:
            with open('failed_chat_ids.txt', 'w') as f:
                f.write('\n'.join(map(str, err_msg)))
            with open('failed_chat_ids.txt', 'rb') as f:
                await bot.send_document(MY_IDs[2][0], f, caption='Failed chat IDs', protect_content=True, disable_notification=True)
            return
        await bot.reply_to(message, f'Failed to forward message to chat IDs: {err_msg}', allow_sending_without_reply=True, disable_notification=True)
    else:
        await bot.reply_to(message, 'Message forwarded to all chats successfully!', allow_sending_without_reply=True)

@bot.message_handler(commands=['cancelbroadcast'])
async def cancelBroadcast_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    global CANCEL_BROADCAST
    CANCEL_BROADCAST = 1
    await bot.reply_to(message, 'Broadcast cancelled!', allow_sending_without_reply=True)
    await sleep(2)
    await bot.send_message(MY_IDs[2][0], f'\#Broadcast cancelled by: [{escChar(escName(user_obj))}](tg://user?id={user_obj.id})', parse_mode='MarkdownV2')

# Forward message by message ID and chat ID
@bot.message_handler(commands=['fwd'])
async def fwd_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    command_parts = message.text.split(' ', 3)
    if len(command_parts) < 3:
        await bot.reply_to(message, 'No chat ID or message ID specified!', allow_sending_without_reply=True)
        return
    chat_id = command_parts[1]
    msg_id = command_parts[2]
    if not (chat_id.isdigit() or (chat_id.startswith('-') and chat_id[1:].isdigit())
            or (chat_id.startswith('@') and chat_id[1].isalpha())):
        await bot.reply_to(message, 'Invalid chat ID!', allow_sending_without_reply=True)
        return
    if not msg_id.isdigit():
        await bot.reply_to(message, 'Invalid message ID!', allow_sending_without_reply=True)
        return
    try:
        print(f'Forwarding from: {chat_id}\nTo: {chatId}\nMessage ID: {msg_id}\n')
        await bot.forward_message(chatId, chat_id, msg_id, True, disable_notification=True)
    except Exception as e:
        await bot.reply_to(message, f'Failed to forward message.\n\nError: {str(e).split("Description:")[-1].strip()}', allow_sending_without_reply=True)

# Get chat administrators
@bot.message_handler(commands=['getadmins'])
async def getAdmins_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        await bot.reply_to(message, 'No chat ID specified!', allow_sending_without_reply=True)
        return
    chat_id = command_parts[1]
    if not (chat_id.isdigit() or (chat_id.startswith('-') and chat_id[1:].isdigit())
            or (chat_id.startswith('@') and chat_id[1].isalpha())):
        await bot.reply_to(message, 'Invalid chat ID!', allow_sending_without_reply=True)
        return
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except Exception as e:
        await bot.reply_to(message, f'Failed to fetch admins.\n\nError: {str(e).split("Description:")[-1].strip()}', allow_sending_without_reply=True)
        return
    admin_list = '\n'.join([f'*{i}\.* [{escChar(escName(admin.user, 50, "full"))}](tg://user?id={admin.user.id}) − {admin.user.id} *\({admin.status}\)*'
                            .replace('\(administrator\)', '').replace('(creator\\', '(owner\\')
                            for i, admin in enumerate(admins, 1)])
    await bot.reply_to(message, f'👥 *Chat Admins:*\n\n{admin_list}', parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)

@bot.message_handler(commands=['botstats'])
async def botStats_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    total_ids = [] # Total chats
    g_ids, u_ids = await to_thread(getAllChatIds_sql) # Group chats, Private (user) chats
    g_ids, u_ids = (list(set(g_ids)), list(set(u_ids)))
    total_ids.extend(g_ids)
    total_ids.extend(u_ids)
    total_ids = list(set(total_ids))
    import wordlist
    stats_msg = f'🤖 *Bot stats \(complete\):*\n\n' \
        f'*Chats \(total\):* {len(total_ids)}\n' \
        f'*Users:* {len(u_ids)}\n' \
        f'*Groups:* {len(g_ids)}\n' \
        f'*Potential reach:* 4\.1M\n' \
        f'*Super\-users:* {len(MY_IDs[1])}\n' \
        f'*AI users:* {len(AI_USERS)}\n' \
        f'*AI groups:* {len(CROCO_CHATS)}\n' \
        f'*Groups with cheaters:* {len(CHEAT_RECORD)}\n' \
        f'*Detected cheats:* {sum(CHEAT_RECORD.values())}\n' \
        f'*Blocked groups:* {len(BLOCK_CHATS)}\n' \
        f'*Blocked users:* {len(BLOCK_USERS)}\n' \
        f'*Total WORDs:* {len(wordlist.WORDLIST)}\n' \
        f'*Active chats \(since reboot\):* {len(STATE)}\n'
    last30days_stats = await to_thread(get_last30days_stats_sql)
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
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    plt.close()
    # Append today's stats to message
    stats_msg = f'📅 *Today\'s stats:*\n\n' \
        f'*New chats:* {chats_added[-1]}\n' \
        f'*Games played:* {int(games_played[-1] * 100)}\n' \
        f'*Cheating rate:* {escChar(100*cheats_detected[-1]/games_played[-1])[:4]}%\n' \
        '                                     \n' + stats_msg
    await bot.send_photo(chatId, photo=buffer.getvalue(), caption=stats_msg, parse_mode='MarkdownV2', protect_content=True,
                            reply_to_message_id=message.message_id, allow_sending_without_reply=True)

@bot.message_handler(commands=['sysinfo', 'serverinfo'])
async def serverInfo_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    msg = await bot.reply_to(message, '📡 Fetching latest reports...', allow_sending_without_reply=True, disable_notification=True)
    try:
        def getSysInfo():
            # Fetch system info
            cpu_usage = psutil.cpu_percent()
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            # Fetch network speed
            st = speedtest.Speedtest()
            st.get_best_server()
            download_speed = round(st.download() / 1024 / 1024, 2)
            upload_speed = round(st.upload() / 1024 / 1024, 2)
            ping = round(st.results.ping)
            text = f'🖥 *Server info:*\n\n' \
                f'*System:* {escChar(platform.system())} {escChar(platform.release())}\n' \
                f'*CPU usage:* {escChar(cpu_usage)}%\n' \
                f'*Memory usage:* {escChar(mem.percent)}%\n' \
                f'*Disk usage:* {escChar(disk.percent)}%\n' \
                f'*Network speed:*\n' \
                f'\t*– Download:* {escChar(download_speed)} Mb/s\n' \
                f'\t*– Upload:* {escChar(upload_speed)} Mb/s\n' \
                f'\t*– Ping:* {escChar(ping)} ms\n' \
                f'*Uptime:* {escChar(time.strftime("%H:%M:%S", time.gmtime(time.time() - psutil.boot_time())))}\n'
            return text
        # Fetch results in a separate thread
        resTxt = await to_thread(getSysInfo)
    except Exception as e:
        resTxt = f'🖥 *Server info:* Failed to fetch data\.\n\n*Error:* {escChar(e.__repr__())}'
    await bot.edit_message_text(text=resTxt, chat_id=message.chat.id, message_id=msg.message_id, parse_mode='MarkdownV2')

# See chat/user info
@bot.message_handler(commands=['info'])
async def info_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
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
                                        parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)
            return
        await bot.reply_to(message, f'👤 *User info:*\n\n'
                                    f'*ID:* `{escChar(rply_chat_obj.id)}`\n'
                                    f'*Name:* {escChar(escName(rply_chat_obj, 100, "full"))}\n'
                                    f'*Username:* @{escChar(rply_chat_obj.username)}\n'
                                    f'*User link:* [link](tg://user?id={escChar(rply_chat_obj.id)})\n',
                                    parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)
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
                                        parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)
    else:
        await bot.reply_to(message, f'👥 *Chat info:*\n\n'
                                            f'*ID:* `{escChar(chat_obj.id)}`\n'
                                            f'*Type:* {escChar(chat_obj.type)}\n'
                                            f'*Title:* {escChar(chat_obj.title)}\n'
                                            f'*Username:* @{escChar(chat_obj.username)}\n'
                                            f'*Invite link:* {escChar(chat_obj.invite_link)}\n'
                                            f'*Description:* {escChar(chat_obj.description)}\n',
                                            parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)

@bot.message_handler(commands=['del'])
async def del_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
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
        alrt_msg = await bot.reply_to(message, '*Permission required:* `can_delete_messages`', parse_mode='MarkdownV2',
                                      allow_sending_without_reply=True, disable_notification=True)
        await sleep(10)
        await bot.delete_message(message.chat.id, alrt_msg.message_id)
        return
    await bot.delete_message(message.chat.id, rply_msg.message_id)

@bot.message_handler(commands=['showcheats'])
async def showCheats_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    toal_cheats = sum(CHEAT_RECORD.values())
    cheat_msg = ''
    for i, (chat_id, cheat_count) in enumerate(CHEAT_RECORD.items(), 1):
        cheat_msg += f'{i}. {chat_id} — {cheat_count}\n'
    cheat_msg = '🔍 No cheats found yet\!' if cheat_msg == '' else f'🕵🏻‍♂️ *Cheats detected in groups:* `{toal_cheats}`\n\n' + escChar(cheat_msg)
    await bot.reply_to(message, cheat_msg, parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)

# Admin commands handler (mute, unmute, ban) (superuser only) --------------------------------- #
# TODO: Add/Fix mute/unmute/ban/unban methods
@bot.message_handler(commands=['mute'])
async def mute_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
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
            try:
                await bot.restrict_chat_member(message.chat.id, rply_usr_obj.id)
            except Exception as e:
                if 'is an administrator' in str(e):
                    await bot.reply_to(message, 'I cannot mute an admin!', allow_sending_without_reply=True)
                    return
                else:
                    await bot.reply_to(message, 'Failed to mute user!', allow_sending_without_reply=True)
                    return
            await bot.reply_to(message, f'Muted [{escName(rply_usr_obj)}](tg://user?id={rply_usr_obj.id}).',
                               parse_mode='Markdown', allow_sending_without_reply=True)
            await sleep(3)
            # Send logs to log chat
            await bot.send_message(MY_IDs[2][0], f'🔇 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#muted\n'
                                                 f'*User:* [{escChar(escName(rply_usr_obj))}](tg://user?id={rply_usr_obj.id})\n'
                                                 f'*Chat ID:* `{message.chat.id}`\n'
                                                 f'*Message ID:* `{message.message_id}`', parse_mode='MarkdownV2')
        else:
            await bot.reply_to(message, 'No user specified!', allow_sending_without_reply=True)
        return
    user_id = command_parts[1]
    if not user_id.isdigit():
        await bot.reply_to(message, 'Invalid user ID!', allow_sending_without_reply=True)
        return
    if user_id in MY_IDs[1]:
        await bot.reply_to(message, 'I cannot mute a superuser!', allow_sending_without_reply=True)
        return
    try:
        usr_obj = await bot.get_chat_member(message.chat.id, user_id)
        if usr_obj.status in ('administrator', 'creator'):
            await bot.reply_to(message, 'I cannot mute an admin!', allow_sending_without_reply=True)
            return
    except:
        await bot.reply_to(message, 'User not found!', allow_sending_without_reply=True)
        return
    await bot.restrict_chat_member(message.chat.id, usr_obj.user.id)
    await bot.reply_to(message, f'Muted [{escName(usr_obj.user)}](tg://user?id={usr_obj.user.id}).',
                       parse_mode='Markdown', allow_sending_without_reply=True)
    await sleep(3)
    # Send logs to log chat
    await bot.send_message(MY_IDs[2][0], f'🔇 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#muted\n'
                                            f'*User:* [{escChar(escName(usr_obj.user))}](tg://user?id={usr_obj.user.id})\n'
                                            f'*Chat ID:* `{message.chat.id}`\n'
                                            f'*Message ID:* `{message.message_id}`', parse_mode='MarkdownV2')

@bot.message_handler(commands=['unmute'])
async def unmute_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
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
            await sleep(3)
            # Send logs to log chat
            await bot.send_message(MY_IDs[2][0], f'🔊 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#unmuted\n'
                                                 f'*User:* [{escChar(escName(rply_usr_obj))}](tg://user?id={rply_usr_obj.id})\n'
                                                 f'*Chat ID:* `{message.chat.id}`\n'
                                                 f'*Message ID:* `{message.message_id}`', parse_mode='MarkdownV2')
        else:
            await bot.reply_to(message, 'No user specified!', allow_sending_without_reply=True)
        return
    user_id = command_parts[1]
    if not user_id.isdigit():
        await bot.reply_to(message, 'Invalid user ID!', allow_sending_without_reply=True)
        return
    try:
        usr_obj = await bot.get_chat_member(message.chat.id, user_id)
        if usr_obj.status != 'restricted':
            await bot.reply_to(message, f'[{escName(usr_obj.user)}](tg://user?id={usr_obj.user.id}) is not muted!',
                               parse_mode='Markdown', allow_sending_without_reply=True)
            return
    except:
        await bot.reply_to(message, 'User not found!', allow_sending_without_reply=True)
        return
    await bot.restrict_chat_member(message.chat.id, usr_obj.user.id, can_send_messages=True)
    await bot.reply_to(message, f'[{escName(usr_obj.user)}](tg://user?id={usr_obj.user.id}) can speak now!',
                       parse_mode='Markdown', allow_sending_without_reply=True)
    await sleep(3)
    # Send logs to log chat
    await bot.send_message(MY_IDs[2][0], f'🔊 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#unmuted\n'
                                            f'*User:* [{escChar(escName(usr_obj.user))}](tg://user?id={usr_obj.user.id})\n'
                                            f'*Chat ID:* `{message.chat.id}`\n'
                                            f'*Message ID:* `{message.message_id}`', parse_mode='MarkdownV2')

# Block/Unblock chat/user (superuser only) --------------------------------------------------------- #
@bot.message_handler(commands=['blockchat'])
async def blockchat_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    command_parts = message.text.split(' ', 3)
    if len(command_parts) < 2:
        await bot.reply_to(message, 'No chat ID specified!', allow_sending_without_reply=True, disable_notification=True)
        return
    chat_id = command_parts[1]
    if not (chat_id.isdigit() or (chat_id.startswith('-') and chat_id[1:].isdigit())
            or (chat_id.startswith('@') and chat_id[1].isalpha())):
        await bot.reply_to(message, 'Invalid chat ID!', allow_sending_without_reply=True, disable_notification=True)
        return
    if chat_id[0] != '@' and int(chat_id) in BLOCK_CHATS:
        await bot.reply_to(message, 'Chat already blocked!', allow_sending_without_reply=True, disable_notification=True)
        return
    title = 'unknown\_chat'
    try:
        chat_obj = await bot.get_chat(chat_id)
        if chat_obj.type == 'private':
            await bot.reply_to(message, 'Provided id belongs to a user! To block a user, use /blockuser command.', allow_sending_without_reply=True)
            return
        chat_id = chat_obj.id
        title = chat_obj.title
    except:
        if chat_id[0] == '@':
            await bot.reply_to(message, 'Chat not found!', allow_sending_without_reply=True, disable_notification=True)
            return
    BLOCK_CHATS.append(int(chat_id))
    await bot.reply_to(message, f'Chat {title} blocked successfully!', parse_mode='Markdown', allow_sending_without_reply=True)
    await sleep(1)
    # Send logs to log chat
    await bot.send_message(MY_IDs[2][0], f'🚫 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#blocked\n'
                                            f'*Chat:* {title}\n'
                                            f'*Chat ID:* `{chat_id}`\n', parse_mode='MarkdownV2')
    await sleep(1)
    # Send notice to blocked chat
    if len(command_parts) > 2 and title != 'unknown\_chat':
        await sleep(3)
        await bot.send_message(chat_id, f'🚫 *This chat/group was banned from using this bot due to a violation of our Terms of Service\.*\n\n' \
            f'If you\'re chat/group owner and believe this is a mistake, please write to: \@CrocodileGamesGroup', parse_mode='MarkdownV2')

@bot.message_handler(commands=['unblockchat'])
async def unblockchat_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        await bot.reply_to(message, 'No chat ID specified!', allow_sending_without_reply=True)
        return
    chat_id = command_parts[1]
    if not (chat_id.isdigit() or (chat_id.startswith('-') and chat_id[1:].isdigit())
            or (chat_id.startswith('@') and chat_id[1].isalpha())):
        await bot.reply_to(message, 'Invalid chat ID!', allow_sending_without_reply=True)
        return
    if chat_id[0] != '@' and int(chat_id) not in BLOCK_CHATS:
        await bot.reply_to(message, 'Chat not blocked!', allow_sending_without_reply=True)
        return
    title = 'unknown\_chat'
    try:
        chat_obj = await bot.get_chat(chat_id)
        if chat_obj.type == 'private':
            await bot.reply_to(message, 'Provided id belongs to a user! To unblock a user, use /unblockuser command.', allow_sending_without_reply=True)
            return
        chat_id = chat_obj.id
        title = chat_obj.title
    except:
        if chat_id[0] == '@':
            await bot.reply_to(message, 'Chat not found!', allow_sending_without_reply=True)
            return
    BLOCK_CHATS.remove(int(chat_id))
    await bot.reply_to(message, f'Chat {title} unblocked successfully!', parse_mode='Markdown', allow_sending_without_reply=True)
    await sleep(1)
    # Send logs to log chat
    await bot.send_message(MY_IDs[2][0], f'🔓 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#unblocked\n'
                                            f'*Chat:* {title}\n'
                                            f'*Chat ID:* `{chat_id}`\n', parse_mode='MarkdownV2')

@bot.message_handler(commands=['blockuser'])
async def blockuser_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
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
            user_title = f'[{escName(rply_usr_obj)}](tg://user?id={rply_usr_obj.id})'
            await bot.reply_to(message, f'User {user_title} blocked!', parse_mode='Markdown', allow_sending_without_reply=True)
            await sleep(1)
            # Send logs to log chat
            await bot.send_message(MY_IDs[2][0], f'🚫 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#blocked\n'
                                                    f'*User:* {user_title}\n'
                                                    f'*User ID:* `{rply_usr_obj.id}`\n', parse_mode='MarkdownV2')
        else:
            await bot.reply_to(message, 'No user specified!', allow_sending_without_reply=True)
        return
    user_id = command_parts[1]
    if not (user_id.isdigit() or (user_id.startswith('@') and user_id[1].isalpha())):
        await bot.reply_to(message, 'Invalid user ID!', allow_sending_without_reply=True)
        return
    if user_id[0] != '@' and int(user_id) in BLOCK_USERS:
        await bot.reply_to(message, 'User already blocked!', allow_sending_without_reply=True)
        return
    user_title = 'unknown\_user'
    try:
        usr_obj = await bot.get_chat(user_id)
        if usr_obj.type != 'private':
            await bot.reply_to(message, 'Provided id belongs to a group! To block a group, use /blockchat command.', allow_sending_without_reply=True)
            return
        user_id = usr_obj.id
        user_title = f'[{escName(usr_obj)}](tg://user?id={usr_obj.id})'
    except:
        if user_id[0] == '@':
            await bot.reply_to(message, 'User not found!', allow_sending_without_reply=True)
            return
    BLOCK_USERS.append(int(user_id))
    await bot.reply_to(message, f'User {user_title} blocked!', parse_mode='Markdown', allow_sending_without_reply=True)
    await sleep(1)
    # Send logs to log chat
    await bot.send_message(MY_IDs[2][0], f'🚫 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#blocked\n'
                                            f'*User:* {user_title}\n'
                                            f'*User ID:* `{user_id}`\n', parse_mode='MarkdownV2')

@bot.message_handler(commands=['unblockuser'])
async def unblockuser_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
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
            user_title = f'[{escName(rply_usr_obj)}](tg://user?id={rply_usr_obj.id})'
            await bot.reply_to(message, f'User {user_title} unblocked!', parse_mode='Markdown', allow_sending_without_reply=True)
            await sleep(1)
            # Send logs to log chat
            await bot.send_message(MY_IDs[2][0], f'🔓 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#unblocked\n'
                                                    f'*User:* {user_title}\n'
                                                    f'*User ID:* `{rply_usr_obj.id}`\n', parse_mode='MarkdownV2')
        else:
            await bot.reply_to(message, 'No user specified!', allow_sending_without_reply=True)
        return
    user_id = command_parts[1]
    if not (user_id.isdigit() or (user_id.startswith('@') and user_id[1].isalpha())):
        await bot.reply_to(message, 'Invalid user ID!', allow_sending_without_reply=True)
        return
    if user_id[0] != '@' and int(user_id) not in BLOCK_USERS:
        await bot.reply_to(message, 'User not blocked!', allow_sending_without_reply=True)
        return
    user_title = 'unknown\_user'
    try:
        usr_obj = await bot.get_chat(user_id)
        if usr_obj.type != 'private':
            await bot.reply_to(message, 'Provided id belongs to a group! To unblock a group, use /unblockchat command.', allow_sending_without_reply=True)
            return
        user_id = usr_obj.id
        user_title = f'[{escName(usr_obj)}](tg://user?id={usr_obj.id})'
    except:
        if user_id[0] == '@':
            await bot.reply_to(message, 'User not found!', allow_sending_without_reply=True)
            return
    BLOCK_USERS.remove(int(user_id))
    await bot.reply_to(message, f'User {user_title} unblocked!', parse_mode='Markdown', allow_sending_without_reply=True)
    await sleep(1)
    # Send logs to log chat
    await bot.send_message(MY_IDs[2][0], f'🔓 *[{escChar(escName(user_obj))}](tg://user?id={user_obj.id})* \#unblocked\n'
                                            f'*User:* {user_title}\n'
                                            f'*User ID:* `{user_id}`\n', parse_mode='MarkdownV2')

# Add/Remove/Show AI chats (superuser only) --------------------------------------------------- #
@bot.message_handler(commands=['aiuser'])
async def setaiuser_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
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
                await bot.send_message(chatId, '❌ Reply to an user message\'s you want to set AI user!')
        else:
            await bot.send_message(chatId, '❌ Need superuser privilege to execute this command!')

@bot.message_handler(commands=['delaiuser'])
async def delaiuser_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
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
                await bot.send_message(chatId, '❌ Reply to an user\'s message you want to remove AI access from!')
        else:
            await bot.send_message(chatId, '❌ Need superuser privilege to execute this command!')

@bot.message_handler(commands=['showaiusers'])
async def showaiusers_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        user_obj = message.from_user
        if user_obj.id in MY_IDs[1]:
            global AI_USERS
            if len(AI_USERS) == 0:
                await bot.send_message(chatId, '🤖 No AI users yet to show!')
            else:
                await bot.send_message(chatId, f"🤖 *AI users:*\n\n{', '.join([f'[{user}](tg://user?id={user})' for user in AI_USERS.keys()])}", parse_mode='MarkdownV2')
        else:
            await bot.send_message(chatId, '❌ Need superuser privilege to execute this command!')

# Ludo game commands handler (startludo) ------------------------------------------------------ #
@bot.message_handler(commands=['startludo'])
async def startludo_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    # chatId = message.chat.id
    # if chatId not in (BLOCK_CHATS + BLOCK_USERS):
    #     await bot.send_game(chatId, 'ludo')
    return

# Crocodile game commands handler ------------------------------------------------------------- #
# (game, stop, stats, mystats, ranking, globalranking, chatranking, rules, help, addword) ----- #
@bot.message_handler(commands=['game'])
async def start_game(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    userObj = message.from_user
    if message.chat.type == 'private':
        await startBotCmdInPvt(message, chatId)
        return
    if (chatId in BLOCK_CHATS) or (userObj.id in BLOCK_USERS) or (message.text.lower() == '/game@octopusen_bot'):
        return
    if (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
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
    curr_status = curr_game['status']
    if (curr_status != 'not_started'):
        state = STATE.get(str(chatId))
        if state is None or state[0] == WAITING_FOR_COMMAND:
            started_at = int(curr_game['started_at'])
            WORD.update({str(chatId): curr_game['data'].word})
            state = [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, started_at, 'False', False]
            STATE.update({str(chatId): state})
            if int(datetime.now(pytz.timezone('Asia/Kolkata')).timestamp()) - started_at > 43200:
                # Don't send [restart notice] if game started 12 hours ago
                return
            await bot.send_message(chatId, f'🔄 *Bot restarted\!*\nAll active games were restored back and will continue running\.', parse_mode='MarkdownV2')
        isNewPlyr = (await to_thread(getUserPoints_sql, userObj.id)) is None
        started_from = int(time.time() - curr_game['started_at'])
        if (started_from < 30 or (isNewPlyr and started_from < 600 and curr_status != 'leader')):
            msg = await bot.send_message(chatId, '⚠ Do not blabber! The game has already started.')
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return
        if state[5]:
            msg = await bot.send_message(chatId, '⚠ Do not blabber! Someone else is going to lead the game next.')
            await sleep(10)
            await bot.delete_message(chatId, msg.message_id)
            return
        fullname = escName(userObj)
        rmsg = await bot.send_message(chatId, f'⏳ *{escChar(fullname)}* want to lead the game\!\nIn `5` seconds\.\.\.',
                                        parse_mode='MarkdownV2', reply_markup=getInlineBtn('newLeader_req'))
        STATE[str(chatId)][5] = True
        for i in range(1, 6):
            await sleep(1)
            state = STATE.get(str(chatId))
            if state[0] == WAITING_FOR_COMMAND: # If game stopped before 5 secs
                return
            if not state[5]: # If cancelled by button press
                # print('Change-leader request cancelled! Chat:', chatId)
                return
            try:
                ico = '✅' if i == 5 else '⌛' if i&1 else '⏳'
                await bot.edit_message_text(f'{ico} *{escChar(fullname)}* want to lead the game\!\nIn `{5 - i}` seconds\.\.\.',
                    chatId, rmsg.message_id, parse_mode='MarkdownV2', reply_markup=getInlineBtn('newLeader_req'))
            except:
                return
        await sleep(0.3)
        await bot.delete_message(chatId, rmsg.message_id)
        await sleep(0.3)
    if await startGame(message) is not None:
        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), 'True', False]})
        await to_thread(update_dailystats_sql, datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)

@bot.message_handler(commands=['stop'])
async def stop_game(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    userObj = message.from_user
    if (message.chat.type != 'private') and (chatId not in BLOCK_CHATS) and (userObj.id not in BLOCK_USERS):
        if (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
            return
        global STATE
        if await stopGame(message):
            STATE.update({str(chatId): [WAITING_FOR_COMMAND]})

# See other user's stats (superuser only)
@bot.message_handler(commands=['stats'])
async def stats_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    if message.reply_to_message is None:
        await mystats_cmd(message)
        return
    chatId = message.chat.id
    user_obj = message.from_user
    if (chatId in BLOCK_CHATS and user_obj.id not in MY_IDs[1]) or (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
        return
    reply_user_obj = message.reply_to_message.from_user
    user_stats = await to_thread(getUserPoints_sql, reply_user_obj.id)
    if not user_stats:
        await bot.send_message(chatId, f'📊 {escName(reply_user_obj)} has no stats yet!', disable_notification=True)
    else:
        global GLOBAL_RANKS
        if not GLOBAL_RANKS:
            granks = {}
            grp_player_ranks = await to_thread(getTop25PlayersInAllChats_sql)
            for gprObj in grp_player_ranks:
                if gprObj.user_id in granks:
                    granks[gprObj.user_id]['points'] += gprObj.points
                else:
                    granks[gprObj.user_id] = {'user_id': int(gprObj.user_id), 'name': gprObj.name, 'points': gprObj.points}
            GLOBAL_RANKS = sorted(granks.values(), key=lambda x: x['points'], reverse=True)
        fullName = escName(reply_user_obj, 25, 'full').replace("🏅", "")
        grp_player_ranks = await to_thread(getTop25Players_sql, chatId, 2000)
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
                                f'{last_played}'
                                '                               \n'
                                f'❕ _You receive 1💵 reward for\neach correct word guess\._',
                                parse_mode='MarkdownV2')

@bot.message_handler(commands=['mystats'])
async def mystats_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    if chatId in BLOCK_CHATS or (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
        return
    user_obj = message.from_user
    curr_chat_user_stat = None
    curr_chat_points = 0
    total_points = 'Loading...'
    user_stats = await to_thread(getUserPoints_sql, user_obj.id)
    if not user_stats:
        await bot.send_message(chatId, '📊 You have no stats yet!', disable_notification=True)
    else:
        global GLOBAL_RANKS
        if not GLOBAL_RANKS:
            granks = {}
            grp_player_ranks = await to_thread(getTop25PlayersInAllChats_sql)
            for gprObj in grp_player_ranks:
                if gprObj.user_id in granks:
                    granks[gprObj.user_id]['points'] += gprObj.points
                else:
                    granks[gprObj.user_id] = {'user_id': int(gprObj.user_id), 'name': gprObj.name, 'points': gprObj.points}
            GLOBAL_RANKS = sorted(granks.values(), key=lambda x: x['points'], reverse=True)
        fullName = escName(user_obj, 25, 'full').replace('🏅', '')
        grp_player_ranks = await to_thread(getTop25Players_sql, chatId, 2000)
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
                                f'*Played in:* {played_in_chats} groups\n'
                                '                               \n'
                                f'❕ _You receive 1💵 reward for\neach correct word guess\._',
                                parse_mode='MarkdownV2')

@bot.message_handler(commands=['ranking'])
async def ranking_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        if message.chat.type == 'private':
            await bot.send_message(chatId, 'This command can be used in group chats only!\nOr use: /globalranking')
            return
        grp_player_ranks = await to_thread(getTop25Players_sql, chatId)
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
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        grp_player_ranks = await to_thread(getTop25PlayersInAllChats_sql)
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
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        grp_ranks = await to_thread(getTop10Chats_sql)
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
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    if chatId in BLOCK_CHATS or (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
        return
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
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    if chatId in BLOCK_CHATS or (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
        return
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
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    user_obj = message.from_user
    if (chatId in (BLOCK_CHATS + BLOCK_USERS) and user_obj.id not in MY_IDs[1]) or user_obj.id in BLOCK_USERS:
        return
    command_parts = message.text.split(' ', 2)
    if len(command_parts) < 2:
        await bot.send_message(chatId, '❌ No word specified!', disable_notification=True)
        return
    word = command_parts[1].lower()
    if len(word) > 20:
        await bot.send_message(chatId, '❌ Word must be less than 20 characters!', disable_notification=True)
        return
    if not word.isalpha():
        await bot.send_message(chatId, '❌ Word must contain only alphabets!', disable_notification=True)
        return
    if user_obj.id not in MY_IDs[1]:
        import wordlist
        if word in wordlist.WORDLIST:
            msg = await bot.reply_to(message, f'*{word}* exists in my dictionary\!', parse_mode='MarkdownV2',
                                     allow_sending_without_reply=True, disable_notification=True)
            await sleep(30)
            await bot.delete_message(chatId, msg.message_id)
            return
        await bot.reply_to(message, '☑️ Your request is being reviewed. You will be notified soon!',
                           allow_sending_without_reply=True, disable_notification=True)
        await sleep(1)
        await bot.send_message(MY_IDs[2][0], f'\#req\_addNewWord\n*ChatID:* `{chatId}`\n*UserID:* `{user_obj.id}`\n*Word:* `{word}`',
                               reply_markup=getInlineBtn('addWord_req'), parse_mode='MarkdownV2', disable_notification=True)
        return
    if not (await funcs.addNewWord(word)):
        msg = await bot.reply_to(message, f'*{word}* exists in my dictionary\!', parse_mode='MarkdownV2',
                                 allow_sending_without_reply=True, disable_notification=True)
        await sleep(30)
        await bot.delete_message(chatId, msg.message_id)
        return
    await bot.send_message(chatId, f'✅ A new word added to my dictionary\!\n\n*Word:* `{word}`', parse_mode='MarkdownV2', disable_notification=True)

@bot.message_handler(commands=['approve'])
async def approveAddWordReq_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    if not NEW_WORD_REQS:
        await bot.reply_to(message, '❌ No pending requests!', allow_sending_without_reply=True, disable_notification=True)
        return
    # Send confirmation message
    cnfrm_msg = ''
    for nwr_chat_id, nwr_users in NEW_WORD_REQS.items():
        cnfrm_msg += f'\n{escChar(nwr_chat_id)}: \[\n' + ',\n'.join([f'    [{u}](tg://user?id={u}): \[{nwr_users[u]}\]' for u in nwr_users]) + '\n\]'
    await bot.reply_to(message, f'⏳ *Pending requests:* {len(NEW_WORD_REQS)}\n{cnfrm_msg}', parse_mode='MarkdownV2', reply_markup=getInlineBtn('addWord_req_approve'), allow_sending_without_reply=True)

@bot.message_handler(commands=['cmdhelp', 'cmdlist'])
async def cmdlist_cmd(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    user_obj = message.from_user
    if user_obj.id not in MY_IDs[1]:
        return
    superusr_cmds = (
        '/info \- chat/user info\n'
        '/sysinfo \- server stats\n'
        '/botstats \- bot stats\n'
        '/send \- send broadcast\n'
        '/cancelbroadcast \- stop broadcast\n'
        '/fwd \- \[chat\_id\] \[message\_id\]\n'
        '/getadmins \- get chat admins\n'
        '/approve \- approve new requests\n'
        '/showcheats \- groups with cheats\n'
        '/cmdhelp \- show this message\n'
    )
    block_cmds = (
        '/blockchat \- block chat\n'
        '/unblockchat \- unblock chat\n'
        '/blockuser \- block user\n'
        '/unblockuser \- unblock user\n'
    )
    admin_cmds = (
        '/del \- delete message\n'
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
    await bot.send_message(chatId, '📖 *Bot commands:*\n\n'
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

# Handler for "bot added to chat/started by user" (send message to 1st superchat (MY_IDs[2][0]))
@bot.my_chat_member_handler(func=lambda message: message.old_chat_member.status in ['kicked', 'left']
                            and message.new_chat_member.status in ['member', 'administrator'])
async def handle_new_chat_members(message):
    chatId = message.chat.id
    userObj = message.from_user
    name_user = f'[{escChar(escName(userObj, 50, "full"))}](tg://user?id={userObj.id})' + (escChar(f' (@{userObj.username})') if userObj.username else f' \(`{userObj.id}`\)')
    if message.chat.type == 'private':
        await bot.send_message(MY_IDs[2][0], f'✅ Bot \#started by user: {name_user}', parse_mode='MarkdownV2', disable_notification=True)
        return
    username = f'\n\(\@{escChar(message.chat.username)}\)' if message.chat.username else ''
    if chatId not in BLOCK_CHATS:
        await bot.send_message(MY_IDs[2][0], f'✅ Bot \#added to chat: `{escChar(chatId)}`\n{escChar(message.chat.title)}{username}\nBy: {name_user}',
                               parse_mode='MarkdownV2', disable_notification=True)
        await sleep(3)
        markup_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton('📢 Get bot updates!', url='t.me/CrocodileGames')],
            [InlineKeyboardButton('🚀 Launch game!', callback_data='start_game')]
        ])
        await bot.send_message(chatId, f'👉🏻 Tap /help to see game commands.\n\nSupport group: @CrocodileGamesGroup', reply_markup=markup_btn)
    else:
        await bot.send_message(text=f'☑️ Bot \#added to a \#blocked chat: `{escChar(chatId)}`\n{escChar(message.chat.title)}{username}\nBy: {name_user}',
                               chat_id=MY_IDs[2][0], parse_mode='MarkdownV2', disable_notification=True)
        await sleep(3)
        await bot.send_message(chatId, f'🚫 *This chat/group was banned from using this bot due to violation of our Terms of Service\.*\n\n' \
            f'If you\'re chat/group owner and believe this is a mistake, please write to: \@CrocodileGamesGroup', parse_mode='MarkdownV2')
    await to_thread(update_dailystats_sql, datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 2, 1)

# Handler for "bot removed/stopped by chat/user" (send message to 1st superchat (MY_IDs[2][0]))
@bot.my_chat_member_handler(func=lambda message: message.new_chat_member.status in ['kicked', 'left'])
async def handle_my_chat_member(message):
    chatId = message.chat.id
    userObj = message.from_user
    name_chat = escChar(message.chat.title) + (escChar(f' (@{message.chat.username})') if message.chat.username else f' \(`{chatId}`\)')
    name_user = f'[{escChar(escName(userObj, 50, "full"))}](tg://user?id={userObj.id})' + (escChar(f' (@{userObj.username})') if userObj.username else f' \(`{userObj.id}`\)')
    if message.chat.type != 'private':
        await bot.send_message(MY_IDs[2][0], f'❌ Bot \#removed from chat:\n{name_chat}\nBy: {name_user}', parse_mode='MarkdownV2', disable_notification=True)
    else:
        await bot.send_message(MY_IDs[2][0], f'❌ Bot \#stopped by user: {name_user}', parse_mode='MarkdownV2', disable_notification=True)

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
    await bot.send_message(MY_IDs[2][0], f'📝 #new_chat_title\nID: {chatId}\nNew: {title}\nOld: {TOP10_CHAT_NAMES.get(str(chatId))}', disable_notification=True)
    TOP10_CHAT_NAMES.update({str(chatId): str(title)})
    await sleep(1)
    await bot.send_message(chatId, f'📝 *Updated chat title in rank list\!*\n\nFor top\-10 chats: /chatranking\nFor any query, ask \@CrocodileGamesGroup',
                           parse_mode='MarkdownV2', disable_notification=True)

# Handler for incoming media (if AI is enabled for chat/user) -------------------------------------- #
@bot.message_handler(content_types=['photo', 'video', 'audio', 'voice'], func=lambda msg: msg.chat.type in ['supergroup', 'group'])
async def handle_media_ai(message):
    await handle_group_media(message) # Setting up STATE for chat
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        userObj = message.from_user
        userId = userObj.id
        rplyMsg = message.reply_to_message
        contentType = message.content_type
        if userId in BLOCK_USERS:
            return
        isAiUser = ((str(userId) in AI_USERS.keys()) and (chatId == int(AI_USERS.get(str(userId)))))
        if ((isAiUser or (chatId in CROCO_CHATS))
            and ((message.caption and message.caption.startswith('@croco')) or (rplyMsg and rplyMsg.from_user.id == MY_IDs[0]))
            ):
            if STATE.get(str(chatId))[0] == WAITING_FOR_WORD and not isAiUser:
                msg = await bot.reply_to(message, '✋🏻 Don\'t blabber! I\'m busy with the game right now!', allow_sending_without_reply=True, disable_notification=True)
                await sleep(15)
                await bot.delete_message(chatId, msg.message_id)
                return
            await bot.send_chat_action(chatId, 'typing')
            usr_name = (''.join(filter(str.isalpha, escName(userObj, 25, 'full')))).strip()
            if usr_name in ['', 'id']: usr_name = 'Member'
            prompt = f'{usr_name}: [content: {contentType}]\n' + message.caption.replace('@croco ', '') if message.caption else f'{usr_name}: [content: {contentType}]'
            if rplyMsg:
                if not rplyMsg.text:
                    await bot.reply_to(message, f'✋🏻 I cannot handle multiple {contentType}s from different users at a moment!', allow_sending_without_reply=True)
                    return
                rply_usr_name = (''.join(filter(str.isalpha, escName(rplyMsg.from_user, 25, 'full')))).strip()
                if rply_usr_name in ['', 'id']: rply_usr_name = 'Another Member'
                rply_usr_name = 'Croco' if rplyMsg.from_user.id == MY_IDs[0] else usr_name if rplyMsg.from_user.id == userId else rply_usr_name
                prompt = f'{rply_usr_name}: {rplyMsg.text}\n\n{prompt}'
            prompt += '\n\nCroco:'
            file = await getFileFromMsgObj(message, message, contentType)
            if file is None: return
            file_bytes, mime_type = file
            aiResp = await funcs.getMediaAIResp(prompt, None, None, file_bytes, mime_type)
            aiResp = aiResp if aiResp != 0 else 'Something went wrong! Please try again later.'
            aiResp = aiResp.replace('Croco:', '', 1).lstrip() if aiResp.startswith('Croco:') else aiResp
            aiResp = escChar(aiResp).replace('\\*\\*', '*').replace('\\`', '`')
            await bot.reply_to(message, aiResp, parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)
        return

# Handler for incoming messages in groups
@bot.message_handler(content_types=['text'], func=lambda message: message.chat.type in ['supergroup', 'group'])
async def handle_group_message(message):
    if message.forward_from or message.forward_from_chat:
        return
    chatId = message.chat.id
    userObj = message.from_user
    userId = userObj.id
    msgText = message.text
    rplyMsg = message.reply_to_message
    if chatId in BLOCK_CHATS or userId in BLOCK_USERS:
        return
    global STATE, CHEAT_RECORD, NO_CHEAT_CHATS, WORD
    state = STATE.get(str(chatId))
    if state is None:
        curr_game = await getCurrGame(chatId, userId)
        if curr_game['status'] == 'not_started':
            STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            return
        else:
            started_at = int(curr_game['started_at'])
            WORD.update({str(chatId): curr_game['data'].word})
            STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, started_at, 'False', False]})
            if int(datetime.now(pytz.timezone('Asia/Kolkata')).timestamp()) - started_at > 43200:
                # Don't send [restart notice] if game started 12 hours ago
                return
            if (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
                return
            await bot.send_message(chatId, f'🔄 *Bot restarted\!*\nAll active games were restored back and will continue running\.', parse_mode='MarkdownV2')
        state = STATE.get(str(chatId))
    
    if state[0] == WAITING_FOR_WORD:
        isLeader = state[1] == userId
        # If leader types sth after starting game, change state[2]; ie. show_changed_word_msg=True
        if isLeader:
            cheat_status = 'Force True' if state[4] == 'Force True' else 'False'
            if (rplyMsg is None) or (rplyMsg and (rplyMsg.from_user.id == MY_IDs[0])):
                STATE.update({str(chatId): [WAITING_FOR_WORD, userId, True, state[3], cheat_status, state[5]]})
            else:
                # When leader replies to any msg, except bot's msg
                STATE.update({str(chatId): [WAITING_FOR_WORD, userId, state[2], state[3], cheat_status, state[5]]})
            if message.via_bot and any(t in msgText.lower() for t in ['whisper message to', 'read the whisper', 'private message to', 'generating whisper']):
                STATE.update({str(chatId): [WAITING_FOR_WORD, userId, STATE.get(str(chatId))[2], STATE.get(str(chatId))[3], 'Force True', STATE.get(str(chatId))[5]]})
                print('\n>>> Whisper message detected! ChatID:', chatId, '| UserID:', userId, '| Bot:', message.via_bot.username)
                return
            state = STATE.get(str(chatId))
        # Check if the message contains the word "Word"
        word = WORD.get(str(chatId))
        if word is None:
            return
        can_show_cheat_msg = state[4]
        if re.search(rf'\b({word})(?=(\w{{1,5}}\b|[.,\/\s]|$))', msgText, re.IGNORECASE) is not None:
            # (regex_pattern) or (((state[2]) and ((int(time.time())-state[3]) < 3600) and (len(msgText) < 80) and (not isLeader) and (can_show_cheat_msg == 'False'))
            #                     and ((await getWordMatchAIResp(word, msgText)) and (STATE.get(str(chatId), [0])[0] == WAITING_FOR_WORD) and (WORD.get(str(chatId), '0') == word)))
            is_cheat_allowed = chatId in NO_CHEAT_CHATS
            if not is_cheat_allowed:
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif not isLeader:
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            points = 1
            fullName = escName(userObj)
            # Check if user is not leader, or if the chat can ignore cheat
            if not isLeader or is_cheat_allowed:
                if is_cheat_allowed and isLeader:
                    return
                if can_show_cheat_msg == 'False' or is_cheat_allowed:
                    await bot.send_message(chatId, f'🎉 [{escChar(fullName)}](tg://user?id={userId}) found the word\! *{word}*',
                                            reply_markup=getInlineBtn('found_word'), parse_mode='MarkdownV2')
                else:
                    await bot.send_message(chatId, f'🚨 [{escChar(fullName)}](tg://user?id={userId}) lost 1💵 for cheating\! *{word}*',
                                            reply_markup=getInlineBtn('found_word'), parse_mode='MarkdownV2')
                    points = -1
                    CHEAT_RECORD[str(chatId)] = CHEAT_RECORD.get(str(chatId), 0) + 1
                await to_thread(removeGame_sql, chatId)
                if points == -1:
                    await to_thread(update_dailystats_sql, datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 1, 1)
            else:
                # Leader revealed the word (stop game and deduct leader's points)
                await stopGame(message, isWordRevealed=True)
                points = -1
            await to_thread(incrementPoints_sql, userId, chatId, points, escName(userObj, 100, 'full'))
    
    if (
        (str(userId) in AI_USERS.keys())
        and (chatId == int(AI_USERS.get(str(userId))))
        and (not message.text.startswith('/'))
        and (message.text.startswith('@croco') or (rplyMsg and (rplyMsg.from_user.id == MY_IDs[0])))
        ):
        if (state[0] == WAITING_FOR_WORD) and (userId not in MY_IDs[1]):
            return
        await bot.send_chat_action(chatId, 'typing')
        supported_media = ['photo', 'video', 'audio', 'voice']
        usr_name = (''.join(filter(str.isalpha, escName(userObj, 25, 'full')))).strip()
        if usr_name in ['', 'id']: usr_name = 'Member'
        prompt = f'{usr_name}: {msgText}'
        rplyToMsg = message
        rplyMsg_contentType = None
        if rplyMsg:
            rplyMsg_contentType = rplyMsg.content_type
            tmp = getPromptForMediaAI(userId, msgText, rplyToMsg, rplyMsg, rplyMsg_contentType, prompt, usr_name, supported_media)
            if tmp is None: return
            rplyToMsg, prompt = tmp
        prompt += '\n\nCroco:'
        # Generate response using AI model and send it to user as a reply to his message
        if rplyMsg and rplyMsg_contentType in supported_media:
            file = await getFileFromMsgObj(message, rplyMsg, rplyMsg_contentType)
            if file is None: return
            file_bytes, mime_type = file
            aiResp = await funcs.getMediaAIResp(prompt, None, None, file_bytes, mime_type)
        else:
            aiResp = await funcs.getAIResp(prompt)
        aiResp = aiResp if aiResp != 0 else 'Something went wrong! Please try again later.'
        aiResp = aiResp.replace('Croco:', '', 1).lstrip() if aiResp.startswith('Croco:') else aiResp
        aiResp = escChar(aiResp).replace('\\*\\*', '*').replace('\\`', '`')
        await bot.reply_to(rplyToMsg, aiResp, parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)
        return

    elif chatId in CROCO_CHATS: # Check if chat is allowed to use Croco AI
        msgText_lwr = msgText.lower()
        if msgText.startswith(('/', '@')) and not msgText_lwr.startswith('@croco'):
            return
        IGNORE_MSGS = [
            ('🎉 ', '❗', '❌ ', '⚠ ', '🚨 ', '🛑 ', '⏳ ', '📊 ', '👤 ', '👥 ', '👋🏻 ', '✋🏻 ', '👉🏻 ', '✅ ', '🐊📖 ', '📖 ',
                '🔄 ', '🤖 ', '🖥 ', '📡 ', '🕵🏻‍♂️ ', '🔍 ', '📝 ', '☑️ ', 'Player stats 📊', 'TOP-25 players 🐊📊', '#req_',
                'TOP-25 players in all groups 🐊📊', 'TOP-10 groups 🐊📊', 'User ', 'Invalid ', 'Something went wrong!', 'Error 0x'),
            (' is explaining the word!', ' refused to lead!')
        ]
        if (rplyMsg) and (
            ((rplyMsg.from_user.id == MY_IDs[0]) and (not rplyMsg.text.startswith(IGNORE_MSGS[0])) and (not rplyMsg.text.endswith(IGNORE_MSGS[1])))
            or (msgText_lwr.startswith('@croco'))
            ):
            if state[0] == WAITING_FOR_WORD and userId not in MY_IDs[1]:
                msg = await bot.reply_to(message, '✋🏻 Don\'t blabber! I\'m busy with the game right now!', allow_sending_without_reply=True, disable_notification=True)
                await sleep(15)
                await bot.delete_message(chatId, msg.message_id)
                return
            await bot.send_chat_action(chatId, 'typing')
            usr_name = (''.join(filter(str.isalpha, escName(userObj, 25, 'full')))).strip()
            if usr_name in ['', 'id']: usr_name = 'Member'
            rplyText = rplyMsg.text
            rplyToMsg = message
            resp = None
            preConvObjList = await to_thread(getCrocoAIConv_sql, chatId, rplyText)
            if preConvObjList:
                preConvObj = preConvObjList[0]
                # get Croco AI resp and then update prompt in DB
                time_diff = int(rplyMsg.date) - int(preConvObj.time)
                if 0 < time_diff < 5:
                    prompt = f'{preConvObj.prompt}\n{usr_name}: {msgText}\nCroco: '
                    resp = (await funcs.getCrocoResp(prompt)).lstrip()
                    await to_thread(updateCrocoAIPrompt_sql, id=preConvObj.id, chat_id=chatId, prompt=str(prompt + resp), isNewConv=False)
                else:
                    rem_prmt_frm_indx = str(preConvObj.prompt).find(rplyText)
                    if rem_prmt_frm_indx == -1:
                        await bot.reply_to(message, f'Something went wrong\!\n*Err:* \#0x604 : Failed to retrieve last conversation\.',
                                                parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)
                        return
                    end_offset_index = rem_prmt_frm_indx + len(rplyText)
                    if end_offset_index == len(preConvObj.prompt):
                        prompt = f'{preConvObj.prompt}\n{usr_name}: {msgText}\nCroco: '
                        resp = (await funcs.getCrocoResp(prompt)).lstrip()
                        await to_thread(updateCrocoAIPrompt_sql, id=preConvObj.id, chat_id=chatId, prompt=str(prompt + resp), isNewConv=False)
                    else:
                        renew_prompt = preConvObj.prompt[:end_offset_index]
                        prompt = f'{renew_prompt}\n{usr_name}: {msgText}\nCroco: '
                        resp = (await funcs.getCrocoResp(prompt)).lstrip()
                        await to_thread(updateCrocoAIPrompt_sql, id=None, chat_id=chatId, prompt=str(prompt + resp), isNewConv=True)
            else:
                supported_media = ['photo', 'video', 'audio', 'voice']
                rply_usr_name = (''.join(filter(str.isalpha, escName(rplyMsg.from_user, 25, 'full')))).strip()
                if rply_usr_name in ['', 'id']: rply_usr_name = 'Another Member'
                rply_usr_name = 'Croco' if rplyMsg.from_user.id == MY_IDs[0] else usr_name if rplyMsg.from_user.id == userId else rply_usr_name
                rplyToMsg = message
                rplyMsg_contentType = rplyMsg.content_type
                prompt = f'{usr_name}: {msgText}'
                tmp = getPromptForMediaAI(userId, msgText, rplyToMsg, rplyMsg, rplyMsg_contentType, prompt, usr_name, supported_media)
                if tmp is None: return
                rplyToMsg, prompt = tmp
                prompt += '\nCroco: '
                if rplyMsg_contentType in supported_media:
                    file = await getFileFromMsgObj(message, rplyMsg, rplyMsg_contentType)
                    if file is None: return
                    file_bytes, mime_type = file
                    resp = await funcs.getMediaAIResp(prompt, None, None, file_bytes, mime_type)
                    resp = resp if resp != 0 else 'Error 0x404: Please try again later!'
                else:
                    resp = (await funcs.getCrocoResp(prompt)).lstrip()
                await to_thread(updateCrocoAIPrompt_sql, id=None, chat_id=chatId, prompt=str(prompt + resp), isNewConv=True)
            aiResp = escChar(resp).replace('\\*\\*', '*').replace('\\`', '`')
            await bot.reply_to(rplyToMsg, aiResp, parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)
        elif any(t in msgText_lwr for t in AI_TRIGGER_MSGS):
            if state[0] == WAITING_FOR_WORD and userId not in MY_IDs[1]:
                return
            await bot.send_chat_action(chatId, 'typing')
            usr_name = (''.join(filter(str.isalpha, escName(userObj, 25, 'full')))).strip()
            if usr_name in ['', 'id']: usr_name = 'Member'
            prompt = f'{usr_name}: {msgText}\nCroco: '
            resp = (await funcs.getCrocoResp(prompt)).lstrip()
            await to_thread(updateCrocoAIPrompt_sql, id=None, chat_id=chatId, prompt=str(prompt + resp), isNewConv=True)
            aiResp = escChar(resp).replace('\\*\\*', '*').replace('\\`', '`')
            await bot.reply_to(message, aiResp, parse_mode='MarkdownV2', allow_sending_without_reply=True, disable_notification=True)

# Handler for incoming media in groups
@bot.message_handler(content_types=['sticker', 'document', 'animation', 'dice', 'poll', 'video_note', 'contact'],
                     func=lambda message: message.chat.type in ['supergroup', 'group'])
async def handle_group_media(message):
    chatId = message.chat.id
    userId = message.from_user.id
    if chatId in BLOCK_CHATS and userId in BLOCK_USERS:
        return
    # print(message.content_type)
    # with open('sentMsg.json', 'w') as f:
    #     f.write(str(message).replace('\'', '\"').replace('None', 'null').replace('True', 'true').replace('False', 'false'))
    global STATE
    state = STATE.get(str(chatId))
    if state is None:
        curr_game = await getCurrGame(chatId, userId)
        if curr_game['status'] == 'not_started':
            STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
        else:
            started_at = int(curr_game['started_at'])
            WORD.update({str(chatId): curr_game['data'].word})
            STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, started_at, 'False', False]})
            if int(datetime.now(pytz.timezone('Asia/Kolkata')).timestamp()) - started_at > 43200:
                # Don't send [restart notice] if game started 12 hours ago
                return
            if (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
                return
            await bot.send_message(chatId, f'🔄 *Bot restarted\!*\nAll active games were restored back and will continue running\.', parse_mode='MarkdownV2')
    elif state[0] == WAITING_FOR_WORD and state[1] == userId:
        cheat_status = 'Force True' if state[4] == 'Force True' else 'False'
        STATE.update({str(chatId): [WAITING_FOR_WORD, userId, state[2], state[3], cheat_status, state[5]]})



# Callbacks handler for inline buttons --------------------------------------------------------- #

@bot.callback_query_handler(func=lambda call: True)
async def handle_query(call):
    chatId = call.message.chat.id
    userObj = call.from_user
    if chatId not in BLOCK_CHATS:
        if userObj.id in BLOCK_USERS:
            await bot.answer_callback_query(call.id, '❌ You were banned from using this bot due to a violation of our Terms of Service.' \
                                            '\n\nFor queries, join: @CrocodileGamesGroup', show_alert=True, cache_time=30)
            return
        # try: # Disabled for best performance
        #     if (await bot.get_chat_member(chatId, MY_IDs[0])).can_send_messages == False:
        #         await bot.answer_callback_query(call.id, '❌ Bot was muted by chat admin!', show_alert=True, cache_time=5)
        #         return
        # except:
        #     await bot.answer_callback_query(call.id, '❌ Bot was removed from this chat!', show_alert=True, cache_time=10)
        #     return
        # Schedule bot mute for EVS group
        # if chatId == -1001596465392:
        #     now = datetime.now(pytz.timezone('Asia/Kolkata'))
        #     if not (now.time() >= datetime.time(datetime.strptime('23:30:00', '%H:%M:%S')) or \
        #     now.time() <= datetime.time(datetime.strptime('09:00:00', '%H:%M:%S'))):
        #         await bot.answer_callback_query(call.id, f"❗ Game will be available for play daily from 11:30 PM to 9:00 AM IST.", show_alert=True)
        #         return
        global STATE
        curr_game = await getCurrGame(chatId, userObj.id)
        curr_status = curr_game['status']
        state = STATE.get(str(chatId))
        if state is None:
            if curr_status == 'not_started':
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            else:
                started_at = int(curr_game['started_at'])
                WORD.update({str(chatId): curr_game['data'].word})
                STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, started_at, 'False', False]})
                if int(datetime.now(pytz.timezone('Asia/Kolkata')).timestamp()) - started_at > 43200:
                    # Don't send [restart notice] if game started 12 hours ago
                    return
                await bot.send_message(chatId, f'🔄 *Bot restarted\!*\nAll active games were restored back and will continue running\.', parse_mode='MarkdownV2')
        elif curr_status != 'not_started' and state[0] == WAITING_FOR_COMMAND:
            # STATE is not synced with curr_status
            WORD.update({str(chatId): curr_game['data'].word})
            STATE.update({str(chatId): [WAITING_FOR_WORD, int(curr_game['data'].leader_id), True, int(curr_game['started_at']), 'False', False]})

        # Game panel inline btn handlers for leader use cases only ---------------- #
        if call.data == 'change_word':
            if curr_status == 'leader':
                new_word = await funcs.getNewWord()
                await bot.answer_callback_query(call.id, f"Word: {new_word}", show_alert=True)
                last_word = WORD.get(str(chatId), '')
                WORD.update({str(chatId): new_word})
                await changeWord(call, last_word)
                STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(curr_game['started_at']), 'True', STATE.get(str(chatId))[5]]})
            elif curr_status == 'not_leader':
                await bot.answer_callback_query(call.id, '⚠ Only leader can change the word!', show_alert=True, cache_time=30)
            else:
                await bot.answer_callback_query(call.id, '⚠ Game has not started yet!', show_alert=True, cache_time=5)
        elif call.data == 'see_word':
            if curr_status == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True, cache_time=5)
            elif curr_status == 'not_leader' and userObj.id != MY_IDs[1][0]:
                await bot.answer_callback_query(call.id, "⚠ Only leader can see the word!", show_alert=True, cache_time=30)
            else:
                word = WORD.get(str(chatId), '[Change this word] ❌')
                await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
        elif call.data == 'generate_hints':
            if curr_status == 'not_started':
                await bot.answer_callback_query(call.id, "⚠ Game has not started yet!", show_alert=True, cache_time=5)
            elif curr_status == 'not_leader':
                await bot.answer_callback_query(call.id, "⚠ Ask to leader for hints!", show_alert=True, cache_time=30)
            else:
                global HINTS
                if WORD.get(str(chatId)) is None:
                    HINTS.update({str(chatId): ['❌ Error: Change this word or restart the game!']})
                elif not (HINTS.get(str(chatId)) is not None and len(HINTS.get(str(chatId))) > 0):
                    HINTS.update({str(chatId): await funcs.getHints(WORD.get(str(chatId)))})
                await bot.answer_callback_query(call.id, f"{HINTS.get(str(chatId))[0]}\n\n❕ You are free to use your own customised hints!", show_alert=True)
                HINTS.get(str(chatId)).pop(0)
        elif call.data == 'drop_lead':
            if curr_status == 'leader':
                await stopGame(call, isRefused=True, word=(f' *~{WORD.get(str(chatId))}~*' if STATE.get(str(chatId))[2] else ''))
                await bot.delete_message(chatId, call.message.message_id)
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_status == 'not_leader':
                await bot.answer_callback_query(call.id, '⚠ You are not leading the game!', show_alert=True, cache_time=30)
            else:
                await bot.answer_callback_query(call.id, '⚠ Game has not started yet!', show_alert=True, cache_time=5)

        # Inline btn handlers for all general use cases
        elif call.data == 'start_game': # User start new game from "XYZ found the word! **WORD**"
            if curr_status == 'not_started':
                word = await startGame(call)
                if word is not None:
                    try:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                    except:
                        pass
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), 'True', False]})
                    await to_thread(update_dailystats_sql, datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_status == 'not_leader':
                isNewPlyr = (await to_thread(getUserPoints_sql, userObj.id)) is None
                started_from = int(time.time() - curr_game['started_at'])
                if (started_from > 30 and not isNewPlyr) or (started_from > 600):
                    if STATE.get(str(chatId))[5]:
                        await bot.answer_callback_query(call.id, '⚠ Do not blabber! Someone else is going to lead the game next.', show_alert=True)
                        return
                    fullname = escName(userObj)
                    rmsg = await bot.send_message(chatId, f'⏳ *{escChar(fullname)}* want to lead the game\!\nIn `5` seconds\.\.\.',
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
                            ico = '✅' if i == 5 else '⌛' if i&1 else '⏳'
                            await bot.edit_message_text(f'{ico} *{escChar(fullname)}* want to lead the game\!\nIn `{5 - i}` seconds\.\.\.',
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
                        await to_thread(update_dailystats_sql, datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)
                    else:
                        STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                else:
                    await bot.answer_callback_query(call.id, "⚠ Do not blabber! Game has already started by someone else.", show_alert=True)
            else:
                await bot.answer_callback_query(call.id, "⚠ Game has already started by you!", show_alert=True)
        elif call.data == 'start_game_from_refuse': # User start new game from "XYZ refused to lead!"
            if curr_status == 'not_started':
                word = await startGame(call)
                if word is not None:
                    try:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        await bot.delete_message(chatId, call.message.message_id)
                    except:
                        pass
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False, int(time.time()), 'True', False]})
                    await to_thread(update_dailystats_sql, datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_status == 'not_leader':
                isNewPlyr = (await to_thread(getUserPoints_sql, userObj.id)) is None
                started_from = int(time.time() - curr_game['started_at'])
                if (started_from > 30 and not isNewPlyr) or (started_from > 600):
                    if STATE.get(str(chatId))[5]:
                        await bot.answer_callback_query(call.id, '⚠ Do not blabber! Someone else is going to lead the game next.', show_alert=True)
                        return
                    fullname = escName(userObj)
                    rmsg = await bot.send_message(chatId, f'⏳ *{escChar(fullname)}* want to lead the game\!\nIn `5` seconds\.\.\.',
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
                            ico = '✅' if i == 5 else '⌛' if i&1 else '⏳'
                            await bot.edit_message_text(f'{ico} *{escChar(fullname)}* want to lead the game\!\nIn `{5 - i}` seconds\.\.\.',
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
                        await to_thread(update_dailystats_sql, datetime.now(pytz.timezone('Asia/Kolkata')).date().isoformat(), 0, 1)
                    else:
                        STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
                else:
                    await bot.answer_callback_query(call.id, "⚠ Do not blabber! Game has already started by someone else.", show_alert=True)
            else:
                await bot.answer_callback_query(call.id, "⚠ Game has already started by you!", show_alert=True)

        elif call.data == 'ludo':
            await bot.answer_callback_query(call.id, url='https://t.me/CrocodileGameEnn_bot?game=ludo')
        elif call.data == 'ranking_list_findMe_currChat':
            user_stats = await to_thread(getTop25Players_sql, chatId, 2000)
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
                grp_player_ranks = await to_thread(getTop25PlayersInAllChats_sql)
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
                            if await funcs.addNewWord(wd):
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
                await bot.send_message(MY_IDs[2][0], f'✅ All words added to dictionary\!\n\n🔔 *Notice sent \(times\):* `{cnt}`', parse_mode='MarkdownV2', allow_sending_without_reply=True)
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
                if userObj.id not in MY_IDs[1] and userObj.id == STATE.get(str(chatId))[1]:
                    await bot.answer_callback_query(call.id, '❌ Only the requester and other participants can undo this action!', show_alert=True, cache_time=5)
                    return
                STATE[str(chatId)][5] = False
                await sleep(0.1)
                msg = '❌ ~' + escChar(call.message.text.split("\n")[0][2:]) + f'~\n\-\> Cancelled by *{escChar(escName(userObj))}*'
                await bot.edit_message_text(msg, chatId, call.message.message_id, parse_mode='MarkdownV2')
            else:
                await bot.answer_callback_query(call.id, '❌ Request was expired!', cache_time=30)

# Start the bot
try:
    print('[PROD] Bot is running...')
    asyncio.run(bot.infinity_polling())
except BaseException as e:
    print('\n[PROD] Bot stopped!\nCaused by:', e.__repr__())
