import os
import time
import asyncio
from asyncio import sleep
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import funcs
from sql_helper.current_running_game_sql import addGame_sql, getGame_sql, removeGame_sql
from sql_helper.rankings_sql import incrementPoints_sql, getUserPoints_sql, getTop25Players_sql, getTop25PlayersInAllChats_sql, getTop10Chats_sql
from sql_helper.ai_conv_sql import getAllConv_sql, updateEngAIPrompt_sql

BOT_TOKEN = os.environ.get('BOT_TOKEN', None)
MY_IDs = [5321125784, 6103212777] # My ID, and Bot ID
AI_USERS = {}
BLOCK_CHATS = [int(x) for x in os.environ.get('BLOCK_CHATS', '').split(',') if x]
CROCO_CHATS = [int(x) for x in os.environ.get('CROCO_CHATS', '').split(',') if x]
STATE = {} # STATE('chat_id': [str(game_state), int(leader_id), bool(show_changed_word_msg)])
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
        markup.add(
            InlineKeyboardButton('See word', callback_data='see_word'),
            InlineKeyboardButton('Generate hints', callback_data='generate_hints'),
            InlineKeyboardButton('Change word', callback_data='change_word'),
            InlineKeyboardButton('Drop lead', callback_data='drop_lead')
        )
    elif event == 'found_word':
        markup.row_width = 1
        markup.add(InlineKeyboardButton('Start new game!', callback_data='start_game'))
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
    await bot.send_message(chatId, f'*[{funcs.escChar(userObj.first_name)}](tg://user?id={userObj.id}) is explaining the word\!*', reply_markup=getInlineBtn('leading'), parse_mode='MarkdownV2')
    return WORD.get(str(chatId))

async def stopGame(message, isRefused=False, isChangeLeader=False, isWordRevealed=False):
    # Stop game if user is admin or leader
    try:
        chatId = message.chat.id
    except:
        chatId = message.message.chat.id
    userObj = message.from_user
    if isRefused:
        await bot.send_message(chatId, f'{funcs.escChar(userObj.first_name)} refused to lead!', reply_markup=getInlineBtn('refused_lead'))
    elif isChangeLeader:
        # If game started more than 30 seconds, allow others to change leader
        pass
    elif isWordRevealed:
        # Leader revealed the word (deduct point)
        await bot.send_message(chatId, f'🛑 *Game stopped\!*\n[{funcs.escChar(userObj.first_name)}](tg://user?id={userObj.id}) \(\-1💵\) revealed the word: *{WORD.get(str(chatId))}*', reply_markup=getInlineBtn('refused_lead'), parse_mode='MarkdownV2')
    else:
        chatMemb_obj = await bot.get_chat_member(chatId, userObj.id)
        curr_game = await getCurrGame(chatId, userObj.id)
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
    global STATE
    # Save word to database and return (leader changed the word)
    try:
        HINTS.get(str(chatId)).pop()
    except:
        pass
    WORD.update({str(chatId): funcs.getNewWord()})
    addGame_sql(chatId, user_obj.id, WORD.get(str(chatId)))
    if (STATE.get(str(chatId))[0] == WAITING_FOR_COMMAND) or (STATE.get(str(chatId))[0] == WAITING_FOR_WORD and STATE.get(str(chatId))[2]):
        await bot.send_message(chatId, f"❗ {funcs.escChar(user_obj.first_name)} changed the word\!", parse_mode='MarkdownV2')
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
@bot.message_handler(commands=['start'])
async def start_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        await bot.send_message(chatId, '👋 Hey!\nI\'m Crocodile Game Bot. To start a game, use command: /game')

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
        global STATE
        if await startGame(message, isStartFromCmd=True) is not None:
            STATE.update({str(chatId): [WAITING_FOR_WORD, userId, False]})

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
        user_stats = getUserPoints_sql(user_obj.id, chatId)
        if user_stats is None:
            await bot.send_message(chatId, '📊 You have no stats yet!')
        else:
            fullName = user_obj.first_name
            if user_obj.last_name is not None:
                fullName += ' ' + user_obj.last_name
            rank = ''
            grank = ''
            await bot.send_message(chatId, f'*Player stats* 📊\n\n'
                                    f'*Name:* {funcs.escChar(fullName)}\n'
                                    f'*Earned cash:* {str(user_stats.points)} 💵\n'
                                    f' *— in all chats:* {str(user_stats.points)} 💵\n'
                                    f'*Rank:* \#{rank}\n'
                                    f'*Global rank:* \#{grank}\n\n'
                                    f'❕ _You receive 1💵 reward for\neach correct word guess\._',
                                    parse_mode='MarkdownV2')

@bot.message_handler(commands=['ranking'])
async def ranking_cmd(message):
    chatId = message.chat.id
    if chatId not in BLOCK_CHATS:
        grp_player_ranks = getTop25Players_sql(chatId)
        if grp_player_ranks is None:
            await bot.send_message(chatId, '📊 No player\'s rank determined yet for this group!')
        else:
            i = 1
            ranksTxt = ''
            for gprObj in grp_player_ranks:
                ranksTxt += f'*{i}\.* {funcs.escChar(gprObj.name)} — {gprObj.points} 💵\n'
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
            ranks = sorted(ranks.values(), key=lambda x: x['points'], reverse=True)
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
                ranksTxt += f"{i} {funcs.escChar(user['name'])} — {user['points']} 💵\n"
                i = j
            await bot.send_message(chatId, f'*TOP\-25 players in all groups* 🐊📊\n\n{ranksTxt}', parse_mode='MarkdownV2')

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
                STATE.update({str(chatId): [WAITING_FOR_WORD, userId, True]})
            # Check if the message contains the word "Word"
            if message.text.lower() == WORD.get(str(chatId)):
                # Check if user is not leader
                curr_game = await getCurrGame(chatId, userId)
                if curr_game['status'] == 'not_leader':
                    # Someone guessed the word (delete word from database)
                    fullName = userObj.first_name
                    if userObj.last_name is not None:
                        fullName += ' ' + userObj.last_name
                    removeGame_sql(chatId)
                    await bot.send_message(chatId, f'🎉 [{funcs.escChar(userObj.first_name)}](tg://user?id={userId}) found the word\! *{WORD.get(str(chatId))}*', reply_markup=getInlineBtn('found_word'), parse_mode='MarkdownV2')
                    incrementPoints_sql(userId, chatId, fullName)
                elif curr_game['status'] == 'not_started':
                    pass
                elif curr_game['status'] == 'leader':
                    # Leader revealed the word (stop game and deduct leader's points)
                    await stopGame(message, isWordRevealed=True)
                STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
        
        elif chatId in CROCO_CHATS: # Check if chat is allowed to use Croco English AI
            if (rplyMsg is not None) and (rplyMsg.from_user.id == MY_IDs[1]) and (rplyMsg.text.startswith('Croco: ')) and not (msgText.startswith('/') or msgText.startswith('@')):
                rplyText = rplyMsg.text
                resp = None
                preConvObj = getAllConv_sql(chatId)
                foundPreConv = False
                if preConvObj is not None and preConvObj.prompts is not None and (str(preConvObj.prompts).find(rplyText) != -1):
                    foundPreConv = True
                    # get Croco English AI resp and then update prompt in DB
                    p = f"{preConvObj.prompts}\nMember 4: {msgText}\nCroco:"
                    resp = funcs.escChar(funcs.getCrocoResp(p))
                    updateEngAIPrompt_sql(id=preConvObj.id, chat_id=chatId, prompt=str(p + resp), isNewConv=False)
                if not foundPreConv:
                    p = f"{funcs.ENG_AI_PRE_PROMPT}\n- Another conversation -\n...\n{rplyText}\nMember 4: {msgText}\nCroco:"
                    resp = funcs.escChar(funcs.getCrocoResp(p))
                    updateEngAIPrompt_sql(id=None, chat_id=chatId, prompt=str(p + resp), isNewConv=True)
                await bot.send_message(chatId, f'*Croco:* {resp}', reply_to_message_id=message.message_id, parse_mode='MarkdownV2')
            elif any(t in msgText.lower() for t in funcs.ENG_AI_TRIGGER_MSGS):
                p = f"{funcs.ENG_AI_PRE_PROMPT}\nMember 4: {msgText}\nCroco:"
                resp = funcs.escChar(funcs.getCrocoResp(p))
                updateEngAIPrompt_sql(id=None, chat_id=chatId, prompt=str(p + resp), isNewConv=True)
                await bot.send_message(chatId, f'*Croco:* {resp}', reply_to_message_id=message.message_id, parse_mode='MarkdownV2')



# Callbacks handler for inline buttons ---------------------------------------- #
@bot.callback_query_handler(func=lambda call: True)
async def handle_query(call):
    chatId = call.message.chat.id
    userObj = call.from_user
    if chatId not in BLOCK_CHATS:
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
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False]})
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False]})
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
                    STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False]})
                else:
                    STATE.update({str(chatId): [WAITING_FOR_COMMAND]})
            elif curr_game['status'] == 'not_leader':
                if int(time.time()) - curr_game['started_at'] > 30:
                    # If game started more than 30 seconds ago, then another user can restart the game taking leader's place
                    await stopGame(call, isChangeLeader=True)
                    word = await startGame(call)
                    if word is not None:
                        await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                        STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False]})
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
                word = await changeWord(call)
                await bot.answer_callback_query(call.id, f"Word: {word}", show_alert=True)
                STATE.update({str(chatId): [WAITING_FOR_WORD, userObj.id, False]})
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
