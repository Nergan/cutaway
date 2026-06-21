import sys
from pathlib import Path
from fastapi import FastAPI

app = FastAPI(title="Simple AI Chat Standalone")
BASE_DIR = Path(__file__).parent

from simple_aichat import router
app.include_router(router, prefix='/simple-aichat')

@app.get("/")
def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url='/simple-aichat')

# Conditionally bind Eel logic for the Desktop App runtime
try:
    import eel
    import core
    
    eel.init(str(BASE_DIR))

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
        core.chat_history = []
        if core.model is not None:
            prompt = core.get_prompt()
            used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
            eel.update_tokens(used_tokens, core.CONTEXT_SIZE)()

    @eel.expose
    def init_model():
        try:
            if core.model is None:
                from llama_cpp import Llama
                core.model = Llama(model_path=str(core.MODEL_PATH), n_ctx=core.CONTEXT_SIZE, verbose=False)
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
        stop_words = [f'{core.USERNAME}:', f'{core.MODEL_NAME}:']
        
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

except ImportError:
    pass # Eel is ignored seamlessly in Web-Only environments

if __name__ == '__main__':
    if "--web" in sys.argv:
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000)
    else:
        if 'eel' in sys.modules:
            eel.start('simple-aichat.html', size=(1000, 850))
        else:
            print("Eel is not installed. Run 'python main.py --web'")