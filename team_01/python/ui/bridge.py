from __future__ import annotations
"""Front-end glue extracted from app.py: the postMessage→query-param selection
bridge, and the floating Ask-Agent drawer markup."""

SELECTION_BRIDGE_JS = """
<script>
(function(){
  if(window._selBridgeReady)return;window._selBridgeReady=true;
  function _rerun(url){
    window.parent.history.replaceState(null,'',url.toString());
    window.parent.dispatchEvent(new PopStateEvent('popstate',{state:null}));
    setTimeout(function(){window.parent.dispatchEvent(new PopStateEvent('popstate',{state:null}));},40);
  }
  window.parent.addEventListener('message',function(ev){
    if(!ev.data||!ev.data.type)return;
    var url=new URL(window.parent.location.href);
    if(ev.data.type==='selectElement'){
      var eid=ev.data.elementId||'';
            var lvl=ev.data.level||'';
      var prev=url.searchParams.get('_sel')||'';
            var prevLvl=url.searchParams.get('_lvl')||'';
            if(eid===prev && lvl===prevLvl)return;
      if(eid){url.searchParams.set('_sel',eid);}else{url.searchParams.delete('_sel');}
            if(lvl){url.searchParams.set('_lvl',lvl);}else{url.searchParams.delete('_lvl');}
      _rerun(url);
    } else if(ev.data.type==='toolbar'){
      url.searchParams.set('_tb_'+ev.data.key, ev.data.val);
      _rerun(url);
    } else if(ev.data.type==='agentQuery'){
      url.searchParams.set('_aq', ev.data.text.slice(0,600));
      _rerun(url);
    }
  });
})();
</script>"""


def agent_drawer_html(is_light: bool, hist_js: str) -> str:
    _drawer_bg    = "#ffffff" if is_light else "#0d2828"
    _drawer_bord  = "#c0d8d8" if is_light else "#1a4040"
    _drawer_text  = "#1a2a30" if is_light else "#c8eeed"
    _drawer_acc   = "#088a87" if is_light else "#2ac0c0"
    _drawer_mut   = "#5a7070" if is_light else "#5a9090"
    _drawer_btn_c = "#ffffff" if is_light else "#071a1a"
    _hist_js = hist_js
    return f"""<script>
(function(){{
  var par = window.parent.document;
  var win = window.parent;
  var _hh = {_hist_js};

  // Always re-inject or update styles so they survive Streamlit hot-reloads
  var _sid = 'agent-drawer-styles';
  var _oldStyle = par.getElementById(_sid);
  if(_oldStyle) _oldStyle.remove();
  var style = par.createElement('style');
  style.id = _sid;
  style.textContent =
    '#agent-drawer{{position:fixed;top:50%;right:0;transform:translateY(-50%) translateX(100%);transition:transform 0.28s cubic-bezier(.4,0,.2,1);width:290px;z-index:99999;background:{_drawer_bg};border:1px solid {_drawer_bord};border-right:none;border-radius:12px 0 0 12px;box-shadow:-6px 0 24px rgba(0,0,0,0.4);font-family:\'Suisse Intl\',\'Inter\',sans-serif;}}'
    +'#agent-drawer.open{{transform:translateY(-50%) translateX(0);}}'
    +'#agent-drawer-tab{{position:absolute;left:-30px;top:50%;transform:translateY(-50%);width:30px;height:52px;background:{_drawer_bg};border:1px solid {_drawer_bord};border-right:none;border-radius:10px 0 0 10px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:14px;color:{_drawer_acc};user-select:none;}}'
    +'#agent-drawer-body{{padding:14px 14px 12px;}}'
    +'#agent-drawer-title{{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:{_drawer_acc};margin-bottom:10px;}}'
    +'#agent-drawer-history{{max-height:180px;overflow-y:auto;font-size:11px;color:{_drawer_mut};margin-bottom:10px;line-height:1.5;}}'
    +'#agent-drawer-history .dq{{color:{_drawer_text};font-weight:600;}}'
    +'#agent-drawer-input{{width:100%;box-sizing:border-box;background:rgba(128,128,128,0.08);border:1px solid {_drawer_bord};border-radius:6px;color:{_drawer_text};font-size:12px;padding:8px 10px;resize:none;font-family:inherit;margin-bottom:8px;}}'
    +'#agent-drawer button{{width:100%;background:{_drawer_acc};color:{_drawer_btn_c};border:none;border-radius:6px;font-size:12px;font-weight:700;padding:7px;cursor:pointer;font-family:inherit;}}';
  par.head.appendChild(style);

  // Update history if panel already exists
  var existing = par.getElementById('agent-drawer');
  if(existing){{
    var he = par.getElementById('agent-drawer-history');
    if(he) he.innerHTML = _hh;
    return;
  }}

  // Build panel — note: onclick runs in parent page context so call functions directly
  var panel = par.createElement('div');
  panel.id = 'agent-drawer';
  panel.innerHTML =
    '<div id="agent-drawer-tab" onclick="toggleDrawer()">&#9664;</div>'
    +'<div id="agent-drawer-body">'
    +'<div id="agent-drawer-title">Ask Agent</div>'
    +'<div id="agent-drawer-history"></div>'
    +'<textarea id="agent-drawer-input" placeholder="Ask about this design…" rows="3"></textarea>'
    +'<button onclick="submitDrawerQuery()">Send ›</button>'
    +'</div>';
  par.body.appendChild(panel);
  par.getElementById('agent-drawer-history').innerHTML = _hh;

  // Define functions on parent window (global scope of the Streamlit page)
  win._drawerOpen = false;
  win.toggleDrawer = function(){{
    win._drawerOpen = !win._drawerOpen;
    par.getElementById('agent-drawer').classList.toggle('open', win._drawerOpen);
    par.getElementById('agent-drawer-tab').innerHTML = win._drawerOpen ? '&#9654;' : '&#9664;';
  }};
  win.submitDrawerQuery = function(){{
    var txt = par.getElementById('agent-drawer-input').value.trim();
    if(!txt) return;
    par.getElementById('agent-drawer-input').value = '';
    var h = par.getElementById('agent-drawer-history');
    h.innerHTML += '<div class="dq">You: '+txt.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</div><div>Processing…</div>';
    h.scrollTop = h.scrollHeight;
    win.postMessage({{type:'agentQuery',text:txt}}, '*');
  }};
}})();
</script>"""
