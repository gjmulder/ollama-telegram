import sqlite3
import json
import os
from func.db_queries import *

class DatabaseManager:
    def __init__(self, db_name='users.db'):
        self.db_name = db_name
        self.conn = sqlite3.connect(self.db_name)
        self.cursor = self.conn.cursor()

    def close_connection(self):
        self.conn.close()

    def initialize_database(self):
        self.cursor.execute(init_db_query)
        self.cursor.execute(create_users_table_query)
        self.cursor.execute(create_chats_table_query)
        self.cursor.execute(create_system_prompts_table_query)
        self.cursor.execute(create_global_settings_table_query)
        self.cursor.execute(create_active_chat_contexts_table_query)

        # Initialize global settings if not exist
        self.cursor.execute(select_count_global_settings_query)
        if self.cursor.fetchone()[0] == 0:
            initial_model = os.getenv("INITMODEL")
            self.cursor.execute(insert_global_settings_query, (initial_model, None))
        self.conn.commit()

    def register_user(self, user_id, user_name):
        self.cursor.execute(insert_or_replace_users_query, (user_id, user_name))
        self.conn.commit()

    def save_chat_message(self, user_id, role, content):
        # Check if user exists, register if not
        if not self._user_exists(user_id):
            # You might want to fetch the username if available and pass it here
            # For now, using user_id as username as a fallback
            self.register_user(user_id, str(user_id))

        self.cursor.execute(insert_chats_query, (user_id, role, content))
        self.conn.commit()

    def _user_exists(self, user_id):
        self.cursor.execute(select_user_exists_query, (user_id,))
        return self.cursor.fetchone() is not None

    def add_system_prompt(self, user_id, prompt, is_global):
        self.cursor.execute(insert_system_prompts_query2, (user_id, prompt, is_global))
        self.conn.commit()

    def get_system_prompts(self, user_id=None, is_global=None):
        query = select_system_prompts_query
        params = []

        if user_id is not None:
            query += select_system_prompts_user_filter
            params.append(user_id)
            if is_global is not None:
                query += select_system_prompts_global_filter
                params.append(is_global)
        elif is_global is not None:
            query += select_system_prompts_global_filter
            params.append(is_global)

        self.cursor.execute(query, params)
        prompts = self.cursor.fetchall()
        return prompts

    def delete_system_prompt(self, prompt_id):
        self.cursor.execute(delete_system_prompt_query, (prompt_id,))
        self.conn.commit()

    def load_allowed_user_ids(self):
        self.cursor.execute(select_user_ids_query)
        user_ids = [row[0] for row in self.cursor.fetchall()]
        return user_ids

    def get_all_users(self):
        self.cursor.execute(select_all_users_query)
        users = self.cursor.fetchall()
        return users

    def remove_user(self, user_id):
        self.cursor.execute(delete_user_query, (user_id,))
        removed = self.cursor.rowcount > 0
        self.conn.commit()
        return removed

    def load_global_settings(self):
        self.cursor.execute(select_global_settings_limit_1_query)
        settings = self.cursor.fetchone()
        if settings:
            modelname, db_selected_prompt_id = settings
            selected_prompt_id = int(db_selected_prompt_id) if db_selected_prompt_id is not None else None
            return modelname, selected_prompt_id
        return None, None

    def save_global_settings(self, modelname, selected_prompt_id, default_temperature):
        self.cursor.execute(update_global_settings_query, (modelname, selected_prompt_id, default_temperature))
        self.conn.commit()

    async def load_active_chats(self):
        self.cursor.execute(select_active_chat_contexts_query)
        rows = self.cursor.fetchall()
        loaded_chats = {}
        for row in rows:
            chat_key, db_modelname, db_selected_prompt_id, messages_json, stream = row
            messages = json.loads(messages_json) if messages_json else []
            loaded_chats[chat_key] = {
                "model": db_modelname,
                "messages": messages,
                "stream": bool(stream),
                "selected_prompt_id": int(db_selected_prompt_id) if db_selected_prompt_id is not None else None
            }
        return loaded_chats

    async def save_active_chats(self, active_chats):
        self.cursor.execute(delete_active_chat_contexts_query)
        for chat_key, chat_data in active_chats.items():
            messages_json = json.dumps(chat_data["messages"]) if chat_data.get("messages") else None
            self.cursor.execute(insert_active_chat_contexts_query,
                      (chat_key, chat_data["model"], chat_data.get("selected_prompt_id"), messages_json, chat_data["stream"]))
        self.conn.commit()

    def save_active_chat_context(self, chat_key, chat_context):
        messages_json = json.dumps(chat_context["messages"]) if chat_context.get("messages") else None
        self.cursor.execute(replace_active_chat_contexts_query,
                  (chat_key, chat_context["model"], chat_context.get("selected_prompt_id"), messages_json, chat_context["stream"]))
        self.conn.commit()

    def delete_active_chat_context(self, chat_key):
        self.cursor.execute(delete_active_chat_context_by_key_query, (chat_key,))
        self.conn.commit()