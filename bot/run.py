from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters.command import Command, CommandStart
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from func.interactions import *
import asyncio
import traceback
import io
import base64
import sys
import logging
import json
import os
import signal
from pathlib import Path
import random
from func.db_queries import *

# Disable watchdog debug logging
logging.getLogger('watchdog').setLevel(logging.WARNING)

bot = Bot(token=token)
dp = Dispatcher()
start_kb = InlineKeyboardBuilder()
settings_kb = InlineKeyboardBuilder()

start_kb.row(
    types.InlineKeyboardButton(text="ℹ️ About", callback_data="about"),
    types.InlineKeyboardButton(text="⚙️ Settings", callback_data="settings"),
    types.InlineKeyboardButton(text="📝 Register", callback_data="register"),
)
settings_kb.row(
    types.InlineKeyboardButton(text="🔄 Switch LLM", callback_data="switchllm"),
    types.InlineKeyboardButton(text="🗑️ Delete LLM", callback_data="delete_model"),
)
settings_kb.row(
    types.InlineKeyboardButton(text="📋 Select System Prompt", callback_data="select_prompt"),
    types.InlineKeyboardButton(text="🗑️ Delete System Prompt", callback_data="delete_prompt"), 
)
settings_kb.row(
    types.InlineKeyboardButton(text="📋 List Users and remove User", callback_data="list_users"),
)

commands = [
    types.BotCommand(command="start", description="Start"),
    types.BotCommand(command="reset", description="Reset Chat"),
    types.BotCommand(command="history", description="Look through messages"),
    types.BotCommand(command="pullmodel", description="Pull a model from Ollama"),
    types.BotCommand(command="addglobalprompt", description="Add a global prompt"),
    types.BotCommand(command="addprivateprompt", description="Add a private prompt"),
    types.BotCommand(command="temp", description="Set Temperature"),
]

class ActiveChats:
    def __init__(self):
        self._active_chats = {}
        self._lock = asyncio.Lock()

    async def get(self, chat_key):
        async with self._lock:
            return self._active_chats.get(chat_key)

    async def set(self, chat_key, value):
        async with self._lock:
            self._active_chats[chat_key] = value

    async def pop(self, chat_key):
        async with self._lock:
            return self._active_chats.pop(chat_key, None)

    async def contains(self, chat_key):
        async with self._lock:
            return chat_key in self._active_chats
        
    async def get_all(self):
        async with self._lock:
            return self._active_chats.copy()
        
    async def set_all(self, new_chats):
        async with self._lock:
            self._active_chats = new_chats

    async def update_message(self, chat_key, role, content):
         async with self._lock:
            if chat_key in self._active_chats:
                self._active_chats[chat_key]["messages"].append({"role": role, "content": content})

    async def update_model(self, chat_key, model_name):
        async with self._lock:
            if chat_key in self._active_chats:
                self._active_chats[chat_key]["model"] = model_name

    async def update_temperature(self, chat_key, temperature):
        async with self._lock:
            if chat_key in self._active_chats:
                self._active_chats[chat_key]["temperature"] = temperature

    async def update_selected_prompt_id(self, chat_key, selected_prompt_id):
        async with self._lock:
            if chat_key in self._active_chats:
                self._active_chats[chat_key]["selected_prompt_id"] = selected_prompt_id

    async def initialize_chat(self, chat_key, modelname, default_temperature, selected_prompt_id):
        async with self._lock:
            if chat_key not in self._active_chats:
                self._active_chats[chat_key] = {
                    "model": modelname,
                    "messages": [],
                    "stream": True,
                    "temperature": default_temperature,
                    "selected_prompt_id": selected_prompt_id
                }

ACTIVE_CHATS = ActiveChats()

modelname = os.getenv("INITMODEL")
mention = None
selected_prompt_id = None  # Variable to store the selected prompt ID
CHAT_TYPE_GROUP = "group"
CHAT_TYPE_SUPERGROUP = "supergroup"

timeout = os.getenv("TIMEOUT", "3000")
global DEFAULT_TEMPERATURE
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
if log_level_str not in log_levels:
    log_level = logging.DEBUG
else:
    log_level = logging.getLevelName(log_level_str)

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(init_db_query)
    c.execute(create_users_table_query)
    c.execute(create_chats_table_query)
    c.execute(create_system_prompts_table_query)
    c.execute(create_global_settings_table_query)
    c.execute(create_active_chat_contexts_table_query)

    # Initialize global settings if not exist
    c.execute(select_count_global_settings_query)
    if c.fetchone()[0] == 0:
        c.execute(insert_global_settings_query, (modelname, selected_prompt_id))
    conn.commit()
    conn.close()

def register_user(user_id, user_name):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(insert_or_replace_users_query, (user_id, user_name))
    conn.commit()
    conn.close()

def save_chat_message(user_id, role, content):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(insert_chats_query,
              (user_id, role, content))
    conn.commit()
    conn.close()

@dp.callback_query(lambda query: query.data == "register")
async def register_callback_handler(query: types.CallbackQuery):
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    register_user(user_id, user_name)
    await query.answer("You have been registered successfully!")

async def get_bot_info():
    global mention
    if mention is None:
        get = await bot.get_me()
        mention = f"@{get.username}"
    return mention

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    start_message = f"Welcome, <b>{message.from_user.full_name}</b>!"
    await message.answer(
        start_message,
        parse_mode=ParseMode.HTML,
        reply_markup=start_kb.as_markup(),
        disable_web_page_preview=True,
    )

@dp.message(Command("reset"))
async def command_reset_handler(message: Message) -> None:
    if message.from_user.id in allowed_ids:
        if await ACTIVE_CHATS.contains(message.from_user.id):
            await ACTIVE_CHATS.pop(message.from_user.id)
            logging.info(f"Chat has been reset for {message.from_user.first_name}")
            await bot.send_message(
                chat_id=message.chat.id,
                text="Chat has been reset",
            )

@dp.message(Command("history"))
async def command_get_context_handler(message: Message) -> None:
    if message.from_user.id in allowed_ids:
        chat_key = get_chat_key(message)
        if await ACTIVE_CHATS.contains(chat_key):
            messages = (await ACTIVE_CHATS.get(chat_key))["messages"]
            context = ""
            for msg in messages:
                context += f"*{msg['role'].capitalize()}*: {msg['content']}\n"
            await bot.send_message(
                chat_id=message.chat.id,
                text=context,
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await bot.send_message(
                chat_id=message.chat.id,
                text="No chat history available for this user",
            )

@dp.message(Command("addglobalprompt"))
async def add_global_prompt_handler(message: Message):
    prompt_text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None  # Get the prompt text from the command arguments
    if prompt_text:
        add_system_prompt(message.from_user.id, prompt_text, True)
        await message.answer("Global prompt added successfully.")
    else:
        await message.answer("Please provide a prompt text to add.")

@dp.message(Command("addprivateprompt"))
async def add_private_prompt_handler(message: Message):
    prompt_text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None  # Get the prompt text from the command arguments
    if prompt_text:
        add_system_prompt(message.from_user.id, prompt_text, False)
        await message.answer("Private prompt added successfully.")
    else:
        await message.answer("Please provide a prompt text to add.")

@dp.message(Command("pullmodel"))
async def pull_model_handler(message: Message) -> None:
    model_name = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None  # Get the model name from the command arguments
    logging.info(f"Downloading {model_name}")
    if model_name:
        response = await manage_model("pull", model_name)
        if response.status == 200:
            await message.answer(f"Model '{model_name}' is being pulled.")
        else:
            await message.answer(f"Failed to pull model '{model_name}': {response.reason}")
    else:
        await message.answer("Please provide a model name to pull.")

@dp.callback_query(lambda query: query.data == "settings")
async def settings_callback_handler(query: types.CallbackQuery):
    await bot.send_message(
        chat_id=query.message.chat.id,
        text=f"Choose the right option.",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=settings_kb.as_markup()
    )

@dp.callback_query(lambda query: query.data == "switchllm")
async def switchllm_callback_handler(query: types.CallbackQuery):
    models = await model_list()
    switchllm_builder = InlineKeyboardBuilder()
    for model in models:
        modelname = model["name"]
        modelfamilies = ""
        if model["details"]["families"]:
            modelicon = {"llama": "🦙", "clip": "📷"}
            try:
                modelfamilies = "".join(
                    [modelicon[family] for family in model["details"]["families"]]
                )
            except KeyError as e:
                modelfamilies = f"✨"
        switchllm_builder.row(
            types.InlineKeyboardButton(
                text=f"{modelname} {modelfamilies}", callback_data=f"model_{modelname}"
            )
        )
    await query.message.edit_text(
        f"{len(models)} models available.\n🦙 = Regular\n🦙📷 = Multimodal", reply_markup=switchllm_builder.as_markup(),
    )
    save_global_settings_to_db()

@dp.callback_query(lambda query: query.data.startswith("model_"))
async def model_callback_handler(query: types.CallbackQuery):
    global modelname
    global modelfamily
    modelname = query.data.split("model_")[1]
    await query.answer(f"Chosen model: {modelname}")
    save_global_settings_to_db()

@dp.callback_query(lambda query: query.data == "about")
@perms_admins
async def about_callback_handler(query: types.CallbackQuery):
    dotenv_model = os.getenv("INITMODEL")
    global modelname
    global selected_prompt_id
    global DEFAULT_TEMPERATURE

    # Fetch the selected prompt name
    selected_prompt_name = "None"
    if selected_prompt_id is not None:
        prompts = get_system_prompts(user_id=query.from_user.id, is_global=None)
        for prompt in prompts:
            if prompt[0] == selected_prompt_id:
                selected_prompt_name = prompt[2]  # prompt[2] is the prompt text
                break

    # Get the current chat key
    chat_key = get_chat_key(query.message)

    # Fetch current temperature for the chat
    current_temperature = DEFAULT_TEMPERATURE  # Default value
    chat_data = await ACTIVE_CHATS.get(chat_key)
    if chat_data:
        current_temperature = chat_data.get("temperature", DEFAULT_TEMPERATURE)

    await bot.send_message(
        chat_id=query.message.chat.id,
        text=f"""<b><u>Bot Info</u></b>

<b>Current Model:</b> <code>{modelname}</code>
<b>Default Model (.env):</b> <code>{dotenv_model}</code>

<b>Selected Prompt:</b> <code>{selected_prompt_name}</code>
<b>Current Temperature:</b> <code>{current_temperature}</code>

This project is under <a href='https://github.com/ruecat/ollama-telegram/blob/main/LICENSE'>MIT License.</a>
<a href='https://github.com/ruecat/ollama-telegram'>Source Code</a>""",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

@dp.callback_query(lambda query: query.data == "list_users")
@perms_admins
async def list_users_callback_handler(query: types.CallbackQuery):
    users = get_all_users_from_db()
    user_kb = InlineKeyboardBuilder()
    for user_id, user_name in users:
        user_kb.row(types.InlineKeyboardButton(text=f"{user_name} ({user_id})", callback_data=f"remove_{user_id}"))
    user_kb.row(types.InlineKeyboardButton(text="Cancel", callback_data="cancel_remove"))
    await query.message.answer("Select a user to remove:", reply_markup=user_kb.as_markup())

@dp.callback_query(lambda query: query.data.startswith("remove_"))
@perms_admins
async def remove_user_from_list_handler(query: types.CallbackQuery):
    user_id = int(query.data.split("_")[1])
    if remove_user_from_db(user_id):
        await query.answer(f"User {user_id} has been removed.")
        await query.message.edit_text(f"User {user_id} has been removed.")
    else:
        await query.answer(f"User {user_id} not found.")

@dp.callback_query(lambda query: query.data == "cancel_remove")
@perms_admins
async def cancel_remove_handler(query: types.CallbackQuery):
    await query.message.edit_text("User removal cancelled.")

@dp.callback_query(lambda query: query.data == "select_prompt")
async def select_prompt_callback_handler(query: types.CallbackQuery):
    prompts = get_system_prompts(user_id=query.from_user.id)
    prompt_kb = InlineKeyboardBuilder()
    for prompt in prompts:
        prompt_id, _, prompt_text, _, _ = prompt
        prompt_kb.row(
            types.InlineKeyboardButton(
                text=prompt_text, callback_data=f"prompt_{prompt_id}"
            )
        )
    await query.message.edit_text(
        f"{len(prompts)} system prompts available.", reply_markup=prompt_kb.as_markup()
    )
    save_global_settings_to_db()

    all_chats = await ACTIVE_CHATS.get_all()
    for chat_key in all_chats:
        await ACTIVE_CHATS.update_selected_prompt_id(chat_key, selected_prompt_id)

@dp.callback_query(lambda query: query.data.startswith("prompt_"))
async def prompt_callback_handler(query: types.CallbackQuery):
    global selected_prompt_id
    prompt_id = int(query.data.split("prompt_")[1])
    selected_prompt_id = prompt_id
    save_global_settings_to_db()

    # Fetch the selected prompt text from the database
    prompts = get_system_prompts(user_id=query.from_user.id)
    selected_prompt_name = "Unknown Prompt"  # Default value if prompt not found
    for prompt in prompts:
        if prompt[0] == prompt_id:
            selected_prompt_name = prompt[2]  # prompt[2] is the prompt text
            break

    # Truncate the prompt name for the answer.  Keep it short!
    truncated_prompt_name = (selected_prompt_name[:50] + '...') if len(selected_prompt_name) > 50 else selected_prompt_name
    await query.answer(f"Prompt '{truncated_prompt_name}' selected!", show_alert=True)

    all_chats = await ACTIVE_CHATS.get_all()
    for chat_key in all_chats:
        await ACTIVE_CHATS.update_selected_prompt_id(chat_key, selected_prompt_id)

@dp.callback_query(lambda query: query.data == "delete_prompt")
async def delete_prompt_callback_handler(query: types.CallbackQuery):
    prompts = get_system_prompts(user_id=query.from_user.id)
    delete_prompt_kb = InlineKeyboardBuilder()
    for prompt in prompts:
        prompt_id, _, prompt_text, _, _ = prompt
        delete_prompt_kb.row(
            types.InlineKeyboardButton(
                text=prompt_text, callback_data=f"delete_prompt_{prompt_id}"
            )
        )
    await query.message.edit_text(
        f"{len(prompts)} system prompts available for deletion.", reply_markup=delete_prompt_kb.as_markup()
    )

@dp.callback_query(lambda query: query.data.startswith("delete_prompt_"))
async def delete_prompt_confirm_handler(query: types.CallbackQuery):
    prompt_id = int(query.data.split("delete_prompt_")[1])
    delete_system_prompt(prompt_id)
    await query.answer(f"Deleted prompt ID: {prompt_id}")

@dp.callback_query(lambda query: query.data == "delete_model")
async def delete_model_callback_handler(query: types.CallbackQuery):
    models = await model_list()
    delete_model_kb = InlineKeyboardBuilder()
    for model in models:
        modelname = model["name"]
        delete_model_kb.row(
            types.InlineKeyboardButton(
                text=modelname, callback_data=f"delete_model_{modelname}"
            )
        )
    await query.message.edit_text(
        f"{len(models)} models available for deletion.", reply_markup=delete_model_kb.as_markup()
    )

@dp.callback_query(lambda query: query.data.startswith("delete_model_"))
async def delete_model_confirm_handler(query: types.CallbackQuery):
    modelname = query.data.split("delete_model_")[1]
    response = await manage_model("delete", modelname)
    if response.status == 200:
        await query.answer(f"Deleted model: {modelname}")
    else:
        await query.answer(f"Failed to delete model: {modelname}")

@dp.message(Command("temp"))
async def set_temperature_command(message: types.Message):
    try:
        temp = float(message.text.split(maxsplit=1)[1])
        if 0.0 <= temp <= 1.0:
            chat_key = get_chat_key(message)
            await ACTIVE_CHATS.update_temperature(chat_key, temp)
            await message.answer(f"Temperature set to {temp} for this chat.")
        else:
            await message.answer("Temperature must be between 0.0 and 1.0.")
    except (ValueError, IndexError):
        await message.answer("Usage: /temp [temperature value between 0.0 and 1.0]")

@dp.message()
@perms_allowed
async def handle_message(message: types.Message):
    await get_bot_info()
    
    if message.chat.type == "private":
        await ollama_request(message)
        return

    # Randomly reply to 10% of chats where one's name isn't mentioned
    if message.text and ("marv" in message.text.lower() or random.random() < 0.1):
        await ollama_request(message)
        return

    if await is_mentioned_in_group_or_supergroup(message):
        thread = await collect_message_thread(message)
        prompt = format_thread_for_prompt(thread)
        
        await ollama_request(message, prompt)

async def is_mentioned_in_group_or_supergroup(message: types.Message):
    if message.chat.type not in ["group", "supergroup"]:
        return False
    
    is_mentioned = (
        (message.text and message.text.startswith(mention)) or
        (message.caption and message.caption.startswith(mention))
    )
    
    is_reply_to_bot = (
        message.reply_to_message and 
        message.reply_to_message.from_user.id == bot.id
    )
    
    return is_mentioned or is_reply_to_bot

async def collect_message_thread(message: types.Message, thread=None):
    if thread is None:
        thread = []
    
    thread.insert(0, message)
    
    if message.reply_to_message:
        await collect_message_thread(message.reply_to_message, thread)
    
    return thread

def format_thread_for_prompt(thread):
    prompt = "Conversation thread:\n\n"
    for msg in thread:
        sender = "User" if msg.from_user.id != bot.id else "Bot"
        content = msg.text or msg.caption or "[No text content]"
        prompt += f"{sender}: {content}\n\n"
    
    prompt += "History:"
    return prompt

async def process_image(message):
    image_base64 = ""
    if message.content_type == "photo":
        image_buffer = io.BytesIO()
        await bot.download(message.photo[-1], destination=image_buffer)
        image_base64 = base64.b64encode(image_buffer.getvalue()).decode("utf-8")
    return image_base64

def get_chat_key(message: types.Message) -> str:
    """Generate a unique key for each chat context"""
    if message.chat.type == "private":
        return f"private_{message.from_user.id}"
    else:
        return f"group_{message.chat.id}"  # Only use group ID for group chats

async def add_prompt_to_active_chats(message, prompt, image_base64, modelname, system_prompt=None):
    chat_key = get_chat_key(message)
    await ACTIVE_CHATS.initialize_chat(chat_key, modelname, DEFAULT_TEMPERATURE, selected_prompt_id)

    # 2. Prepare the messages list:  Append to existing messages, don't overwrite
    messages = (await ACTIVE_CHATS.get(chat_key))["messages"]

    # 3. Add system prompt if provided and not already present
    if system_prompt:
        # Check if a system prompt already exists.  Only add if it doesn't.
        existing_system_messages = [
            msg for msg in messages if msg.get("role") == "system"
        ]
        if not existing_system_messages:
            messages.append({"role": "system", "content": system_prompt})

    # 4. Add the new user message
    user_identifier = (
        message.from_user.first_name if message.chat.type != "private" else ""
    )
    content_with_user = (
        f"{user_identifier + ': ' if user_identifier else ''}{prompt}"
    )
    messages.append(
        {
            "role": "user",
            "content": content_with_user,
            "images": [image_base64] if image_base64 else [],
        }
    )

    # 5. Update the ACTIVE_CHATS dictionary *after* modifying the messages list
    await ACTIVE_CHATS.update_model(chat_key, modelname)

    # 6.  *Don't* re-initialize temperature here.  It's already handled.

    # 7. Save to DB *after* all changes
    chat_data = await ACTIVE_CHATS.get(chat_key)
    save_active_chat_context_to_db(chat_key, chat_data)

def save_active_chat_context_to_db(chat_key, chat_context):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    messages_json = json.dumps(chat_context["messages"]) if chat_context.get("messages") else None
    c.execute(replace_active_chat_contexts_query,
              (chat_key, chat_context["model"], chat_context.get("selected_prompt_id"), messages_json, chat_context["stream"]))
    conn.commit()
    conn.close()
    print(f"Active chat context for key '{chat_key}' saved to database.")

async def send_response(message, text):
    for page_text in text:
        await bot.send_message(
            chat_id=message.chat.id,
            text=page_text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.message_id
        )

async def handle_response(message, response_data, full_response):
    chat_key = get_chat_key(message)
    full_response_stripped = full_response.strip()
    if full_response_stripped == "":
        return
    if response_data.get("done"):

        formatted_response = convert_markdown_for_telegram(full_response_stripped, message.chat.id < 0)
        if (message.chat.id > 0):
            formatted_response = [f"{page}\n\n⚙️ {modelname}\nGenerated in {response_data.get('total_duration') / 1e9:.2f}s." for page in formatted_response]
        text = formatted_response
        await send_response(message, text)
        await ACTIVE_CHATS.update_message(chat_key, "assistant", full_response_stripped)

        logging.info(
            f"[Response]: '{full_response_stripped}' for {message.from_user.first_name} {message.from_user.last_name}"
        )
        chat_data = await ACTIVE_CHATS.get(chat_key)
        save_active_chat_context_to_db(chat_key, chat_data)
        if response_data.get('total_duration') and response_data.get('total_tokens'):
            duration_sec = response_data.get('total_duration') / 1e9
            tokens_per_sec = response_data.get('total_tokens') / duration_sec if duration_sec > 0 else 0
            logging.info(f"[Token Usage] Model: {modelname}, Duration: {duration_sec:.2f}s, Tokens: {response_data.get('total_tokens')}, Throughput: {tokens_per_sec:.2f} tokens/sec")
        return True
    return False

async def ollama_request(message: types.Message, prompt: str = None):
    user_full_name = f"{message.from_user.first_name} {message.from_user.last_name}"
    user_id = message.from_user.id
    chat_key = get_chat_key(message)
    try:
        full_response = ""
        await bot.send_chat_action(message.chat.id, "typing") # Start typing here
        image_base64 = await process_image(message)
        
        # Determine the prompt
        if prompt is None:
            prompt = message.text or message.caption

        # Retrieve and prepare system prompt if selected
        system_prompt = None
        if selected_prompt_id is not None:
            system_prompts = get_system_prompts(user_id=message.from_user.id, is_global=None)
            if system_prompts:
                # Find the specific prompt by ID
                for sp in system_prompts:
                    if sp[0] == selected_prompt_id:
                        system_prompt = sp[2]
                        break
                
                if system_prompt is None:
                    logging.warning(f"Selected prompt ID {selected_prompt_id} not found for user {message.from_user.id}")

        # Save the user's message
        save_chat_message(message.from_user.id, "user", prompt)

        # Prepare the active chat with the system prompt
        await add_prompt_to_active_chats(message, prompt, image_base64, modelname, system_prompt)
        
        logging.info(
            f"[OllamaAPI]: Processing '{prompt}' for {user_full_name}"
        )
        
        # Get the chat key and payload
        payload = await ACTIVE_CHATS.get(chat_key)
        payload["selected_prompt_id"] = selected_prompt_id
        temperature = payload.get("temperature")
        
        # Generate response
        async for response_data in generate(payload, modelname, prompt, temperature=temperature):
            msg = response_data.get("message")
            if msg is None:
                continue
            chunk = msg.get("content", "")
            full_response += chunk

            if any([c in chunk for c in ".\n!?"]) or response_data.get("done"):
                if await handle_response(message, response_data, full_response):
                    save_chat_message(message.from_user.id, "assistant", full_response)
                    break

    except Exception as e:
        print(f"-----\n[OllamaAPI-ERR] CAUGHT FAULT!\n{traceback.format_exc()}\n-----")
        await bot.send_message(
            chat_id=message.chat.id,
            text=f"Something went wrong: {str(e)}",
            parse_mode=ParseMode.HTML,
        )
    finally:
        await bot.send_chat_action(message.chat.id, "cancel") # Stop typing in finally block

def save_context_to_db(chat_key):
    """Save the active chat to DB"""
    print(f"\nSaving context for {chat_key} to database...")
    save_active_chat_context_to_db(chat_key, ACTIVE_CHATS.get(chat_key, {}))
    print(f"Context for {chat_key} saved successfully!")

def signal_handler(sig, frame):
    """Handle Ctrl+C by saving context before exit"""
    print("\nCtrl+C detected!")
    save_global_settings_to_db()
    asyncio.run(asyncio.coroutine(save_active_chats_to_db)())
    sys.exit(0)

def load_global_settings_from_db():
    global modelname
    global selected_prompt_id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(select_global_settings_limit_1_query)
    settings = c.fetchone()
    if settings:
        modelname, db_selected_prompt_id = settings
        selected_prompt_id = int(db_selected_prompt_id) if db_selected_prompt_id is not None else None
    else:
        print("No settings found in global_settings table.")

    # Load SYSTEM_PROMPT from env
    env_system_prompt = os.getenv("SYSTEM_PROMPT")
    print(f"SYSTEM_PROMPT from .env: '{env_system_prompt}'")

    if env_system_prompt and selected_prompt_id is None:
        print("Condition 'env_system_prompt and selected_prompt_id is None' is TRUE - Checking for existing prompt...")
        # Check if a system prompt with this text already exists
        c.execute(select_id_from_system_prompts_query, (env_system_prompt,))
        existing_prompt = c.fetchone()

        if existing_prompt:
            selected_prompt_id = existing_prompt[0]
            print(f"Existing system prompt found, using ID: {selected_prompt_id}")
        else:
            print("No existing system prompt found, creating a new one...")
            # Create a new system prompt
            c.execute(insert_system_prompts_query, (env_system_prompt, None, True))
            selected_prompt_id = c.lastrowid
            print(f"Created new system prompt from .env with ID: {selected_prompt_id}")
            conn.commit() # Commit here to save the newly inserted prompt
    else:
        print("Condition 'env_system_prompt and selected_prompt_id is None' is FALSE - Skipping default prompt loading.")

    conn.close()
    print(f"Global settings loaded from database: modelname={modelname}, selected_prompt_id={selected_prompt_id}")

def save_global_settings_to_db():
    global modelname
    global selected_prompt_id
    global DEFAULT_TEMPERATURE
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(update_global_settings_query, (modelname, selected_prompt_id, DEFAULT_TEMPERATURE))
    conn.commit()
    conn.close()
    print(f"Global settings saved to database: modelname={modelname}, selected_prompt_id={selected_prompt_id}, temperature={DEFAULT_TEMPERATURE}")

async def load_active_chats_from_db():  # Make the function async
    global ACTIVE_CHATS
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(select_active_chat_contexts_query)
    rows = c.fetchall()
    loaded_chats = {}  # Temporary dictionary to store loaded chats
    for row in rows:
        chat_key, db_modelname, db_selected_prompt_id, messages_json, stream = row
        messages = json.loads(messages_json) if messages_json else []
        loaded_chats[chat_key] = {  # Store in the temporary dictionary
            "model": db_modelname,
            "messages": messages,
            "stream": bool(stream),
            "selected_prompt_id": int(db_selected_prompt_id) if db_selected_prompt_id is not None else None
        }
    conn.close()
    print(f"Active chats loaded from database. Count: {len(loaded_chats)}")
    await ACTIVE_CHATS.set_all(loaded_chats)  # Await the set_all call

async def save_active_chats_to_db():
    all_chats = await ACTIVE_CHATS.get_all() # get all chats
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(delete_active_chat_contexts_query)
    for chat_key, chat_data in all_chats.items():
        messages_json = json.dumps(chat_data["messages"]) if chat_data.get("messages") else None
        c.execute(insert_active_chat_contexts_query,
                  (chat_key, chat_data["model"], chat_data.get("selected_prompt_id"), messages_json, chat_data["stream"]))
    conn.commit()
    conn.close()
    print(f"Active chats saved to database. Count: {len(all_chats)}")

def delete_active_chat_context_from_db(chat_key):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(delete_active_chat_context_by_key_query, (chat_key,))
    conn.commit()
    conn.close()
    print(f"Active chat context for key '{chat_key}' deleted from database.")

async def main():
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    init_db()
    load_global_settings_from_db()
    await load_active_chats_from_db()  # Await the loading
    allowed_ids = load_allowed_ids_from_db()
    print(f"allowed_ids: {allowed_ids}")
    await bot.set_my_commands(commands)
    try:
        await dp.start_polling(bot, skip_update=True)
    except Exception as e:
        logging.error(f"Error during polling: {e}", exc_info=True)
        print(f"Bot polling stopped due to error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
