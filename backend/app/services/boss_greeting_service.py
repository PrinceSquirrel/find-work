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
                or not job.title.strip()):
            return {"status": "blocked", "message": "缺少可核对的 BOSS 岗位地址或名称。"}
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
        # The listing card may have stale metadata (including salary mislabeled as company).
        # Bind the chat to the currently rendered details, not to that cached field.
        identity = evaluate(source["webSocketDebuggerUrl"], _job_identity_script(target.path, job.title))
        if not isinstance(identity, dict) or identity.get("status") != "verified":
            return {"status": "blocked", "message": identity.get("message", "无法核对目标岗位，未点击。")
                    if isinstance(identity, dict) else "无法核对目标岗位，未点击。"}
        try:
            opened = evaluate(source["webSocketDebuggerUrl"], _open_conversation_script(target.path, identity))
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
                result = evaluate(chats[0]["webSocketDebuggerUrl"], _chat_send_script(target.path, identity, text))
                if not isinstance(result, dict):
                    return {"status": "unknown"}
                if result.get("status") in {"confirmed", "already_confirmed"}:
                    return {**result, "verified_company": identity["companies"][0], "verified_city": identity["city"]}
                return result
            sleep(0.25)
        return {"status": "unknown", "message": "未进入可识别的聊天页。请先核对平台，不要直接重试。"}


_DOM_HELPERS = r"""
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const visible = node => Boolean(node?.isConnected && node.getClientRects().length &&
  getComputedStyle(node).visibility === 'visible');
const plain = node => (node?.innerText ?? node?.textContent ?? '').trim();
const norm = value => value.normalize('NFKC').replace(/\s+/g, '');
const same = (left, right) => !!left && !!right && norm(left) === norm(right);
const sameCity = (left, right) => !!left && !!right && norm(left).replace(/市$/, '') === norm(right).replace(/市$/, '');
const unique = (root, selector) => { const items = [...root.querySelectorAll(selector)].filter(visible); return items.length === 1 ? items[0] : null; };
const blocked = () => /\/(?:captcha|login|security)(?:\/|$)/i.test(location.pathname) ||
  Array.from(document.querySelectorAll('[role=alert], [role=dialog], .dialog-wrap, .toast, .error-tip'))
    .filter(visible).some(node => /验证码|安全验证|请先登录|实名认证|发送失败|操作频繁|沟通上限|沟通受限|暂不能发送/.test(plain(node)));
const outcome = (status, message) => ({status, message});
"""

_DETAIL_IDENTITY = r"""
const directText = node => node ? Array.from(node.childNodes).filter(child => child.nodeType === 3)
  .map(child => child.textContent).join(' ').trim() : '';
const companyName = value => value && value.length <= 120 && !/^(未知|待核对|加载中|面议|薪资面议|[\d.]+\s*[-–—~到]\s*[\d.]+\s*[kK万元千].*)$/.test(value);
const describeJob = () => {
  const heading = unique(document, '.info-primary .name h1');
  const title = heading?.getAttribute('title')?.trim() || plain(heading);
  const city = plain(unique(document, '.info-primary .text-city'));
  const recruiter = directText(unique(document, '.job-boss-info h2.name'));
  const contactMeta = unique(document, '.job-boss-info .boss-info-attr');
  const shortCompany = Array.from(contactMeta?.childNodes || []).find(child => child.nodeType === 3 && child.textContent.trim())
    ?.textContent.split(/[·•|]/)[0].trim() || '';
  const companyLink = unique(document, '.company-info > a[title]:not(:has(img))');
  const company = companyLink?.getAttribute('title')?.trim() || plain(companyLink);
  const companies = [...new Set([shortCompany, company].filter(companyName))];
  return title && city && companies.length && recruiter ? {title, city, companies, recruiter} : null;
};
"""


def _job_identity_script(path: str, title: str) -> str:
    return "(async () => {\n" + _DOM_HELPERS + _DETAIL_IDENTITY + "const expected = " + json.dumps({"path": path, "title": title}) + r""";
for (let attempt = 0; attempt < 24; attempt++) {
  if (blocked() || location.origin !== 'https://www.zhipin.com' || location.pathname !== expected.path)
    return outcome('blocked', '未进入正确岗位或平台要求验证，未点击沟通。');
  const identity = describeJob();
  if (identity) return same(identity.title, expected.title)
    ? {status: 'verified', ...identity}
    : outcome('blocked', '详情页的岗位名和清单不一致，未点击沟通。请刷新岗位并重新生成。');
  await wait(250);
}
return outcome('blocked', '详情页未显示可核对的公司、城市或招聘者，未点击沟通。');
})()"""


def _open_conversation_script(path: str, identity: dict) -> str:
    return "(async () => {\n" + _DOM_HELPERS + _DETAIL_IDENTITY + "const expected = " + json.dumps({**identity, "path": path}) + r""";
for (let attempt = 0; attempt < 24; attempt++) {
  if (blocked()) return outcome('blocked', '平台要求验证或登录，请本人处理。');
  if (location.origin !== 'https://www.zhipin.com' || location.pathname !== expected.path)
    return outcome('blocked', '浏览器没有停在目标岗位，未操作。');
  const live = describeJob();
  if (!live || !same(live.title, expected.title) || !sameCity(live.city, expected.city) ||
    !same(live.recruiter, expected.recruiter) || !live.companies.some(company => expected.companies.some(name => same(company, name))))
    return outcome('blocked', '岗位详情的招聘对象发生变化，未点击。');
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


def _chat_send_script(path: str, identity: dict, message: str) -> str:
    payload = json.dumps({**identity, "path": path, "text": message}, ensure_ascii=True)
    return "(async () => {\n" + _DOM_HELPERS + "const expected = " + payload + r""";
const onChat = () => location.origin === 'https://www.zhipin.com' && location.pathname === '/web/geek/chat';
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
  const recruiter = plain(unique(header, '.base-info .name-text'));
  if (!same(title, expected.title) || !expected.companies.some(name => same(company, name)) ||
      !sameCity(city, expected.city) || !same(recruiter, expected.recruiter)) return null;
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
