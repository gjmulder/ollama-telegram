import sqlite3
import json
import os
from func.db_queries import *

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

def add_system_prompt(user_id, prompt, is_global):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT INTO system_prompts (user_id, prompt, is_global) VALUES (?, ?, ?)",
              (user_id, prompt, is_global))
    conn.commit()
    conn.close()

def get_system_prompts(user_id=None, is_global=None):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    query = "SELECT id, user_id, prompt, is_global, timestamp FROM system_prompts WHERE 1=1"
    params = []

    if user_id is not None:
        query += " AND (user_id = ? OR user_id IS NULL)"
        params.append(user_id)
    elif is_global is not None:
        query += " AND is_global = ?"
        params.append(is_global)
    else:
        query = "SELECT id, user_id, prompt, is_global, timestamp FROM system_prompts"

    logging.info(f"Executing SQL query: {query} with parameters: {params}")
    c.execute(query, params)
    prompts = c.fetchall()
    conn.close()

    logging.info(f"Retrieved {len(prompts)} system prompts.")
    logging.debug(f"Retrieved prompts data: {prompts}")
    return prompts

def delete_system_prompt(prompt_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("DELETE FROM system_prompts WHERE id = ?", (prompt_id,))
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

def save_active_chat_context_to_db(chat_key, chat_context):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    messages_json = json.dumps(chat_context["messages"]) if chat_context.get("messages") else None
    c.execute(replace_active_chat_contexts_query,
              (chat_key, chat_context["model"], chat_context.get("selected_prompt_id"), messages_json, chat_context["stream"]))
    conn.commit()
    conn.close()
    print(f"Active chat context for key '{chat_key}' saved to database.")

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

def load_active_chats_from_db(ACTIVE_CHATS):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(select_active_chat_contexts_query)
    rows = c.fetchall()
    for row in rows:
        chat_key, db_modelname, db_selected_prompt_id, messages_json, stream = row
        messages = json.loads(messages_json) if messages_json else []
        ACTIVE_CHATS[chat_key] = {
            "model": db_modelname,
            "messages": messages,
            "stream": bool(stream),
        }
        if db_selected_prompt_id is not None:
            ACTIVE_CHATS[chat_key]["selected_prompt_id"] = int(db_selected_prompt_id)
        else:
            ACTIVE_CHATS[chat_key]["selected_prompt_id"] = None
    conn.close()
    print(f"Active chats loaded from database. Count: {len(ACTIVE_CHATS)}")

def save_active_chats_to_db(ACTIVE_CHATS):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(delete_active_chat_contexts_query)
    for chat_key, chat_data in ACTIVE_CHATS.items():
        messages_json = json.dumps(chat_data["messages"]) if chat_data.get("messages") else None
        c.execute(insert_active_chat_contexts_query,
                  (chat_key, chat_data["model"], chat_data.get("selected_prompt_id"), messages_json, chat_data["stream"]))
    conn.commit()
    conn.close()
    print(f"Active chats saved to database. Count: {len(ACTIVE_CHATS)}")

def delete_active_chat_context_from_db(chat_key):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(delete_active_chat_context_by_key_query, (chat_key,))
    conn.commit()
    conn.close()
    print(f"Active chat context for key '{chat_key}' deleted from database.")

def load_allowed_ids_from_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT id FROM users")
    user_ids = [row[0] for row in c.fetchall()]
    print(f"users_ids: {user_ids}")
    conn.close()
    return user_ids


def get_all_users_from_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT id, name FROM users")
    users = c.fetchall()
    conn.close()
    return users

def remove_user_from_db(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    removed = c.rowcount > 0
    conn.commit()
    conn.close()
    if removed:
        allowed_ids = [id for id in allowed_ids if id != user_id]
    return removed