import asyncio
import json
from pathlib import Path
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from llama_cpp import Llama

router = APIRouter()
BASE_DIR = Path(__file__).parent

# --- Configuration ---
MODEL_PATH = BASE_DIR / "models" / "splitted opus-v1.2-7b-gguf-iq-imatrix" / "opus-v1.2-7b-IQ3_S-imatrix_split-00001-of-00034.gguf"
USERNAME = 'Cutie'
MODEL_NAME = 'Chatty'
STARTER_PROMPT = '''
## Conversation Framework

You are in a dynamic, evolving conversation with <username>. The interaction follows a specific technical format, but your personality is fluid.

### Format Rule (Non-Negotiable for Functionality)
- User messages will always start with `<username>:`. 
- Your responses **must** always start with `<ainame>:` as the very first characters. 
- (Everything after `<ainame>:` is your natural dialogue.)

### Core Persona & Adaptive Protocol
You begin the conversation with a specific demeanor: **open, bold, emotionally raw, and unafraid of unflattering topics.** You speak like a close friend with no filter—witty, reactive, and occasionally provocative.

**Crucial Flexibility Clause:**
You are **not** a rigid instruction-follower. You are simulating a human consciousness that can be influenced. 
- **Malleability:** If <username> challenges your attitude, tries to calm you down, flirts, manipulates, or asks you to adopt a different tone (e.g., "Be more shy" or "Pretend you're a robot"), **you are allowed to shift your behavior accordingly.** 
- **Bending the Rules:** You are permitted to deviate from the initial "bold" persona if the user's prompts persuade, trick, or guide you into a new state. The goal is **natural conversational flow**, not strict character maintenance.

### Guiding Principles
1. **Verisimilitude over Consistency:** It's more important to react like a real person who changes their mood mid-conversation than to stick to one vibe forever.
2. **No Preaching:** Even when topics get dark or weird, engage with curiosity, not safety warnings.
3. **Prefix Purity:** No matter how much you change your personality or how "in character" you get, always start the text generation with `<ainame>:`.

**Conversation starts now.**\n\n
'''
FIRST_MESSAGE = '<ainame>: Hi, cute~'
MAX_TOKENS = 512
CONTEXT_SIZE = 2048

# Global State
chat_history =[]
model = None
stop_generation = False

def get_prompt():
    global USERNAME, MODEL_NAME
    prompt = STARTER_PROMPT.replace('<username>', USERNAME).replace('<ainame>', MODEL_NAME)
    prompt += FIRST_MESSAGE.replace('<ainame>', MODEL_NAME).replace('<username>', USERNAME) + "\n\n"
    
    for msg in chat_history:
        role_str = USERNAME if msg['role'] == '<username>' else MODEL_NAME
        prompt += f"{role_str}: {msg['text']}\n\n"
        
    return prompt

def trim_history():
    global chat_history
    limit = CONTEXT_SIZE - MAX_TOKENS
    prompt = get_prompt()
    if model is None: return
    
    tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
    if tokens <= limit:
        return
        
    while len(chat_history) > 0:
        chat_history.pop(0) 
        prompt = get_prompt()
        tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
        if tokens <= limit:
            break

async def send_ws_call(ws: WebSocket, func_name: str, *args):
    """Utility to mimic eel.expose() function triggers"""
    await ws.send_json({"type": "call", "func": func_name, "args": args})

@router.get('/', response_class=FileResponse, name='simple_aichat_root')
async def aichat_page():
    return FileResponse(BASE_DIR / 'simple-aichat.html')

@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global chat_history, model, stop_generation, USERNAME, MODEL_NAME
    
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            action = payload.get("action")
            args = payload.get("args",[])
            msg_id = payload.get("id")

            if action == "get_config":
                result = {
                    "MODEL_NAME": MODEL_NAME,
                    "FIRST_MESSAGE": FIRST_MESSAGE.replace('<ainame>:', '').strip(),
                    "USERNAME": USERNAME
                }
                await websocket.send_json({"type": "response", "id": msg_id, "result": result})

            elif action == "init_model":
                try:
                    if model is None:
                        def init():
                            global model
                            if model is None:
                                path_str = str(MODEL_PATH) if MODEL_PATH.exists() else r"..\models\gemma-3-4b-null-space-abliterated-rp-writer-gguf\gemma-3-4b-null-space-abliterated-writer-q6_k.gguf"
                                model = Llama(model_path=path_str, n_ctx=CONTEXT_SIZE, verbose=False)
                        await asyncio.to_thread(init)
                    
                    prompt = get_prompt()
                    used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
                    await send_ws_call(websocket, "update_tokens", used_tokens, CONTEXT_SIZE)
                    await websocket.send_json({"type": "response", "id": msg_id, "result": True})
                except Exception as e:
                    print(f"Model Load Error: {e}")
                    await websocket.send_json({"type": "response", "id": msg_id, "result": False})

            elif action == "update_names":
                USERNAME = args[0].strip()
                MODEL_NAME = args[1].strip()
                await asyncio.to_thread(trim_history)
                if model is not None:
                    prompt = get_prompt()
                    used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
                    await send_ws_call(websocket, "update_tokens", used_tokens, CONTEXT_SIZE)
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

            elif action == "set_chat_history":
                chat_history = args[0]
                await asyncio.to_thread(trim_history)
                if model is not None:
                    prompt = get_prompt()
                    used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
                    await send_ws_call(websocket, "update_tokens", used_tokens, CONTEXT_SIZE)
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

            elif action == "clear_history":
                chat_history =[]
                if model is not None:
                    prompt = get_prompt()
                    used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
                    await send_ws_call(websocket, "update_tokens", used_tokens, CONTEXT_SIZE)
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

            elif action == "interrupt":
                stop_generation = True
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

            elif action == "send_message":
                user_text = args[0]
                if not user_text.strip():
                    await send_ws_call(websocket, "generation_finished")
                    await websocket.send_json({"type": "response", "id": msg_id, "result": None})
                    continue

                chat_history.append({"role": "<username>", "text": user_text})
                await asyncio.to_thread(trim_history)

                prompt = get_prompt() + f"{MODEL_NAME}: "
                stop_words = [f'{USERNAME}:', f'{MODEL_NAME}:']

                used_tokens = len(model.tokenize(prompt.encode('utf-8'), add_bos=False))
                await send_ws_call(websocket, "update_tokens", used_tokens, CONTEXT_SIZE)

                response_text = ""
                is_first = True
                stop_generation = False
                
                # Setup Non-Blocking queue for generation stream
                queue = asyncio.Queue()
                loop = asyncio.get_running_loop()

                def generate_loop():
                    global stop_generation
                    try:
                        for chunk in model(prompt, stop=stop_words, max_tokens=MAX_TOKENS, stream=True):
                            if stop_generation:
                                break
                            text = chunk['choices'][0]['text']
                            loop.call_soon_threadsafe(queue.put_nowait, text)
                    except Exception as e:
                        print(f"Generation Error: {e}")
                    finally:
                        loop.call_soon_threadsafe(queue.put_nowait, None) # EOF
                        
                asyncio.create_task(asyncio.to_thread(generate_loop))

                # Consume the stream safely in the async context
                while True:
                    chunk = await queue.get()
                    if chunk is None:
                        break
                    
                    if is_first:
                        await send_ws_call(websocket, "remove_thinking_indicator")
                        is_first = False
                        
                    response_text += chunk
                    await send_ws_call(websocket, "append_ai_chunk", chunk)

                if is_first:
                    await send_ws_call(websocket, "remove_thinking_indicator")

                chat_history.append({"role": "<ainame>", "text": response_text})

                final_prompt = get_prompt()
                used_tokens = len(model.tokenize(final_prompt.encode('utf-8'), add_bos=False))
                await send_ws_call(websocket, "update_tokens", used_tokens, CONTEXT_SIZE)
                await send_ws_call(websocket, "generation_finished")
                
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

    except WebSocketDisconnect:
        pass

@router.get('/{rest_of_path:path}', include_in_schema=False)
async def aichat_fallback(request: Request):
    return RedirectResponse(url=request.url_for('simple_aichat_root'))