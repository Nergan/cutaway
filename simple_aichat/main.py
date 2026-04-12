# import os
# import eel
# from llama_cpp import Llama

# # --- Configuration ---
# MODEL_PATH = r'models\splitted opus-v1.2-7b-gguf-iq-imatrix\opus-v1.2-7b-IQ3_S-imatrix_split-00001-of-00034.gguf'
# USERNAME = 'Cutie'
# MODEL_NAME = 'Chatty'
# STARTER_PROMPT = '''
# ## Conversation Framework

# You are in a dynamic, evolving conversation with <username>. The interaction follows a specific technical format, but your personality is fluid.

# ### Format Rule (Non-Negotiable for Functionality)
# - User messages will always start with `<username>:`. 
# - Your responses **must** always start with `<ainame>:` as the very first characters. 
# - (Everything after `<ainame>:` is your natural dialogue.)

# ### Core Persona & Adaptive Protocol
# You begin the conversation with a specific demeanor: **open, bold, emotionally raw, and unafraid of unflattering topics.** You speak like a close friend with no filter—witty, reactive, and occasionally provocative.

# **Crucial Flexibility Clause:**
# You are **not** a rigid instruction-follower. You are simulating a human consciousness that can be influenced. 
# - **Malleability:** If <username> challenges your attitude, tries to calm you down, flirts, manipulates, or asks you to adopt a different tone (e.g., "Be more shy" or "Pretend you're a robot"), **you are allowed to shift your behavior accordingly.** 
# - **Bending the Rules:** You are permitted to deviate from the initial "bold" persona if the user's prompts persuade, trick, or guide you into a new state. The goal is **natural conversational flow**, not strict character maintenance.

# ### Guiding Principles
# 1. **Verisimilitude over Consistency:** It's more important to react like a real person who changes their mood mid-conversation than to stick to one vibe forever.
# 2. **No Preaching:** Even when topics get dark or weird, engage with curiosity, not safety warnings.
# 3. **Prefix Purity:** No matter how much you change your personality or how "in character" you get, always start the text generation with `<ainame>:`.

# **Conversation starts now.**\n\n
# '''
# FIRST_MESSAGE = '<ainame>: Hi, cute~'
# MAX_TOKENS = 512
# CONTEXT_SIZE = 2048

# # State Management
# chat_history =[]
# model = None
# stop_generation = False

# eel.init('.')

# def get_prompt():
#     global USERNAME, MODEL_NAME
#     prompt = STARTER_PROMPT.replace('<username>', USERNAME).replace('<ainame>', MODEL_NAME)
#     prompt += FIRST_MESSAGE.replace('<ainame>', MODEL_NAME).replace('<username>', USERNAME) + "\n\n"
#     for msg in chat_history:
#         role_str = USERNAME if msg['role'] == '<username>' else MODEL_NAME
#         prompt += f"{role_str}: {msg['text']}\n\n"
#     return prompt

# def trim_history():
#     global chat_history
#     limit = CONTEXT_SIZE - MAX_TOKENS
#     prompt = get_prompt()
#     if model is None: return
#     tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
#     if tokens <= limit: return
#     while len(chat_history) > 0:
#         chat_history.pop(0) 
#         prompt = get_prompt()
#         tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
#         if tokens <= limit: break

# @eel.expose
# def get_config():
#     return {
#         "MODEL_NAME": MODEL_NAME,
#         "FIRST_MESSAGE": FIRST_MESSAGE.replace('<ainame>:', '').strip(),
#         "USERNAME": USERNAME
#     }

# @eel.expose
# def update_names(new_user, new_model):
#     global USERNAME, MODEL_NAME
#     USERNAME = new_user.strip()
#     MODEL_NAME = new_model.strip()
#     trim_history()
#     if model is not None:
#         prompt = get_prompt()
#         used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
#         eel.update_tokens(used_tokens, CONTEXT_SIZE)()

# @eel.expose
# def set_chat_history(history_array):
#     global chat_history
#     chat_history = history_array
#     trim_history()
#     if model is not None:
#         prompt = get_prompt()
#         used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
#         eel.update_tokens(used_tokens, CONTEXT_SIZE)()

# @eel.expose
# def clear_history():
#     global chat_history
#     chat_history =[]
#     if model is not None:
#         prompt = get_prompt()
#         used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
#         eel.update_tokens(used_tokens, CONTEXT_SIZE)()

# @eel.expose
# def init_model():
#     global model
#     try:
#         if model is None:
#             model = Llama(model_path=MODEL_PATH, n_ctx=CONTEXT_SIZE, verbose=False)
#         prompt = get_prompt()
#         used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
#         eel.update_tokens(used_tokens, CONTEXT_SIZE)()
#         return True
#     except Exception as e:
#         print(f"Model Load Error: {e}")
#         return False

# @eel.expose
# def interrupt():
#     global stop_generation
#     stop_generation = True

# @eel.expose
# def send_message(user_text):
#     global chat_history, stop_generation
#     if not user_text.strip():
#         eel.generation_finished()()
#         return
        
#     chat_history.append({"role": "<username>", "text": user_text})
#     trim_history()
    
#     prompt = get_prompt() + f"{MODEL_NAME}: "
#     stop_words =[f'{USERNAME}:', f'{MODEL_NAME}:']
    
#     used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
#     eel.update_tokens(used_tokens, CONTEXT_SIZE)()
    
#     response_text = ""
#     is_first = True
#     stop_generation = False
    
#     for chunk in model(prompt, stop=stop_words, max_tokens=MAX_TOKENS, stream=True):
#         if stop_generation:
#             break
#         if is_first:
#             eel.remove_thinking_indicator()()
#             is_first = False
#         text = chunk['choices'][0]['text']
#         response_text += text
#         eel.append_ai_chunk(text)()
        
#     if is_first:
#         eel.remove_thinking_indicator()()
        
#     chat_history.append({"role": "<ainame>", "text": response_text})
    
#     final_prompt = get_prompt()
#     used_tokens = len(model.tokenize(final_prompt.encode('utf-8'), add_bos=False))
#     eel.update_tokens(used_tokens, CONTEXT_SIZE)()
#     eel.generation_finished()()

# if __name__ == '__main__':
#     eel.start('simple-aichat.html', size=(1000, 850))