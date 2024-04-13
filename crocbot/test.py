import os
import time
import requests
import funcs
import asyncio
from asyncio import sleep
from telebot.async_telebot import AsyncTeleBot

bot = AsyncTeleBot('5418430180:AAG4iOSP8XIuyiqrQ2Jgc3f9AxIi4DCm5n83')

# Listen for incoming messages (private)
@bot.message_handler(content_types=['photo'])
async def private_message(message):
    # Check if message contains an image
    if message.photo:
        file_id = message.photo[-1].file_id
        file_info = await bot.get_file(file_id)
        file_path = file_info.file_path
        photo = f"https://api.telegram.org/file/bot{os.getenv('BOT_TOKEN')}/{file_path}"
        await bot.send_message(message.chat.id, f"You sent an image! {photo}")

@bot.message_handler(commands=['start'])
async def start(message):
    await bot.send_message(message.chat.id, "Hello, world!")

@bot.message_handler(commands=['send'])
async def send_message_to_chats(message):
    if message.reply_to_message is None:
        await bot.reply_to(message, 'Please reply to a message to forward.')
        return
    chat_ids = []
    err_msg = []
    if message.text.strip() == '/send *':
        # Forward to all chats from your database
        chat_ids = get_chat_ids_from_database()  # Replace with your database logic to fetch chat IDs
    else:
        # Forward to specified chat IDs
        command_parts = message.text.split(' ', 2)
        if len(command_parts) > 2 and command_parts[1] == '-id':
            chat_ids_str = command_parts[2]
            chat_ids = [int(chat_id.strip()) for chat_id in chat_ids_str.split(',') if chat_id.strip().lstrip('-').isdigit()]
    if len(chat_ids) == 0:
        await bot.reply_to(message, 'Invalid command format. Please specify valid chat IDs.')
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


print("[TEST] Bot is running...")
asyncio.run(bot.infinity_polling())
