init_db_query = '''
PRAGMA foreign_keys = ON;
'''

create_users_table_query = '''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT
)
'''

create_chats_table_query = '''
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    content TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
'''

create_system_prompts_table_query = '''
CREATE TABLE IF NOT EXISTS system_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    prompt TEXT,
    is_global BOOLEAN,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
'''

create_global_settings_table_query = '''
CREATE TABLE IF NOT EXISTS global_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modelname TEXT,
    selected_prompt_id INTEGER,
    temperature REAL
)
'''

create_active_chat_contexts_table_query = '''
CREATE TABLE IF NOT EXISTS active_chat_contexts (
    chat_key TEXT PRIMARY KEY,
    modelname TEXT,
    selected_prompt_id INTEGER,
    messages_json TEXT,
    stream BOOLEAN
)
'''

select_count_global_settings_query = '''
SELECT COUNT(*)
FROM global_settings
'''

insert_global_settings_query = '''
INSERT INTO global_settings (
    modelname,
    selected_prompt_id
) VALUES (?, ?)
'''

insert_or_replace_users_query = '''
INSERT OR REPLACE INTO users VALUES (?, ?)
'''

insert_chats_query = '''
INSERT INTO chats (
    user_id,
    role,
    content
) VALUES (?, ?, ?)
'''

replace_active_chat_contexts_query = '''
REPLACE INTO active_chat_contexts (
    chat_key,
    modelname,
    selected_prompt_id,
    messages_json,
    stream
) VALUES (?, ?, ?, ?, ?)
'''

select_global_settings_limit_1_query = '''
SELECT
    modelname,
    selected_prompt_id
FROM global_settings
LIMIT 1
'''

select_id_from_system_prompts_query = '''
SELECT id
FROM system_prompts
WHERE prompt = ?
'''

insert_system_prompts_query = '''
INSERT INTO system_prompts (
    prompt,
    user_id,
    is_global
) VALUES (?, ?, ?)
'''

update_global_settings_query = '''
UPDATE global_settings
SET
    modelname = ?,
    selected_prompt_id = ?,
    temperature = ?
'''

select_active_chat_contexts_query = '''
SELECT
    chat_key,
    modelname,
    selected_prompt_id,
    messages_json,
    stream
FROM active_chat_contexts
'''

delete_active_chat_contexts_query = '''
DELETE FROM active_chat_contexts
'''

insert_active_chat_contexts_query = '''
INSERT INTO active_chat_contexts (
    chat_key,
    modelname,
    selected_prompt_id,
    messages_json,
    stream
) VALUES (?, ?, ?, ?, ?)
'''

delete_active_chat_context_by_key_query = '''
DELETE FROM active_chat_contexts
WHERE chat_key = ?
'''

select_user_exists_query = "SELECT 1 FROM users WHERE id = ?"
insert_system_prompts_query2 = "INSERT INTO system_prompts (user_id, prompt, is_global) VALUES (?, ?, ?)"
select_system_prompts_query = "SELECT id, user_id, prompt, is_global, timestamp FROM system_prompts WHERE 1=1"
select_system_prompts_user_filter = " AND (user_id = ? OR user_id IS NULL)"
select_system_prompts_global_filter = " AND is_global = ?"
delete_system_prompt_query = "DELETE FROM system_prompts WHERE id = ?"
select_user_ids_query = "SELECT id FROM users"
select_all_users_query = "SELECT id, name FROM users"
delete_user_query = "DELETE FROM users WHERE id = ?" 