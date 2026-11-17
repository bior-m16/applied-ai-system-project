"""PawPal+ "Playful Pack" look: colors, CSS and small HTML snippets for app.py.

How the styling works
- .streamlit/config.toml sets the base theme (colors, fonts, corner radius).
- inject_css() adds the cartoon details Streamlit has no setting for: 2px ink
  outlines, chunky offset shadows, colored cards and chat bubbles.
- Cards are styled by KEY. `st.container(key="pet_card_0")` gets the CSS class
  `st-key-pet_card_0`, so the rules below target those classes. Keep the key
  names in app.py exactly as listed in KEYS.
- Only display-only content uses raw HTML (st.markdown(..., unsafe_allow_html=True)).
  Anything clickable must be a real Streamlit widget so it can run Python.
"""

from __future__ import annotations

import html

import streamlit as st

# --- design tokens (from the Playful Pack mockup) ------------------------------------
INK = "#231942"          # text, outlines, shadows
MUTED = "#4A4266"        # secondary text (7:1 on white)
BG = "#F3EADA"           # page background (warm beige)
CREAM = "#FBF5E9"        # big cards (chat) and inputs
ACCENT = "#5B3FD9"       # primary actions, user chat bubble
YELLOW = "#FFD166"       # "Today's walk-through" panel, primary sticker buttons
PINK = "#FFC2D1"         # card fill 1, high priority
MINT = "#BDEBD6"         # card fill 2, medium priority
LILAC = "#DCD3FF"        # card fill 3, low priority
NOTE_BG = "#FFF1C9"      # "I moved a task" note
NOTE_INK = "#4D3800"
DANGER_BG = "#FFE1E1"    # emergency refusal
DANGER_INK = "#7A1020"

CARD_FILLS = [PINK, MINT, LILAC, YELLOW]  # pet cards cycle through these
PRIORITY_FILL = {3: PINK, 2: MINT, 1: LILAC}
PRIORITY_WORD = {3: "High", 2: "Medium", 1: "Low"}

# Container keys app.py must use (CSS below depends on them).
KEYS = {
    "hero": "hero",
    "pet_card": "pet_card_{i}",          # i = 0, 1, 2 ...
    "chat_card": "chat_card",
    "task_sticker": "task_sticker_{turn}_{i}",  # prefix match, so any suffix works
    "ai_note": "ai_note_{turn}_{j}",           # prefix match
    "ai_emergency": "ai_emergency_{turn}",     # prefix match
    "walkthrough": "walkthrough",
    "build_plan": "build_plan",          # st.button key
}

_SHADOW = f"5px 5px 0 {INK}"
_BORDER = f"2px solid {INK}"

_CSS = f"""
<style>
/* page */
[data-testid="stMainBlockContainer"] {{ max-width: 1200px; padding-top: 3.5rem; }}
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}

/* any bordered container becomes a sticker card */
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 28px; }}

/* pet cards: colored, outlined, offset shadow */
{"".join(
    f'.st-key-pet_card_{i} {{ background:{fill}; border:{_BORDER}; border-radius:28px; '
    f'box-shadow:{_SHADOW}; padding:20px; position:relative; }}\n'
    for i, fill in enumerate(CARD_FILLS * 3)
)}

/* big white chat card and yellow walk-through panel */
.st-key-chat_card {{ background:{CREAM}; border:{_BORDER}; border-radius:32px;
    box-shadow:6px 6px 0 {INK}; padding:28px; }}
.st-key-walkthrough {{ background:{YELLOW}; border:{_BORDER}; border-radius:32px;
    box-shadow:6px 6px 0 {INK}; padding:24px; }}

/* proposed-task stickers inside the chat */
[class*="st-key-task_sticker_"] {{ background:#FFFFFF; border:{_BORDER}; border-radius:18px;
    padding:12px 14px; gap:0.25rem; }}

/* notes */
[class*="st-key-ai_note"] {{ background:{NOTE_BG}; color:{NOTE_INK}; border:2px dashed #8A6400;
    border-radius:14px; padding:10px 12px; }}
[class*="st-key-ai_emergency"] {{ background:{DANGER_BG}; color:{DANGER_INK}; border:{_BORDER};
    border-radius:18px; padding:14px 16px; }}

/* chat bubbles */
[data-testid="stChatMessage"] {{ background:transparent; padding:0.25rem 0; width:100%; align-self:stretch; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
    flex-direction:row-reverse; justify-content:flex-start; text-align:left; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
    [data-testid="stChatMessageContent"] {{
    background:{ACCENT}; color:#FFFFFF; border-radius:22px 22px 6px 22px;
    padding:14px 18px; flex:0 1 auto; max-width:80%; margin:0 0 0 auto; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
    [data-testid="stChatMessageContent"] p {{ color:#FFFFFF; }}
[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"]))
    [data-testid="stChatMessageContent"] {{
    background:{BG}; border-radius:6px 22px 22px 22px; padding:16px 18px; }}
[data-testid="stChatMessage"] img, [data-testid^="stChatMessageAvatar"] {{
    border:{_BORDER}; border-radius:50%; background:{YELLOW}; }}

/* chat input: pill with ink outline */
[data-testid="stChatInput"] {{ border:{_BORDER}; border-radius:999px; background:{CREAM}; }}

/* the "View schedule" button covers its whole pet card, so the card itself is the click target */
[class*="st-key-pet_card_"] button {{ background:#FFFFFF; font-size:14px; min-height:36px; }}
[class*="st-key-pet_card_"] button::after {{ content:""; position:absolute; inset:0; border-radius:28px; cursor:pointer; }}
[class*="st-key-pet_card_"]:hover {{ transform:translate(-1px,-1px); box-shadow:7px 7px 0 {INK}; }}

/* buttons: pills; primary = yellow sticker with shadow */
.stButton button, .stFormSubmitButton button, [data-testid="stPopover"] button {{
    border-radius:999px; border:{_BORDER}; font-weight:600; min-height:44px; }}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {{
    background:{YELLOW}; color:{INK}; box-shadow:3px 3px 0 {INK}; }}
.stButton button[kind="primary"]:hover {{ background:#FFC23D; color:{INK}; border-color:{INK}; }}
.stButton button[kind="primary"]:active {{ box-shadow:1px 1px 0 {INK}; transform:translate(2px,2px); }}
.st-key-build_plan button {{ background:{INK}; color:#FFFFFF; box-shadow:none; }}

/* small source tags (popover triggers) inside stickers */
[class*="st-key-task_sticker_"] [data-testid="stPopover"] button {{
    min-height:32px; padding:2px 10px; border:0; background:{BG}; color:#3A2B8C; font-size:13px; }}

/* tabs as pills */
[data-testid="stTabs"] [role="tab"] {{ border:{_BORDER}; border-radius:999px; padding:6px 18px;
    font-weight:600; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ background:{INK}; color:#FFFFFF; }}
/* hide the default underline and the sliding selection bar */
[data-testid="stTabs"] [role="tablist"]::after,
[data-testid="stTabs"] .react-aria-SelectionIndicator {{ display:none; }}
[data-testid="stTabs"] [role="tablist"] {{ gap:8px; padding:4px 6px 10px 0; }}

/* small screens: lighter shadows, less padding */
@media (max-width: 640px) {{
    .st-key-chat_card, .st-key-walkthrough {{ padding:18px; box-shadow:4px 4px 0 {INK}; }}
}}
</style>
"""

# Simple line-drawing faces (decorative, so aria-hidden). Use INK strokes.
_DOG = (
    '<svg width="46" height="46" viewBox="0 0 40 40" aria-hidden="true" fill="none" stroke="#231942" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 14 L7 26 Q7 29 10 28 L13 22"/>'
    '<path d="M30 14 L33 26 Q33 29 30 28 L27 22"/><path d="M12 14 Q20 8 28 14 L28 24 Q28 32 20 32 Q12 32 12 24 Z"/>'
    '<circle cx="16.5" cy="20" r="1" fill="#231942"/><circle cx="23.5" cy="20" r="1" fill="#231942"/>'
    '<path d="M18.5 25 Q20 26.5 21.5 25"/></svg>'
)
_CAT = (
    '<svg width="46" height="46" viewBox="0 0 40 40" aria-hidden="true" fill="none" stroke="#231942" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 17 L11 8 L17 13"/>'
    '<path d="M29 17 L29 8 L23 13"/><path d="M11 17 Q11 32 20 32 Q29 32 29 17 Q29 12 20 12 Q11 12 11 17 Z"/>'
    '<circle cx="16.5" cy="20" r="1" fill="#231942"/><circle cx="23.5" cy="20" r="1" fill="#231942"/>'
    '<path d="M18.5 24.5 L20 25.5 L21.5 24.5"/><path d="M8 23 L14 24 M8 27 L14 26 M32 23 L26 24 M32 27 L26 26"/></svg>'
)
_PAW = (
    '<svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><g fill="#231942">'
    '<ellipse cx="12" cy="16" rx="5" ry="4"/><circle cx="6" cy="10" r="2.2"/><circle cx="10" cy="6.5" r="2.2"/>'
    '<circle cx="14" cy="6.5" r="2.2"/><circle cx="18" cy="10" r="2.2"/></g></svg>'
)


def inject_css() -> None:
    """Add the Playful Pack styles. Call once, right after st.set_page_config()."""
    st.markdown(_CSS, unsafe_allow_html=True)


def logo_html() -> str:
    """The yellow paw badge plus the PawPal+ wordmark."""
    return (
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
        f'<div style="width:46px;height:46px;border-radius:50%;background:{YELLOW};border:{_BORDER};'
        f'box-shadow:3px 3px 0 {INK};display:flex;align-items:center;justify-content:center">{_PAW}</div>'
        f'<span style="font-family:Fredoka,sans-serif;font-weight:700;font-size:28px;color:{INK}">PawPal+</span></div>'
    )


def pet_face_html(species: str) -> str:
    """A white blob with a dog, cat or paw drawing, for the top of a pet card."""
    art = {"dog": _DOG, "cat": _CAT}.get(species.lower(), _PAW)
    return (
        f'<div style="width:72px;height:72px;border-radius:50% 50% 46% 54%;background:#FFFFFF;'
        f'border:{_BORDER};display:flex;align-items:center;justify-content:center;margin-bottom:8px">{art}</div>'
    )


def chip_html(text: str, fill: str = "#FFFFFF", outlined: bool = True) -> str:
    """A small rounded label. Text is escaped, so it's safe for user input."""
    border = _BORDER if outlined else "0"
    return (
        f'<span style="display:inline-block;padding:2px 12px;border-radius:999px;background:{fill};'
        f'border:{border};font-size:13px;font-weight:600;color:{INK}">{html.escape(text)}</span>'
    )


def priority_chip_html(priority: int) -> str:
    return chip_html(PRIORITY_WORD.get(priority, str(priority)), PRIORITY_FILL.get(priority, LILAC), outlined=False)


def pet_chip_html(pet_name: str, index: int) -> str:
    """Pet name chip in the same color as that pet's card."""
    return chip_html(pet_name, CARD_FILLS[index % len(CARD_FILLS)])
