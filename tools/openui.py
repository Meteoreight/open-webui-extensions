"""
title: OpenUI - Generative UI
author: thesysdev/vishxrad
modified: meteoreight
version: 0.5.0
description: Renders interactive generative UI components (charts, forms, tables, cards, follow-ups) in chat using OpenUI Lang.
"""

import json
import secrets
from html import escape
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Theme detection script - runs in <head> before content renders so CSS
# variables resolve to the correct theme immediately.
# ---------------------------------------------------------------------------
_THEME_SCRIPT = """<script>
(function() {
  function systemPrefersDark() {
    return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }
  function bakedThemeIsDark() {
    var root = document.documentElement;
    var theme = root.getAttribute('data-openui-theme') || root.getAttribute('data-theme') || '';
    return theme === 'dark';
  }
  function detectTheme(root) {
    try {
      var stored = parent.localStorage && parent.localStorage.getItem('theme');
      if (stored) {
        if (stored.indexOf('oled') !== -1 || stored.indexOf('dark') !== -1) return true;
        if (stored === 'light' || stored === 'her') return false;
        if (stored === 'system') return systemPrefersDark();
      }
    } catch(e) {}
    if (root.classList.contains('dark') || root.classList.contains('oled-dark')) return true;
    if (root.classList.contains('light') || root.classList.contains('her')) return false;
    if (root.getAttribute('data-theme') === 'dark') return true;
    if (root.getAttribute('data-theme') === 'light') return false;
    return systemPrefersDark();
  }
  function applyTheme(isDark) {
    var t = isDark ? 'dark' : 'light';
    document.documentElement.classList.remove(isDark ? 'light' : 'dark');
    document.documentElement.classList.add(t);
    document.documentElement.style.colorScheme = t;
    document.documentElement.setAttribute('data-theme', t);
    document.documentElement.setAttribute('data-openui-theme', t);
  }
  try {
    var p = parent.document.documentElement;
    applyTheme(detectTheme(p));
    new MutationObserver(function() {
      applyTheme(detectTheme(p));
    }).observe(p, { attributes: true, attributeFilter: ['class', 'data-theme', 'style'] });
    window.addEventListener('storage', function(e) {
      if (e.key === 'theme') applyTheme(detectTheme(p));
    });
  } catch(e) {
    applyTheme(bakedThemeIsDark());
  }
})();
</script>"""
# ---------------------------------------------------------------------------
# Body scripts - height reporting, sendPrompt bridge, openLink, render
# ---------------------------------------------------------------------------
_BODY_SCRIPTS = """<script>
var _rhLast = 0;
var _rhRaf = 0;
function reportHeight() {
  var saved = document.body.style.cssText;
  document.body.style.setProperty('height', 'auto', 'important');
  document.body.style.setProperty('overflow', 'visible', 'important');
  var h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  document.body.style.cssText = saved;
  if (h === _rhLast) return;
  _rhLast = h;
  postToParent({ type: 'iframe:height', height: h });
}
window.addEventListener('load', function() {
  reportHeight();
  setTimeout(reportHeight, 200);
  setTimeout(reportHeight, 1000);
  setTimeout(reportHeight, 3000);
});
new ResizeObserver(function() {
  cancelAnimationFrame(_rhRaf);
  _rhRaf = requestAnimationFrame(reportHeight);
}).observe(document.body);
new MutationObserver(function() {
  cancelAnimationFrame(_rhRaf);
  _rhRaf = requestAnimationFrame(reportHeight);
}).observe(document.body, { childList: true, subtree: true });
window.addEventListener('resize', reportHeight);
document.addEventListener('toggle', function() {
  _rhLast = 0;
  setTimeout(reportHeight, 50);
}, true);
function sendPrompt(text) {
  try {
    postToParent({ type: 'input:prompt:submit', text: text });
  } catch(e) {}
}
function openLink(url) {
  try {
    var parsed = new URL(String(url || ''), window.location.href);
    if (!/^(https?|mailto|tel):$/.test(parsed.protocol)) return;
    var opened;
    try { opened = parent.window.open(parsed.href, '_blank', 'noopener,noreferrer'); }
    catch(e) { opened = window.open(parsed.href, '_blank', 'noopener,noreferrer'); }
    if (opened) opened.opener = null;
  } catch(e) {}
}
function parentOrigin() {
  try {
    if (!document.referrer) return null;
    var parsed = new URL(document.referrer);
    // Only accept http(s) origins. Bail out on anything exotic so we never
    // fall back to a wildcard targetOrigin when posting sensitive payloads
    // (e.g. form data via sendPrompt).
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
    return parsed.origin;
  } catch(e) {}
  return null;
}
var _parentOrigin = parentOrigin();
function postToParent(message) {
  // Refuse to post when we cannot pin a concrete parent origin. postMessage
  // with '*' would deliver the message to any embedding page.
  if (!_parentOrigin) return;
  parent.postMessage(message, _parentOrigin);
}
</script>"""
_CDN_BASE = "https://cdn.jsdelivr.net/npm/@openuidev/browser-bundle@0.1.1"
_LOCALHOSTS = {"localhost", "127.0.0.1", "::1"}
_OPENUI_THEME_OVERRIDES = """
/* The bundled OpenUI stylesheet uses @media(prefers-color-scheme: dark).
   Keep iframe theme tied to Open WebUI instead of the browser/device theme. */
:root[data-openui-theme="light"] {
  color-scheme: light;
  --openui-background: oklch(0.97 0 89.876 / 1);
  --openui-foreground: oklch(0.994 0 89.876 / 1);
  --openui-popover-background: oklch(0.994 0 89.876 / 1);
  --openui-sunk-light: oklch(0.097 0 0 / 0.02);
  --openui-sunk: oklch(0.097 0 0 / 0.04);
  --openui-sunk-deep: oklch(0.097 0 0 / 0.08);
  --openui-elevated-light: oklch(0.097 0 0 / 0.04);
  --openui-elevated: oklch(0.097 0 0 / 0.08);
  --openui-elevated-strong: oklch(0.097 0 0 / 0.16);
  --openui-elevated-intense: oklch(0.097 0 0 / 0.32);
  --openui-highlight-subtle: oklch(0.097 0 0 / 0.02);
  --openui-highlight: oklch(0.097 0 0 / 0.04);
  --openui-highlight-strong: oklch(0.097 0 0 / 0.08);
  --openui-highlight-intense: oklch(0.097 0 0 / 0.32);
  --openui-inverted-background: oklch(0.097 0 0 / 1);
  --openui-text-neutral-primary: oklch(0.097 0 0 / 1);
  --openui-text-neutral-secondary: oklch(0.097 0 0 / 0.5);
  --openui-text-neutral-tertiary: oklch(0.097 0 0 / 0.2);
  --openui-text-neutral-link: oklch(0.097 0 0 / 1);
  --openui-text-brand: oklch(0.097 0 0 / 1);
  --openui-text-accent-primary: oklch(0.994 0 89.876 / 1);
  --openui-text-accent-secondary: oklch(0.994 0 89.876 / 0.5);
  --openui-text-accent-tertiary: oklch(0.994 0 89.876 / 0.2);
  --openui-interactive-accent-default: oklch(0.097 0 0 / 1);
  --openui-interactive-accent-hover: oklch(0.097 0 0 / 0.8);
  --openui-interactive-accent-disabled: oklch(0.097 0 0 / 0.4);
  --openui-interactive-accent-pressed: oklch(0.097 0 0 / 1);
  --openui-chat-user-response-bg: oklch(0.097 0 0 / 1);
  --openui-chat-user-response-text: oklch(0.994 0 89.876 / 1);
  --openui-border-default: oklch(0.097 0 0 / 0.06);
  --openui-border-interactive: oklch(0.097 0 0 / 0.12);
  --openui-border-interactive-emphasis: oklch(0.097 0 0 / 0.3);
  --openui-border-interactive-selected: oklch(0.097 0 0 / 1);
  --openui-border-accent: oklch(0.097 0 0 / 0.08);
  --openui-border-accent-emphasis: oklch(0.097 0 0 / 0.3);
}
:root[data-openui-theme="dark"] {
  color-scheme: dark;
  --openui-background: oklch(0.145 0 0 / 1);
  --openui-foreground: oklch(0.205 0 0 / 1);
  --openui-popover-background: oklch(0.205 0 0 / 1);
  --openui-sunk-light: oklch(0.994 0 89.876 / 0.02);
  --openui-sunk: oklch(0.994 0 89.876 / 0.04);
  --openui-sunk-deep: oklch(0.994 0 89.876 / 0.08);
  --openui-elevated-light: oklch(0.994 0 89.876 / 0.04);
  --openui-elevated: oklch(0.994 0 89.876 / 0.08);
  --openui-elevated-strong: oklch(0.994 0 89.876 / 0.16);
  --openui-elevated-intense: oklch(0.994 0 89.876 / 0.32);
  --openui-highlight-subtle: oklch(0.994 0 89.876 / 0.02);
  --openui-highlight: oklch(0.994 0 89.876 / 0.04);
  --openui-highlight-strong: oklch(0.994 0 89.876 / 0.08);
  --openui-highlight-intense: oklch(0.994 0 89.876 / 0.3);
  --openui-inverted-background: oklch(0.994 0 89.876 / 1);
  --openui-text-neutral-primary: oklch(0.985 0 89.876 / 1);
  --openui-text-neutral-secondary: oklch(0.985 0 89.876 / 0.5);
  --openui-text-neutral-tertiary: oklch(0.985 0 89.876 / 0.2);
  --openui-text-neutral-link: oklch(0.985 0 89.876 / 1);
  --openui-text-brand: oklch(0.994 0 89.876 / 1);
  --openui-text-accent-primary: oklch(0.097 0 0 / 1);
  --openui-text-accent-secondary: oklch(0.097 0 0 / 0.5);
  --openui-text-accent-tertiary: oklch(0.097 0 0 / 0.2);
  --openui-interactive-accent-default: oklch(0.994 0 89.876 / 1);
  --openui-interactive-accent-hover: oklch(0.994 0 89.876 / 0.8);
  --openui-interactive-accent-disabled: oklch(0.994 0 89.876 / 0.4);
  --openui-interactive-accent-pressed: oklch(0.994 0 89.876 / 1);
  --openui-chat-user-response-bg: oklch(0.994 0 89.876 / 1);
  --openui-chat-user-response-text: oklch(0.097 0 0 / 1);
  --openui-border-default: oklch(0.994 0 89.876 / 0.12);
  --openui-border-interactive: oklch(0.994 0 89.876 / 0.2);
  --openui-border-interactive-emphasis: oklch(0.994 0 89.876 / 0.4);
  --openui-border-interactive-selected: oklch(0.985 0 89.876 / 1);
  --openui-border-accent: oklch(0.994 0 89.876 / 0.2);
  --openui-border-accent-emphasis: oklch(0.994 0 89.876 / 0.4);
}
"""


def _json_for_script(value: str) -> str:
    return (
        json.dumps(value)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _normalize_cdn_base(cdn_base: str) -> str:
    parsed = urlparse(str(cdn_base or "").strip())
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in _LOCALHOSTS
    ):
        return _CDN_BASE
    if not parsed.netloc or parsed.username or parsed.password:
        return _CDN_BASE
    return parsed._replace(query="", fragment="").geturl().rstrip("/")


def _csp_source_for(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_theme(theme: str | None) -> str:
    if isinstance(theme, dict):
        for key in ("result", "theme", "value", "data"):
            if key in theme:
                return _normalize_theme(theme[key])
    value = str(theme or "").lower().strip()
    return (
        "dark" if value == "dark" or '"dark"' in value or "'dark'" in value else "light"
    )


async def _get_openwebui_theme(__event_call__=None) -> str:
    if not __event_call__:
        return "light"
    try:
        theme = await __event_call__(
            {
                "type": "execute",
                "data": {
                    "code": """
return (() => {
  const systemDark = () => {
    try { return window.matchMedia('(prefers-color-scheme: dark)').matches; }
    catch (e) { return false; }
  };
  try {
    const stored = localStorage.getItem('theme');
    if (stored) {
      if (stored.includes('oled') || stored.includes('dark')) return 'dark';
      if (stored === 'light' || stored === 'her') return 'light';
      if (stored === 'system') return systemDark() ? 'dark' : 'light';
    }
  } catch (e) {}
  try {
    const root = document.documentElement;
    if (root.classList.contains('dark') || root.classList.contains('oled-dark')) return 'dark';
    if (root.classList.contains('light') || root.classList.contains('her')) return 'light';
    if (root.getAttribute('data-theme') === 'dark') return 'dark';
    if (root.getAttribute('data-theme') === 'light') return 'light';
  } catch (e) {}
  const luminance = (cssColor) => {
    const match = String(cssColor || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
    if (!match || match[4] === '0') return null;
    const channels = [Number(match[1]), Number(match[2]), Number(match[3])].map((value) => {
      const normalized = value / 255;
      return normalized <= 0.03928
        ? normalized / 12.92
        : Math.pow((normalized + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  };
  try {
    const candidates = [
      document.body,
      document.querySelector('main'),
      document.querySelector('#app'),
      document.documentElement,
    ].filter(Boolean);
    for (const el of candidates) {
      const lightness = luminance(getComputedStyle(el).backgroundColor);
      if (lightness !== null) return lightness < 0.25 ? 'dark' : 'light';
    }
  } catch (e) {}
  return systemDark() ? 'dark' : 'light';
})();
"""
                },
            }
        )
        return _normalize_theme(theme)
    except Exception:
        return "light"


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------
def _build_openui_html(
    code: str,
    title: str = "Response",
    cdn_base: str = _CDN_BASE,
    theme: str = "light",
) -> str:
    nonce = secrets.token_urlsafe(16)
    safe_title = escape(title, quote=True)
    safe_theme = _normalize_theme(theme)
    safe_cdn_base = _normalize_cdn_base(cdn_base)
    safe_cdn_attr = escape(safe_cdn_base, quote=True)
    cdn_json = _json_for_script(safe_cdn_base)
    cdn_csp_source = _csp_source_for(safe_cdn_base)
    code_json = _json_for_script(code)
    theme_script = _THEME_SCRIPT.replace("<script>", f'<script nonce="{nonce}">')
    body_scripts = _BODY_SCRIPTS.replace("<script>", f'<script nonce="{nonce}">')
    return f"""<!DOCTYPE html>
<html data-theme="{safe_theme}" data-openui-theme="{safe_theme}" class="{safe_theme}" style="color-scheme: {safe_theme};">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'nonce-{nonce}' {cdn_csp_source}; style-src 'self' 'unsafe-inline' {cdn_csp_source}; connect-src {cdn_csp_source}; img-src https: data: blob:; font-src 'self' data: {cdn_csp_source}; object-src 'none'; base-uri 'self'; form-action 'none'">
<link rel="stylesheet" href="{safe_cdn_attr}/dist/openui-styles.css">
<style nonce="{nonce}">
{_OPENUI_THEME_OVERRIDES}
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ background: transparent; }}
body {{ padding: 4px; overflow: visible; }}
#openui-root {{ width: 100%; }}
.openui-loading {{
  display: flex; align-items: center; justify-content: center;
  padding: 32px; color: #888; font-family: system-ui, -apple-system, sans-serif;
  font-size: 14px;
}}
.openui-error {{
  padding: 16px; color: #dc2626; font-family: system-ui, sans-serif;
  background: #fef2f2; border-radius: 8px; border: 1px solid #fecaca;
  font-size: 13px; line-height: 1.5;
}}
.openui-error strong {{ display: block; margin-bottom: 4px; }}
</style>
{theme_script}
</head>
<body>
<div id="openui-root"><div class="openui-loading">Loading components&#8230;</div></div>
{body_scripts}
<script nonce="{nonce}">
(function() {{
  var cdnBase = {cdn_json};
  var script = document.createElement('script');
  script.src = cdnBase + '/dist/openui-bundle.min.js';
  function renderError(title, message) {{
    var el = document.getElementById('openui-root');
    el.textContent = '';
    var box = document.createElement('div');
    box.className = 'openui-error';
    var strong = document.createElement('strong');
    strong.textContent = title;
    box.appendChild(strong);
    box.appendChild(document.createTextNode(message || ''));
    el.appendChild(box);
    reportHeight();
  }}
  script.onload = function() {{
    try {{
      var OpenUI = window.__OpenUI;
      if (!OpenUI || !OpenUI.Renderer || !OpenUI.openuiChatLibrary) {{
        throw new Error('OpenUI bundle loaded but exports missing');
      }}
      var code = {code_json};
      var container = document.getElementById('openui-root');
      container.innerHTML = '';
      var root = OpenUI.createRoot(container);
      function handleAction(event) {{
        if (event.type === 'open_url') {{
          openLink(event.params && event.params.url ? event.params.url : '');
          return;
        }}
        var prompt = event.humanFriendlyMessage || (event.params && event.params.message) || '';
        if (event.formState && Object.keys(event.formState).length > 0) {{
          var formDataStr = Object.entries(event.formState)
            .map(function(entry) {{ return entry[0] + ': ' + JSON.stringify(entry[1]); }})
            .join('\\n');
          prompt = prompt
            ? prompt + '\\n\\nForm data:\\n' + formDataStr
            : 'Form submission' + (event.formName ? ' (' + event.formName + ')' : '') + ':\\n' + formDataStr;
        }}
        if (!prompt && event.type) {{
          prompt = 'User action: ' + event.type + (event.params ? '\\n' + JSON.stringify(event.params) : '');
        }}
        if (prompt) {{
          sendPrompt(prompt);
        }}
      }}
      root.render(OpenUI.React.createElement(OpenUI.Renderer, {{
        response: code,
        library: OpenUI.openuiChatLibrary,
        isStreaming: false,
        onAction: handleAction
      }}));
      setTimeout(reportHeight, 500);
      setTimeout(reportHeight, 2000);
    }} catch(err) {{
      renderError('Failed to render OpenUI', err.message || String(err));
      console.error('OpenUI render error:', err);
    }}
  }};
  script.onerror = function() {{
    renderError(
      'Failed to load OpenUI bundle',
      'Could not load ' + script.src + '. Make sure openui-bundle.min.js is in the static directory.'
    );
  }};
  document.body.appendChild(script);
}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------
class Tools:
    """OpenUI Generative UI - renders interactive components in chat.
    When the user's question could benefit from a visual response (charts,
    tables, forms, cards, step lists, follow-ups, etc.), call render_openui
    to render a rich interactive UI instead of plain markdown.
    NEVER output openui-lang code as text. ALWAYS pass it to render_openui.
    """

    class Valves(BaseModel):
        cdn_base_url: str = Field(
            default=_CDN_BASE,
            description="Base CDN URL for the OpenUI bundle. Change if self-hosting or using a different version.",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def render_openui(
        self,
        openui_lang_code: str,
        title: str = "Response",
        __event_emitter__=None,
        __event_call__=None,
    ) -> tuple:
        """
        Render interactive UI components inline in the chat using OpenUI Lang.
        Use this tool whenever a visual response would be helpful: tables, charts,
        forms, lists, cards, step guides, follow-up suggestions, etc.
        IMPORTANT: Pass the openui-lang code as the openui_lang_code argument.
        NEVER output openui-lang as text in your response. After calling this tool,
        briefly describe what the user sees - do NOT echo the source code.
        ## OpenUI Lang Syntax
        Each statement: `identifier = Expression`. `root = Card(...)` is the entry point.
        Expressions: strings ("..."), numbers, booleans, null, arrays ([...]), objects ({...}), or TypeName(arg1, arg2, ...).
        Arguments are POSITIONAL. Write TypeName(arg1, arg2) NOT TypeName(key: val).
        Every variable (except root) must be referenced by another. Unreferenced = not rendered.
        ## Components
        Card(children[]) - root container, children stack vertically.
        CardHeader(title?, subtitle?)
        TextContent(text, size?) - size: "small"|"default"|"large"|"small-heavy"|"large-heavy"
        MarkDownRenderer(textMarkdown, variant?) - variant: "clear"|"card"|"sunk"
        Callout(variant, title, description) - variant: "info"|"warning"|"error"|"success"|"neutral"
        TextCallout(variant?, title?, description?)
        Image(alt, src?)
        ImageBlock(src, alt?)
        ImageGallery(images[{src,alt?,details?}])
        CodeBlock(language, codeString)
        Separator(orientation?, decorative?)
        Table(columns: Col[])
        Col(label, data[], type?) - type: "string"|"number"|"action"
        BarChart(labels[], series: Series[], variant?, xLabel?, yLabel?) - variant: "grouped"|"stacked"
        LineChart(labels[], series: Series[], variant?, xLabel?, yLabel?) - variant: "linear"|"natural"|"step"
        AreaChart(labels[], series: Series[], variant?, xLabel?, yLabel?)
        HorizontalBarChart(labels[], series: Series[], variant?, xLabel?, yLabel?)
        RadarChart(labels[], series: Series[])
        Series(category, values[])
        PieChart(labels[], values[], variant?) - variant: "pie"|"donut"
        RadialChart(labels[], values[])
        SingleStackedBarChart(labels[], values[])
        ScatterChart(datasets: ScatterSeries[], xLabel?, yLabel?)
        ScatterSeries(name, points: Point[])
        Point(x, y, z?)
        Form(name, buttons: Buttons, fields?: FormControl[])
        FormControl(label, input, hint?)
        Input(name, placeholder?, type?, rules?, value?)
        TextArea(name, placeholder?, rows?, rules?, value?)
        Select(name, items: SelectItem[], placeholder?, rules?, value?)
        SelectItem(value, label)
        DatePicker(name, mode?, rules?, value?)
        Slider(name, variant, min, max, step?, defaultValue?, label?, rules?, value?)
        CheckBoxGroup(name, items: CheckBoxItem[], rules?, value?)
        CheckBoxItem(label, description, name, defaultChecked?)
        RadioGroup(name, items: RadioItem[], defaultValue?, rules?, value?)
        RadioItem(label, description, value)
        SwitchGroup(name, items: SwitchItem[], variant?, value?)
        SwitchItem(label?, description?, name, defaultChecked?)
        Button(label, action?, variant?, type?, size?) - variant: "primary"|"secondary"|"tertiary"
        Buttons(buttons[], direction?) - direction: "row"|"column"
        ListBlock(items: ListItem[], variant?) - variant: "number"|"image"
        ListItem(title, subtitle?, image?, actionLabel?, action?)
        FollowUpBlock(items: FollowUpItem[]) - clickable follow-ups at end
        FollowUpItem(text) - clicking sends text as user message
        SectionBlock(sections: SectionItem[], isFoldable?)
        SectionItem(value, trigger, content[])
        Tabs(items: TabItem[])
        TabItem(value, trigger, content[])
        Accordion(items: AccordionItem[])
        AccordionItem(value, trigger, content[])
        Steps(items: StepsItem[])
        StepsItem(title, details)
        Carousel(children[][], variant?) - each slide is array of components; all slides same structure
        TagBlock(tags[])
        Tag(text, icon?, size?, variant?)
        Action([@steps...]) - wires buttons. Steps: @ToAssistant("msg"), @OpenUrl("url")
        Buttons without Action auto-send their label.
        ## Examples
        Table: root = Card([title, tbl, followUps])
        title = TextContent("Top Languages", "large-heavy")
        tbl = Table([Col("Language", langs), Col("Users (M)", users)])
        langs = ["Python", "JavaScript", "Java"]
        users = [15.7, 14.2, 12.1]
        followUps = FollowUpBlock([FollowUpItem("Tell me more about Python")])
        Chart: root = Card([header, chart])
        header = CardHeader("Monthly Revenue")
        chart = BarChart(months, [Series("Revenue", values)])
        months = ["Jan", "Feb", "Mar", "Apr"]
        values = [42000, 51000, 48000, 62000]
        Form: root = Card([title, form])
        title = TextContent("Contact Us", "large-heavy")
        form = Form("contact", btns, [nameField, emailField])
        nameField = FormControl("Name", Input("name", "Your name", "text", {required: true}))
        emailField = FormControl("Email", Input("email", "you@example.com", "email", {required: true, email: true}))
        btns = Buttons([Button("Submit", Action([@ToAssistant("Submit")]), "primary")])
        ## Rules
        - root = Card(...) MUST be the FIRST line.
        - Every name must be defined and reachable from root.
        - Card is the only layout container. Do NOT use Stack.
        - Use FollowUpBlock at the END for next actions.
        - Carousel slides MUST all have the same structure.
        - Generate realistic data when asked about data.
        :param openui_lang_code: Complete OpenUI Lang code starting with root = Card(...)
        :param title: Short descriptive title for the rendered UI.
        :return: Interactive rich embed rendered inline in the chat.
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f'Rendering "{title}"...',
                        "done": False,
                    },
                }
            )
        theme = await _get_openwebui_theme(__event_call__)
        response = HTMLResponse(
            content=_build_openui_html(
                openui_lang_code, title, self.valves.cdn_base_url, theme
            ),
            headers={"Content-Disposition": "inline"},
        )
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f'Rendered "{title}"',
                        "done": True,
                    },
                }
            )
        result_context = (
            f'OpenUI visualization "{title}" is now rendered and visible to the '
            f"user as an interactive embed. DO NOT echo back the OpenUI Lang source "
            f"code. Instead, briefly describe what the visualization shows in plain "
            f"language. If the visualization has interactive elements (clickable items, "
            f"buttons, forms, follow-ups), mention what the user can interact with."
        )
        return response, result_context
