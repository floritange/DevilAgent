# server.py
import json
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from main import DevilAgent, logger
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="DevilAgent")
agent = DevilAgent(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)


class SearchReq(BaseModel):
    enabled: bool


@app.post("/api/search")
async def set_search(req: SearchReq):
    agent.set_search(req.enabled)
    return {"search_enabled": agent.use_web_search}


class ChatReq(BaseModel):
    message: str


class ModeReq(BaseModel):
    devil_mode: bool


@app.post("/api/chat")
async def chat(req: ChatReq):
    async def gen():
        try:
            async for chunk in agent.chat(req.message):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error(f"SSE error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/mode")
async def set_mode(req: ModeReq):
    agent.set_mode(req.devil_mode)
    return {"devil_mode": agent.devil_mode}


@app.post("/api/clear")
async def clear():
    agent.clear()
    return {"status": "ok"}


@app.get("/api/status")
async def status():
    return {
        "devil_mode": agent.devil_mode,
        "search_enabled": agent.use_web_search,
        "skills": [s["name"] for s in agent.skills_metadata],
        "history": len(agent.history),
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>DevilAgent</title>
<script src="https://cdn.jsdelivr.net/npm/marked@4/marked.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/github-markdown-css@5/github-markdown-light.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:linear-gradient(135deg,#e0f2fe 0%,#f0fdf4 50%,#fdf2f8 100%);min-height:100vh;color:#334155}
.container{max-width:900px;margin:0 auto;padding:20px;display:flex;flex-direction:column;height:100vh}
.header{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;background:rgba(255,255,255,0.8);backdrop-filter:blur(10px);border-radius:16px;margin-bottom:20px;box-shadow:0 4px 20px rgba(0,0,0,0.05);flex-shrink:0}
.header h1{font-size:1.5em;background:linear-gradient(135deg,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.controls{display:flex;gap:10px}
.toggle-btn{padding:10px 18px;border:none;border-radius:12px;cursor:pointer;font-size:0.9em;font-weight:500;transition:all 0.3s;box-shadow:0 2px 10px rgba(0,0,0,0.1)}
.toggle-btn:hover{transform:translateY(-2px);box-shadow:0 4px 15px rgba(0,0,0,0.15)}
.mode-btn.normal{background:linear-gradient(135deg,#a7f3d0,#6ee7b7);color:#065f46}
.mode-btn.devil{background:linear-gradient(135deg,#fca5a5,#f87171);color:#7f1d1d}
.search-btn.on{background:linear-gradient(135deg,#93c5fd,#60a5fa);color:#1e3a8a}
.search-btn.off{background:#e2e8f0;color:#64748b}
.chat-box{background:rgba(255,255,255,0.7);backdrop-filter:blur(10px);border-radius:16px;flex:1;overflow-y:auto;padding:20px;margin-bottom:20px;box-shadow:0 4px 20px rgba(0,0,0,0.05);min-height:200px}
.msg{margin-bottom:12px;padding:14px 18px;border-radius:16px;max-width:85%;line-height:1.6;animation:fadeIn 0.3s;word-wrap:break-word}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.msg.user{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;margin-left:auto;border-bottom-right-radius:4px;white-space:pre-wrap}
.msg.ai{background:#fff;color:#334155;border:1px solid #e2e8f0;border-bottom-left-radius:4px;max-width:90%}
.msg.ai .markdown-body{background:transparent;font-size:14px}
.msg.ai .markdown-body pre{overflow-x:auto;max-width:100%}
.msg.ai .markdown-body code{word-break:break-all}
.stages-container{background:linear-gradient(135deg,#fefce8,#fef9c3);border:1px solid #fde047;border-radius:12px;padding:12px 16px;margin-bottom:12px;font-size:0.85em}
.stages-container .stage-title{font-weight:600;color:#a16207;margin-bottom:8px}
.stages-container .stage-item{color:#92400e;padding:4px 0;display:flex;align-items:center;gap:8px}
.stages-container .stage-item::before{content:'';width:6px;height:6px;background:#f59e0b;border-radius:50%;flex-shrink:0}
.stages-container .stage-item.done::before{background:#22c55e}
.stages-container .stage-item.current::before{animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
.input-area{display:flex;gap:12px;align-items:flex-end;flex-shrink:0}
.input-area textarea{flex:1;padding:12px 16px;border:2px solid #e2e8f0;border-radius:14px;background:#fff;font-size:1em;font-family:inherit;resize:none;min-height:50px;max-height:150px;overflow-y:auto;line-height:1.5}
.input-area textarea:focus{outline:none;border-color:#93c5fd}
.input-area .btn-group{display:flex;flex-direction:column;gap:8px}
.input-area button{padding:12px 20px;border:none;border-radius:12px;font-size:0.95em;font-weight:500;cursor:pointer;white-space:nowrap}
.send-btn{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff}
.send-btn:hover:not(:disabled){opacity:0.9}
.send-btn:disabled{background:#cbd5e1;cursor:not-allowed}
.clear-btn{background:#f1f5f9;color:#64748b}
.clear-btn:hover{background:#e2e8f0}
.status{font-size:0.75em;color:#94a3b8;text-align:center;margin-top:12px;flex-shrink:0}
.hint{font-size:0.7em;color:#94a3b8;margin-top:4px;text-align:right}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>DevilAgent</h1>
<div class="controls">
<button id="searchBtn" class="toggle-btn search-btn on" onclick="toggleSearch()">Web Search</button>
<button id="modeBtn" class="toggle-btn mode-btn devil" onclick="toggleMode()">Devil Mode</button>
</div>
</div>
<div id="chatBox" class="chat-box"></div>
<div class="input-area">
<textarea id="input" placeholder="Type a message... (Enter to send, Shift+Enter for new line)" rows="2" onkeydown="handleKey(event)"></textarea>
<div class="btn-group">
<button onclick="send()" id="sendBtn" class="send-btn">Send</button>
<button class="clear-btn" onclick="clearChat()">Clear</button>
</div>
</div>
<div class="hint">Enter: send | Shift+Enter: new line</div>
<div class="status" id="status">Loading...</div>
</div>

<script>
var devil = true;
var search = true;

function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
    }
    autoResize(e.target);
}

function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 150) + 'px';
}

function renderMd(text) {
    try {
        if (typeof marked !== 'undefined' && marked.parse) {
            return marked.parse(text);
        }
        return text;
    } catch (err) {
        console.error('Markdown error:', err);
        return text;
    }
}

function toggleMode() {
    devil = !devil;
    fetch('/api/mode', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({devil_mode: devil})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        var b = document.getElementById('modeBtn');
        b.className = 'toggle-btn mode-btn ' + (d.devil_mode ? 'devil' : 'normal');
        b.textContent = d.devil_mode ? 'Devil Mode' : 'Normal Mode';
        updateStatus();
    })
    .catch(function(e) { console.error('Mode error:', e); });
}

function toggleSearch() {
    search = !search;
    fetch('/api/search', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled: search})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        var b = document.getElementById('searchBtn');
        b.className = 'toggle-btn search-btn ' + (d.search_enabled ? 'on' : 'off');
        b.textContent = d.search_enabled ? 'Web Search' : 'Offline';
        updateStatus();
    })
    .catch(function(e) { console.error('Search error:', e); });
}

function addMsg(txt, isUser) {
    var box = document.getElementById('chatBox');
    var div = document.createElement('div');
    div.className = 'msg ' + (isUser ? 'user' : 'ai');
    if (isUser) {
        div.textContent = txt;
    } else {
        div.innerHTML = '<div class="markdown-body"></div>';
    }
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

function createStagesContainer() {
    var old = document.getElementById('stagesContainer');
    if (old) old.remove();
    var box = document.getElementById('chatBox');
    var div = document.createElement('div');
    div.className = 'stages-container';
    div.id = 'stagesContainer';
    div.innerHTML = '<div class="stage-title">Processing</div><div class="stages-list"></div>';
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

function addStageItem(txt) {
    var container = document.getElementById('stagesContainer');
    if (!container) container = createStagesContainer();
    var list = container.querySelector('.stages-list');
    var prev = list.querySelector('.stage-item.current');
    if (prev) {
        prev.classList.remove('current');
        prev.classList.add('done');
    }
    var item = document.createElement('div');
    item.className = 'stage-item current';
    item.textContent = txt;
    list.appendChild(item);
    document.getElementById('chatBox').scrollTop = document.getElementById('chatBox').scrollHeight;
}

function finalizeStages() {
    var container = document.getElementById('stagesContainer');
    if (container) {
        var curr = container.querySelector('.stage-item.current');
        if (curr) {
            curr.classList.remove('current');
            curr.classList.add('done');
        }
        container.querySelector('.stage-title').innerHTML = 'Completed';
    }
}

function send() {
    var inp = document.getElementById('input');
    var msg = inp.value.trim();
    if (!msg) return;
    
    inp.value = '';
    inp.style.height = 'auto';
    document.getElementById('sendBtn').disabled = true;
    addMsg(msg, true);
    
    var aiDiv = null;
    var rawContent = '';
    
    fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: msg})
    })
    .then(function(res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';
        
        function read() {
            return reader.read().then(function(result) {
                if (result.done) {
                    finalizeStages();
                    document.getElementById('sendBtn').disabled = false;
                    updateStatus();
                    return;
                }
                buffer += decoder.decode(result.value, {stream: true});
                var lines = buffer.split('\\n');
                buffer = lines.pop() || '';
                
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (line.indexOf('data: ') === 0) {
                        try {
                            var d = JSON.parse(line.substring(6));
                            if (d.content) {
                                if (d.content.indexOf('[STAGE]') === 0) {
                                    addStageItem(d.content.substring(7).trim());
                                } else {
                                    if (!aiDiv) {
                                        finalizeStages();
                                        aiDiv = addMsg('', false);
                                    }
                                    rawContent += d.content;
                                    aiDiv.querySelector('.markdown-body').innerHTML = renderMd(rawContent);
                                    document.getElementById('chatBox').scrollTop = document.getElementById('chatBox').scrollHeight;
                                }
                            }
                            if (d.error) {
                                if (!aiDiv) aiDiv = addMsg('', false);
                                rawContent += '\\n\\n**Error:** ' + d.error;
                                aiDiv.querySelector('.markdown-body').innerHTML = renderMd(rawContent);
                            }
                        } catch (e) {
                            console.error('Parse error:', e);
                        }
                    }
                }
                return read();
            });
        }
        return read();
    })
    .catch(function(e) {
        console.error('Fetch error:', e);
        if (!aiDiv) aiDiv = addMsg('', false);
        aiDiv.querySelector('.markdown-body').innerHTML = '<p style="color:red">[Error: ' + e.message + ']</p>';
        finalizeStages();
        document.getElementById('sendBtn').disabled = false;
        updateStatus();
    });
}

function clearChat() {
    fetch('/api/clear', {method: 'POST'});
    document.getElementById('chatBox').innerHTML = '';
    updateStatus();
}

function updateStatus() {
    fetch('/api/status')
    .then(function(r) { return r.json(); })
    .then(function(d) {
        devil = d.devil_mode;
        var mBtn = document.getElementById('modeBtn');
        mBtn.className = 'toggle-btn mode-btn ' + (devil ? 'devil' : 'normal');
        mBtn.textContent = devil ? 'Devil Mode' : 'Normal Mode';
        search = d.search_enabled;
        var sBtn = document.getElementById('searchBtn');
        sBtn.className = 'toggle-btn search-btn ' + (search ? 'on' : 'off');
        sBtn.textContent = search ? 'Web Search' : 'Offline';
        document.getElementById('status').textContent = 
            'Mode: ' + (d.devil_mode ? 'Devil' : 'Normal') + 
            ' | Search: ' + (d.search_enabled ? 'ON' : 'OFF') + 
            ' | History: ' + d.history + ' msgs';
    })
    .catch(function(e) {
        document.getElementById('status').textContent = 'Error: ' + e.message;
    });
}

// Initialize
if (typeof marked !== 'undefined' && marked.setOptions) {
    marked.setOptions({breaks: true, gfm: true});
}
updateStatus();
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8321, reload=True)
