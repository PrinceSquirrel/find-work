"""Send one reviewed text through the visible BOSS chat UI, never a private API."""
from __future__ import annotations

import json
from time import monotonic, sleep
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from app.services.browser_job_extractor_service import BrowserJobExtractorService


ORIGIN = "https://www.zhipin.com"
CHAT_PATH = "/web/geek/chat"


def _valid_route(url: str, path: str) -> bool:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}" == ORIGIN and parsed.path == path


class BossGreetingService:
    def __init__(self, browser=None):
        self.browser = browser or BrowserJobExtractorService()

    def send(self, job, text: str) -> dict:
        target = urlsplit(job.url)
        if (job.platform != "boss" or not _valid_route(job.url, target.path)
                or not target.path.startswith("/job_detail/") or not target.path.endswith(".html")
                or not all(str(value).strip() for value in (job.title, job.company, job.city))):
            return {"status": "blocked", "message": "缺少可核对的 BOSS 岗位地址、名称、公司或城市。"}
        if not self.browser.cdp_url:
            return {"status": "blocked", "message": "请先启动求职浏览器并登录 BOSS。"}
        tabs = self.browser._load_tabs()
        platform_tabs = [tab for tab in tabs if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl")
                         and str(tab.get("url", "")).startswith(ORIGIN + "/")]
        # Keep existing chats intact. Prefer the exact source job, then a non-chat tab.
        source = next((tab for tab in platform_tabs if _valid_route(tab["url"], target.path)), None)
        source = source or next((tab for tab in platform_tabs if not _valid_route(tab["url"], CHAT_PATH)), None)
        navigation_started = not source or not _valid_route(source["url"], target.path)
        if not source:
            # Use the same local Chrome endpoint as the existing platform launcher.
            request = Request(f"{self.browser.cdp_url}/json/new?{quote(job.url, safe='')}", method="PUT")
            with urlopen(request, timeout=3) as response:
                source = json.load(response)
            if not source.get("webSocketDebuggerUrl") or not source.get("id"):
                return {"status": "blocked", "message": "无法打开目标岗位标签页，未操作。"}
        evaluate = self.browser.runtime_client.evaluate
        if navigation_started:
            if source in tabs:
                try:
                    evaluate(source["webSocketDebuggerUrl"], self.browser._open_job_script(job.url))
                except ValueError:
                    pass  # The read below determines whether navigation actually happened.
            for _ in range(24):
                current = next((tab for tab in self.browser._load_tabs() if tab.get("id") == source["id"]), None)
                if current and _valid_route(current.get("url", ""), target.path):
                    break
                sleep(0.25)
            else:
                return {"status": "blocked", "message": "未进入目标岗位，请检查平台登录或验证状态。"}
        try:
            opened = evaluate(source["webSocketDebuggerUrl"], _open_conversation_script(target.path))
        except ValueError:
            # Navigation can replace the script context after the click. Never replay it.
            opened = None
        if isinstance(opened, dict) and opened.get("status") == "blocked":
            return opened
        known = {tab.get("id") for tab in tabs}
        deadline = monotonic() + 8
        while monotonic() < deadline:
            chats = [tab for tab in self.browser._load_tabs()
                     if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl")
                     and (tab.get("id") == source.get("id") or tab.get("id") not in known)
                     and _valid_route(tab.get("url", ""), CHAT_PATH)]
            if len(chats) > 1:
                return {"status": "unknown", "message": "打开了多个会话，无法确认目标，未填写招呼语。"}
            if chats:
                # A send evaluation is never retried, even after a lost CDP response.
                result = evaluate(chats[0]["webSocketDebuggerUrl"], _chat_send_script(job, text))
                return result if isinstance(result, dict) else {"status": "unknown"}
            sleep(0.25)
        return {"status": "unknown", "message": "未进入可识别的聊天页。请先核对平台，不要直接重试。"}


_DOM_HELPERS = r"""
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const visible = node => Boolean(node?.isConnected && node.getClientRects().length &&
  getComputedStyle(node).visibility === 'visible');
const plain = node => (node?.innerText ?? node?.textContent ?? '').trim();
const norm = value => value.normalize('NFKC').replace(/\s+/g, '');
const same = (left, right) => !!left && !!right && norm(left) === norm(right);
const blocked = () => /\/(?:captcha|login|security)(?:\/|$)/i.test(location.pathname) ||
  Array.from(document.querySelectorAll('[role=alert], [role=dialog], .dialog-wrap, .toast, .error-tip'))
    .filter(visible).some(node => /验证码|安全验证|请先登录|实名认证|发送失败|操作频繁|沟通上限|沟通受限|暂不能发送/.test(plain(node)));
const outcome = (status, message) => ({status, message});
"""


def _open_conversation_script(path: str) -> str:
    return "(async () => {\n" + _DOM_HELPERS + "const path = " + json.dumps(path) + r""";
for (let attempt = 0; attempt < 24; attempt++) {
  if (blocked()) return outcome('blocked', '平台要求验证或登录，请本人处理。');
  if (location.origin !== 'https://www.zhipin.com' || location.pathname !== path)
    return outcome('blocked', '浏览器没有停在目标岗位，未操作。');
  const matches = [...document.querySelectorAll('a,button,[role=button]')].filter(node =>
    visible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true' &&
    /^(立即沟通|继续沟通)$/.test(plain(node)));
  const leaf = matches.filter(node => !matches.some(other => other !== node && node.contains(other)));
  if (leaf.length === 1) { leaf[0].click(); return outcome('opening', '已尝试进入平台会话。'); }
  if (leaf.length > 1) return outcome('blocked', '岗位有多个沟通入口，未点击。');
  await wait(250);
}
return outcome('blocked', '未找到明确的沟通按钮，未点击。');
})()"""


def _chat_send_script(job, message: str) -> str:
    payload = json.dumps({"path": urlsplit(job.url).path, "title": job.title, "company": job.company,
                          "city": job.city, "text": message}, ensure_ascii=True)
    return "(async () => {\n" + _DOM_HELPERS + "const expected = " + payload + r""";
const onChat = () => location.origin === 'https://www.zhipin.com' && location.pathname === '/web/geek/chat';
const unique = (root, selector) => { const items = [...root.querySelectorAll(selector)].filter(visible); return items.length === 1 ? items[0] : null; };
const active = () => {
  if (!onChat() || blocked()) return null;
  const conversation = unique(document, '.chat-conversation');
  if (!conversation) return null;
  const header = unique(conversation, '.top-info-content');
  if (!header) return null;
  const link = header.querySelector('.chat-position-content a[href*="/job_detail/"]');
  if (link && (link.origin !== location.origin || link.pathname !== expected.path)) return null;
  const company = plain(unique(header, '.base-info > span:not(.base-title)'));
  const city = plain(unique(header, '.position-content .city'));
  const title = plain(unique(header, '.position-content .position-name'));
  if (!same(title, expected.title) || !same(company, expected.company) ||
    !(same(city, expected.city) || (city && norm(expected.city).split(/[·・•]/)[0] === norm(city)))) return null;
  const selected = unique(document, '.chat-user .friend-content.selected');
  const editor = unique(conversation, '.message-controls #chat-input[contenteditable="true"]');
  const send = unique(conversation, '.message-controls button.btn-send');
  return selected && editor && send && plain(send) === '发送' ? {conversation, selected, editor, send} : null;
};
const outgoing = node => [...node.querySelectorAll('.chat-record .message-item.item-my, .chat-record .message-item.item-self')];
const exact = row => (row.querySelector('.text-content')?.innerText ?? '').trim() === expected.text;
const receipt = row => Boolean(row.getAttribute('data-mid') && row.querySelector('.message-status.status-delivery, .message-status.status-read'));
const read = editor => (editor.innerText ?? editor.textContent ?? '').replace(/\r\n/g, '\n');
let state;
for (let attempt = 0; attempt < 24; attempt++) {
  if (!onChat() || blocked()) return outcome('unknown', '平台要求验证或已离开聊天页，未发送自定义招呼语。');
  state = active();
  if (state) break;
  await wait(250);
}
if (!state) return outcome('unknown', '无法核对会话中的岗位、公司及城市，未发送。请在平台核对。');
const prior = outgoing(state.conversation);
if (prior.some(row => exact(row) && receipt(row)))
  return outcome('already_confirmed', '此会话已有相同且获平台确认的招呼语，没有重发。');
if (prior.some(exact) || read(state.editor).trim())
  return outcome('unknown', '已有相同消息待确认或聊天框有草稿，未覆盖、未重发。');
const priorIds = new Set(prior.map(row => row.getAttribute('data-mid')));
const stillHere = () => {
  const now = active();
  return now && now.selected === state.selected && now.conversation === state.conversation && now.editor === state.editor && now.send === state.send;
};
state.editor.focus();
if (!stillHere() || read(state.editor).trim()) return outcome('unknown', '聊天目标或草稿发生变化，未发送。');
state.editor.textContent = expected.text;
state.editor.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: expected.text}));
await wait(200);
if (!stillHere() || state.send.disabled || state.send.classList.contains('disabled') ||
    state.send.getAttribute('aria-disabled') === 'true' || read(state.editor) !== expected.text)
  return outcome('unknown', '平台未接受完整原文或会话发生变化，未点击发送。');
state.send.click();
for (let attempt = 0; attempt < 32; attempt++) {
  if (!stillHere()) break;
  if (outgoing(state.conversation).some(row => exact(row) && receipt(row) && !priorIds.has(row.getAttribute('data-mid'))))
    return outcome('confirmed', '聊天记录显示自定义招呼语原文，平台已确认。');
  await wait(250);
}
return outcome('unknown', '已尝试发送，但未取得该原文的平台回执。请先核对聊天记录，不要重发。');
})()"""
