# >> interactions
import logging
import os
import aiohttp
import json
from aiogram import types
from aiohttp import ClientTimeout
from asyncio import Lock
from functools import wraps
from dotenv import load_dotenv
import re  # Add this import at the top if not already present
from func.db_manager import DatabaseManager # Import DatabaseManager

load_dotenv()
token = os.getenv("TOKEN")
allowed_ids = list(map(int, os.getenv("USER_IDS", "").split(",")))
admin_ids = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
ollama_base_url = os.getenv("OLLAMA_BASE_URL")
ollama_port = os.getenv("OLLAMA_PORT", "11434")
log_level_str = os.getenv("LOG_LEVEL", "INFO")
allow_all_users_in_groups = bool(int(os.getenv("ALLOW_ALL_USERS_IN_GROUPS", "0")))
log_levels = list(logging._levelToName.values())
timeout = os.getenv("TIMEOUT", "3000")
if log_level_str not in log_levels:
    log_level = logging.DEBUG
else:
    log_level = logging.getLevelName(log_level_str)
logging.basicConfig(level=log_level)

class OllamaAPIClient:
    def __init__(self, base_url, port):
        self.base_url = base_url
        self.port = port

    async def manage_model(self, action: str, model_name: str):
        async with aiohttp.ClientSession() as session:
            url = f"http://{self.base_url}:{self.port}/api/{action}"
            
            if action == "pull":
                # Use the exact payload structure from the curl example
                data = json.dumps({"name": model_name})
                headers = {
                    'Content-Type': 'application/json'
                }
                logging.info(f"Pulling model: {model_name}")
                logging.info(f"Request URL: {url}")
                logging.info(f"Request Payload: {data}")
                
                async with session.post(url, data=data, headers=headers) as response:
                    logging.info(f"Pull model response status: {response.status}")
                    response_text = await response.text()
                    logging.info(f"Pull model response text: {response_text}")
                    return response
            elif action == "delete":
                data = json.dumps({"name": model_name})
                headers = {
                    'Content-Type': 'application/json'
                }
                async with session.delete(url, data=data, headers=headers) as response:
                    return response
            else:
                logging.error(f"Unsupported model management action: {action}")
                return None

    async def model_list(self):
        async with aiohttp.ClientSession() as session:
            url = f"http://{self.base_url}:{self.port}/api/tags"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["models"]
                else:
                    return []
                
    async def generate(self, payload: dict, modelname: str, prompt: str, temperature: float = 0.7):
        client_timeout = ClientTimeout(total=int(timeout))
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            url = f"http://{self.base_url}:{self.port}/api/chat"

            # Prepare the payload according to Ollama API specification
            ollama_payload = {
                "model": modelname,
                "messages": payload.get("messages", []),
                "stream": payload.get("stream", True),
                "options": {"temperature": temperature}  # Add temperature to options
            }

            try:
                logging.info(f"Sending request to Ollama API: {url}")
                logging.info(f"Payload: {json.dumps(ollama_payload, indent=2)}")

                async with session.post(url, json=ollama_payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logging.error(f"API Error: {response.status} - {error_text}")
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=f"API Error: {error_text}"
                        )

                    buffer = b""
                    async for chunk in response.content.iter_any():
                        buffer += chunk
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            line = line.strip()
                            if line:
                                try:
                                    yield json.loads(line)
                                except json.JSONDecodeError as e:
                                    logging.error(f"JSON Decode Error: {e}")
                                    logging.error(f"Problematic line: {line}")

            except aiohttp.ClientError as e:
                logging.error(f"Client Error during request: {e}")
                raise

def perms_allowed(func):
    @wraps(func)
    async def wrapper(message: types.Message = None, query: types.CallbackQuery = None):
        user_id = message.from_user.id if message else query.from_user.id
        user_full_name = f"{message.from_user.first_name} {message.from_user.last_name}({message.from_user.id})" if message else f"{query.from_user.first_name} {query.from_user.last_name}({query.from_user.id})"
        db_manager = DatabaseManager() # Instantiate DatabaseManager
        try:
            allowed_ids = db_manager.load_allowed_user_ids() # Use DatabaseManager method
            admin_ids = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) # admin_ids still loaded from env
            if user_id in admin_ids:
                logging.info(f"[PERMS_ALLOWED] {user_full_name} is allowed because they are an admin.")
                if message:
                    return await func(message)
                elif query:
                    return await func(query=query)
            elif user_id in allowed_ids:
                logging.info(f"[PERMS_ALLOWED] {user_full_name} is allowed because they are in allowed_ids.")
                if message:
                    return await func(message)
                elif query:
                    return await func(query=query)
            else:
                if message:
                    if message and message.chat.type in ["supergroup", "group"]:
                        if allow_all_users_in_groups:
                            logging.info(f"[PERMS_ALLOWED] {user_full_name} is allowed in group '{message.chat.title}'({message.chat.id}) because ALLOW_ALL_USERS_IN_GROUPS is True.")
                            return await func(message)
                        else:
                            logging.info(f"[PERMS_ALLOWED] {user_full_name} is denied in group '{message.chat.title}'({message.chat.id}). ALLOW_ALL_USERS_IN_GROUPS is False and user is not in allowed_ids/admin_ids.")
                            await message.answer("Access Denied")
                            return
                    else:
                        logging.info(f"[PERMS_ALLOWED] {user_full_name} is denied in private chat. User is not in allowed_ids/admin_ids.")
                        await message.answer("Access Denied")
                        return
                elif query:
                    if message and message.chat.type in ["supergroup", "group"]:
                        logging.info(f"[PERMS_ALLOWED-QUERY] {user_full_name} is denied in group '{message.chat.title}'({message.chat.id}). Queries are not allowed in groups.") # Queries are generally not expected in groups, so explicitly deny
                        return # Do not answer, just ignore. Or maybe answer "Queries not allowed in groups" if needed.
                    else:
                        logging.info(f"[PERMS_ALLOWED-QUERY] {user_full_name} is denied in private chat query. User is not in allowed_ids/admin_ids.")
                        await query.answer("Access Denied")
                        return
        finally:
            db_manager.close_connection() # Close connection in finally block

    return wrapper


def perms_admins(func):
    @wraps(func)
    async def wrapper(message: types.Message = None, query: types.CallbackQuery = None):
        user_id = message.from_user.id if message else query.from_user.id
        user_full_name = f"{message.from_user.first_name} {message.from_user.last_name}({message.from_user.id})" if message else f"{query.from_user.first_name} {query.from_user.last_name}({query.from_user.id})"
        db_manager = DatabaseManager() # Instantiate DatabaseManager
        try:
            admin_ids = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) # admin_ids still loaded from env
            if user_id in admin_ids:
                logging.info(f"[PERMS_ADMINS] {user_full_name} is allowed because they are an admin.")
                if message:
                    return await func(message)
                elif query:
                    return await func(query=query)
            else:
                if message:
                    if message and message.chat.type in ["supergroup", "group"]:
                        logging.info(f"[PERMS_ADMINS] {user_full_name} is denied in group '{message.chat.title}'({message.chat.id}). Admin permissions are not applicable in groups.") # Admin commands usually not relevant in groups
                        return # Or maybe send "Admin commands not in groups"
                    else:
                        logging.info(f"[PERMS_ADMINS] {user_full_name} is denied in private chat. User is not in admin_ids.")
                        await message.answer("Access Denied")
                        logging.info(
                            f"[MSG] {message.from_user.first_name} {message.from_user.last_name}({message.from_user.id}) is not allowed to use this bot."
                        )
                elif query:
                    if message and message.chat.type in ["supergroup", "group"]:
                        logging.info(f"[PERMS_ADMINS-QUERY] {user_full_name} is denied in group '{message.chat.title}'({message.chat.id}). Admin queries are not applicable in groups.") # Admin commands usually not relevant in groups
                        return # Or maybe send "Admin commands not in groups"
                    else:
                        logging.info(f"[PERMS_ADMINS-QUERY] {user_full_name} is denied in private chat query. User is not in admin_ids.")
                        await query.answer("Access Denied")
                        logging.info(
                            f"[QUERY] {message.from_user.first_name} {message.from_user.last_name}({message.from_user.id}) is not allowed to use this bot."
                        )
        finally:
            db_manager.close_connection() # Close connection in finally block

    return wrapper

class contextLock:
    lock = Lock()

    async def __aenter__(self):
        await self.lock.acquire()

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        self.lock.release()

def convert_markdown_for_telegram(text, is_group=False):
    """
    Convert markdown text for Telegram into equivalent HTML formatting while escaping HTML special characters.
    Converts non-empty <think> tags to monospace format, removes empty ones.
    """

    logging.debug(f"Converting markdown for Telegram: {text}")
    
    # First escape HTML special characters except those already in HTML tags
    parts = re.split(r'(<[^>]*>)', text)
    for i in range(0, len(parts), 2):  # Only escape non-tag parts
        parts[i] = parts[i].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = ''.join(parts)

    # Remove "Marvin: " from the beginning of the text
    text = re.sub(r'^Marvin: ', '', text)

    # Remove the first set of matched double quotes, if present
    text = re.sub(r'^"(.*?)"', r'\1', text, count=1)

    # Remove entire <think> some text </think> block if in a group chat
    if is_group:
        text = re.sub(r'<think>(.*?)</think>', '', text, flags=re.DOTALL)
        
    # Remove empty think tags and convert non-empty ones to monospace
    text = re.sub(r'<think>\s*</think>\s*', '', text)  # Remove empty think tags
    text = re.sub(r'<think>(.*?)</think>',
                 lambda m: f'<code>{m.group(1).strip().replace("<", "&lt;").replace(">", "&gt;")}</code >' if m.group(1).strip() else '',
                 text, flags=re.DOTALL)

    # Handle code blocks first to prevent other formatting inside them
    def escape_code(match):
        code = match.group(1) if len(match.groups()) == 1 else match.group(2)
        # **Ensure HTML escaping within code blocks is robust**
        code = code.replace('<', '&lt;').replace('>', '&gt;')
        return f'<pre><code>{code}</code></pre>'

    # Code blocks with language specification ```language
    text = re.sub(r'```(\w+)\n(.*?)```', escape_code, text, flags=re.DOTALL)
    # Regular code blocks ```
    text = re.sub(r'```(.*?)```', escape_code, text, flags=re.DOTALL)
    # Inline code `text`
    text = re.sub(r'`(.*?)`', lambda m: f'<code>{m.group(1).replace("<", "&lt;").replace(">", "&gt;")}</code >', text)

    # Other formatting
    text = re.sub(r'(\*\*|__)(.*?)\1', lambda m: f'<b>{m.group(2)}</b>', text)
    text = re.sub(r'(\*|_)(.*?)\1', lambda m: f'<i>{m.group(2)}</i>', text)
    text = re.sub(r'~~(.*?)~~', lambda m: f'<s>{m.group(1)}</s>', text)
    text = re.sub(r'__(.*?)__', lambda m: f'<u>{m.group(1)}</u>', text)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = re.sub(r'\|\|(.*?)\|\|', lambda m: f'<tg-spoiler>{m.group(1)}</tg-spoiler>', text)
    text = re.sub(r'^\s*[-*+]\s+(.+)$', r'• \1', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*>\s+(.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)

    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    # Ensure no trailing blank lines
    text = text.strip()

    # Implement pagination here
    MAX_MESSAGE_LENGTH = 4096
    pages = []
    current_page = ""
    block_elements = re.split(r'(</p>|</div>|<pre>|</blockquote>|<ul>|<ol>)', text, flags=re.IGNORECASE) # Split by common block-level elements

    for block in block_elements:
        if not block:
            continue

        if len(current_page) + len(block) <= MAX_MESSAGE_LENGTH:
            current_page += block
        else:
            pages.append(current_page)
            current_page = block
            while len(current_page) > MAX_MESSAGE_LENGTH: # Handle very long blocks by further splitting
                split_point = current_page[:MAX_MESSAGE_LENGTH].rfind(' ') # Find last space to split at word boundary
                if split_point == -1:
                    split_point = MAX_MESSAGE_LENGTH # If no space, force split
                pages.append(current_page[:split_point])
                current_page = current_page[split_point:]

    if current_page: # Add the last page
        pages.append(current_page)

    return pages
