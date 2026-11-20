import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from app.services.boss_greeting_service import BossGreetingService, _chat_send_script, _open_conversation_script


JOB = SimpleNamespace(platform="boss", url="https://www.zhipin.com/job_detail/fixture.html",
                      title="产品实习", company="合成公司", city="上海·浦东")
MESSAGE = "您好，想聊聊用户调研。\n这是我审过的文案。"


@pytest.mark.parametrize("scenario,status,clicks", [
    ("delivered", "confirmed", 1), ("incoming", "unknown", 1), ("pending", "unknown", 1),
    ("duplicate", "already_confirmed", 0), ("changed", "unknown", 0), ("draft", "unknown", 0),
    ("wrong-job", "unknown", 0), ("captcha", "unknown", 0), ("different-link", "unknown", 0),
])
def test_visible_chat_requires_identity_exact_outgoing_and_receipt(scenario, status, clicks):
    if not shutil.which("node"):
        pytest.skip("Node is required to run the browser script")
    fixture = r"""
const [scenario, script, text] = JSON.parse(require('fs').readFileSync(0, 'utf8'));
let clicks = 0, filled = '';
const node = (text = '') => ({innerText: text, isConnected: true, getClientRects: () => [1]});
const selected = node(), other = node();
let switched = false;
const editor = node(scenario === 'draft' ? '手动草稿' : '');
editor.focus = () => {};
editor.dispatchEvent = event => { filled = event.data; editor.innerText = editor.textContent; switched = scenario === 'changed'; };
const send = node('发送');
send.getAttribute = () => null;
send.classList = {contains: () => false};
send.click = () => { clicks++; };
const row = (id, delivered) => ({
  getAttribute: key => key === 'data-mid' ? id : null,
  querySelector: selector => selector === '.text-content' ? node(text) : delivered ? node() : null,
});
const header = node();
header.querySelector = () => scenario === 'different-link' ? {origin: 'https://www.zhipin.com', pathname: '/job_detail/other.html'} : null;
header.querySelectorAll = selector => [node(selector.includes('base-info') ? '合成公司' : selector.endsWith('.city') ? '上海' : scenario === 'wrong-job' ? '其他岗位' : '产品实习')];
const conversation = node();
conversation.querySelectorAll = selector => {
  if (selector === '.top-info-content') return [header];
  if (selector.includes('chat-input')) return [editor];
  if (selector.includes('button.btn-send')) return [send];
  if (scenario === 'duplicate') return [row('prior', true)];
  return clicks && ['delivered', 'pending'].includes(scenario) ? [row('new', scenario === 'delivered')] : [];
};
global.location = {origin: 'https://www.zhipin.com', pathname: '/web/geek/chat'};
global.document = {querySelectorAll: selector => selector === '.chat-conversation' ? [conversation]
  : selector.includes('.friend-content.selected') ? [switched ? other : selected]
  : scenario === 'captcha' ? [node('安全验证')] : []};
global.getComputedStyle = () => ({visibility: 'visible'});
global.InputEvent = class { constructor(_, params) { Object.assign(this, params); } };
global.setTimeout = callback => queueMicrotask(callback);
(async()=>{ const result = await eval(script); console.log(JSON.stringify({status: result.status, clicks, filled})); })();
"""
    result = subprocess.run(["node", "-e", fixture], input=json.dumps([scenario, _chat_send_script(JOB, MESSAGE), MESSAGE]),
                            encoding="utf-8", capture_output=True, timeout=10, check=True)
    payload = json.loads(result.stdout)
    assert (payload["status"], payload["clicks"]) == (status, clicks)
    assert payload["filled"] == (MESSAGE if clicks or scenario == "changed" else "")


def test_navigation_action_is_once_and_ignores_preexisting_unrelated_chat():
    src = {"id": "job", "type": "page", "url": JOB.url, "webSocketDebuggerUrl": "job-socket"}
    unrelated = {"id": "other", "type": "page", "url": "https://www.zhipin.com/web/geek/chat", "webSocketDebuggerUrl": "other-socket"}
    new = {**unrelated, "id": "new", "webSocketDebuggerUrl": "new-socket"}
    lists = iter([[src, unrelated], [src, unrelated, new]])
    calls = []

    def evaluate(socket, script):
        calls.append(socket)
        if socket == "job-socket":
            assert script == _open_conversation_script("/job_detail/fixture.html")
            raise ValueError("navigation replaced context")
        assert script == _chat_send_script(JOB, MESSAGE)
        return {"status": "confirmed"}

    browser = SimpleNamespace(cdp_url="local", _load_tabs=lambda: next(lists), runtime_client=SimpleNamespace(evaluate=evaluate))
    assert BossGreetingService(browser).send(JOB, MESSAGE)["status"] == "confirmed"
    assert calls == ["job-socket", "new-socket"]
