import os
import eel
from llama_cpp import Llama
import core

eel.init('.')

@eel.expose
def get_config():
    return {
        "MODEL_NAME": core.MODEL_NAME,
        "FIRST_MESSAGE": core.FIRST_MESSAGE.replace('<ainame>:', '').strip(),
        "USERNAME": core.USERNAME
    }

@eel.expose
def update_names(new_user, new_model):
    core.USERNAME = new_user.strip()
    core.MODEL_NAME = new_model.strip()
    core.trim_history()
    
    if core.model is not None:
        prompt = core.get_prompt()
        used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
        eel.update_tokens(used_tokens, core.CONTEXT_SIZE)()

@eel.expose
def set_chat_history(history_array):
    core.chat_history = history_array
    core.trim_history()
    
    if core.model is not None:
        prompt = core.get_prompt()
        used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
        eel.update_tokens(used_tokens, core.CONTEXT_SIZE)()

@eel.expose
def clear_history():
    core.chat_history =[]
    
    if core.model is not None:
        prompt = core.get_prompt()
        used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
        eel.update_tokens(used_tokens, core.CONTEXT_SIZE)()

@eel.expose
def init_model():
    try:
        if core.model is None:
            path_str = str(core.MODEL_PATH)
            core.model = Llama(model_path=path_str, n_ctx=core.CONTEXT_SIZE, verbose=False)
            
        prompt = core.get_prompt()
        used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
        eel.update_tokens(used_tokens, core.CONTEXT_SIZE)()
        
        return True
    except Exception as e:
        print(f"Model Load Error: {e}")
        return False

@eel.expose
def interrupt():
    core.stop_generation = True

@eel.expose
def send_message(user_text):
    if not user_text.strip():
        eel.generation_finished()()
        return
        
    core.chat_history.append({"role": "<username>", "text": user_text})
    core.trim_history()
    
    prompt = core.get_prompt() + f"{core.MODEL_NAME}: "
    stop_words =[f'{core.USERNAME}:', f'{core.MODEL_NAME}:']
    
    used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
    eel.update_tokens(used_tokens, core.CONTEXT_SIZE)()
    
    response_text = ""
    is_first = True
    core.stop_generation = False
    
    for chunk in core.model(prompt, stop=stop_words, max_tokens=core.MAX_TOKENS, stream=True):
        if core.stop_generation:
            break
            
        if is_first:
            eel.remove_thinking_indicator()()
            is_first = False
            
        text = chunk['choices'][0]['text']
        response_text += text
        eel.append_ai_chunk(text)()
        
    if is_first:
        eel.remove_thinking_indicator()()
        
    core.chat_history.append({"role": "<ainame>", "text": response_text})
    
    final_prompt = core.get_prompt()
    used_tokens = len(core.model.tokenize(final_prompt.encode('utf-8'), add_bos=False))
    eel.update_tokens(used_tokens, core.CONTEXT_SIZE)()
    eel.generation_finished()()

if __name__ == '__main__':
    eel.start('simple-aichat.html', size=(1000, 850))