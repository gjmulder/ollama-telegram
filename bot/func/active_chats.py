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
