import asyncio
import json
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from llama_cpp import Llama
import simple_aichat.core as core

router = APIRouter()

async def send_ws_call(ws: WebSocket, func_name: str, *args):
    """Utility to mimic eel.expose() function triggers"""
    await ws.send_json({"type": "call", "func": func_name, "args": args})

@router.get('/', response_class=FileResponse, name='simple_aichat_root')
async def aichat_page():
    return FileResponse(core.BASE_DIR / 'simple-aichat.html')

@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            action = payload.get("action")
            args = payload.get("args",[])
            msg_id = payload.get("id")

            if action == "get_config":
                result = {
                    "MODEL_NAME": core.MODEL_NAME,
                    "FIRST_MESSAGE": core.FIRST_MESSAGE.replace('<ainame>:', '').strip(),
                    "USERNAME": core.USERNAME
                }
                await websocket.send_json({"type": "response", "id": msg_id, "result": result})

            elif action == "init_model":
                try:
                    if core.model is None:
                        def init():
                            if core.model is None:
                                path_str = str(core.MODEL_PATH)
                                core.model = Llama(model_path=path_str, n_ctx=core.CONTEXT_SIZE, verbose=False)
                        await asyncio.to_thread(init)
                    
                    prompt = core.get_prompt()
                    used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
                    await send_ws_call(websocket, "update_tokens", used_tokens, core.CONTEXT_SIZE)
                    await websocket.send_json({"type": "response", "id": msg_id, "result": True})
                except Exception as e:
                    print(f"Model Load Error: {e}")
                    await websocket.send_json({"type": "response", "id": msg_id, "result": False})

            elif action == "update_names":
                core.USERNAME = args[0].strip()
                core.MODEL_NAME = args[1].strip()
                await asyncio.to_thread(core.trim_history)
                if core.model is not None:
                    prompt = core.get_prompt()
                    used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
                    await send_ws_call(websocket, "update_tokens", used_tokens, core.CONTEXT_SIZE)
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

            elif action == "set_chat_history":
                core.chat_history = args[0]
                await asyncio.to_thread(core.trim_history)
                if core.model is not None:
                    prompt = core.get_prompt()
                    used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
                    await send_ws_call(websocket, "update_tokens", used_tokens, core.CONTEXT_SIZE)
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

            elif action == "clear_history":
                core.chat_history =[]
                if core.model is not None:
                    prompt = core.get_prompt()
                    used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
                    await send_ws_call(websocket, "update_tokens", used_tokens, core.CONTEXT_SIZE)
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

            elif action == "interrupt":
                core.stop_generation = True
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

            elif action == "send_message":
                user_text = args[0]
                if not user_text.strip():
                    await send_ws_call(websocket, "generation_finished")
                    await websocket.send_json({"type": "response", "id": msg_id, "result": None})
                    continue

                core.chat_history.append({"role": "<username>", "text": user_text})
                await asyncio.to_thread(core.trim_history)

                prompt = core.get_prompt() + f"{core.MODEL_NAME}: "
                stop_words = [f'{core.USERNAME}:', f'{core.MODEL_NAME}:']

                used_tokens = len(core.model.tokenize(prompt.encode('utf-8'), add_bos=False))
                await send_ws_call(websocket, "update_tokens", used_tokens, core.CONTEXT_SIZE)

                response_text = ""
                is_first = True
                core.stop_generation = False
                
                # Setup Non-Blocking queue for generation stream
                queue = asyncio.Queue()
                loop = asyncio.get_running_loop()

                def generate_loop():
                    try:
                        for chunk in core.model(prompt, stop=stop_words, max_tokens=core.MAX_TOKENS, stream=True):
                            if core.stop_generation:
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

                core.chat_history.append({"role": "<ainame>", "text": response_text})

                final_prompt = core.get_prompt()
                used_tokens = len(core.model.tokenize(final_prompt.encode('utf-8'), add_bos=False))
                await send_ws_call(websocket, "update_tokens", used_tokens, core.CONTEXT_SIZE)
                await send_ws_call(websocket, "generation_finished")
                
                await websocket.send_json({"type": "response", "id": msg_id, "result": None})

    except WebSocketDisconnect:
        pass

@router.get('/{rest_of_path:path}', include_in_schema=False)
async def aichat_fallback(request: Request):
    return RedirectResponse(url=request.url_for('simple_aichat_root'))