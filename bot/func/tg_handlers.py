import logging
import os
import random
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters.command import Command, CommandStart
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from func.interactions import perms_admins, perms_allowed

dp = Dispatcher()

@dp.callback_query(lambda query: query.data == "register")
async def register_callback_handler(query: types.CallbackQuery):
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    register_user(user_id, user_name)
    await query.answer("You have been registered successfully!")

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    start_message = f"Welcome, <b>{message.from_user.full_name}</b>!"
    await message.answer(
        start_message,
        parse_mode=ParseMode.HTML,
        reply_markup=start_kb.as_markup(),
        disable_web_page_preview=True,
    )

@dp.message(Command("undo"))
async def command_undo_handler(message: Message) -> None:
    if message.from_user.id in allowed_ids:
        if message.from_user.id in ACTIVE_CHATS:
            async with ACTIVE_CHATS_LOCK:
                ACTIVE_CHATS.pop(message.from_user.id)
            logging.info(f"Chat has been undone for {message.from_user.first_name}")
            await bot.send_message(
                chat_id=message.chat.id,
                text="Chat has been undone",
            )

@dp.message(Command("history"))
async def command_get_context_handler(message: Message) -> None:
    if message.from_user.id in allowed_ids:
        chat_key = get_chat_key(message)
        if chat_key in ACTIVE_CHATS:
            messages = ACTIVE_CHATS.get(chat_key)["messages"]
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
    async with ACTIVE_CHATS_LOCK:
        if chat_key in ACTIVE_CHATS:
            current_temperature = ACTIVE_CHATS[chat_key].get("temperature", DEFAULT_TEMPERATURE)

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

    async with ACTIVE_CHATS_LOCK:
        for chat_key in ACTIVE_CHATS:
            ACTIVE_CHATS[chat_key]["selected_prompt_id"] = selected_prompt_id

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

    await query.answer(f"System Prompt '{selected_prompt_name}' selected!", show_alert=True)

    async with ACTIVE_CHATS_LOCK:
        for chat_key in ACTIVE_CHATS:
            ACTIVE_CHATS[chat_key]["selected_prompt_id"] = selected_prompt_id

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
            async with ACTIVE_CHATS_LOCK:
                if chat_key not in ACTIVE_CHATS:
                    ACTIVE_CHATS[chat_key] = {"model": modelname, "temperature": temp, "stream": True, "selected_prompt_id": selected_prompt_id, "messages": []}
                else:
                    ACTIVE_CHATS[chat_key]["temperature"] = temp
                logging.info(f"Temperature set for chat_key: {chat_key}, temperature: {ACTIVE_CHATS[chat_key]['temperature']}")
            await message.answer(f"Temperature set to {temp} for this chat.")
        else:
            await message.answer("Temperature must be between 0.0 and 1.0.")
    except (ValueError, IndexError):
        await message.answer("Usage: /temp [temperature value between 0.0 and 1.0]")

@dp.message()
@perms_allowed
async def handle_message(message: types.Message):
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

