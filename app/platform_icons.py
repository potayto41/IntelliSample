"""
Platform → Lucide icon mapping for the site catalog.
Single source of truth: extend PLATFORM_TO_ICON and LUCIDE_ICONS as needed.
Icons are inline SVGs (Lucide style) for no external deps and full reuse.
"""

from typing import Optional

# Platform name (normalized lowercase) → Lucide icon key used in LUCIDE_ICONS.
PLATFORM_TO_ICON: dict[str, str] = {
    "wordpress": "layout",
    "webflow": "globe",
    "shopify": "shopping-bag",
    "wix": "layout",
    "squarespace": "square",
    "framer": "move",
    "ghost": "ghost",
    "kajabi": "video",
    "bubble": "circle",
    "notion": "file-text",
    "custom": "wrench",
    "unknown": "help-circle",
}

# Lucide icon key → inline SVG (one fragment per icon). Class and size applied in builder.
# viewBox 0 0 24 24, stroke 2, round caps – Lucide standard.
_LUCIDE_PATHS: dict[str, str] = {
    "layout": '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><path d="M3 9h18"/><path d="M9 21V9"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    "shopping-bag": '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>',
    "square": '<rect width="18" height="18" x="3" y="3" rx="2"/>',
    "move": '<path d="m5 9-3 3 3 3"/><path d="M9 5l3-3 3 3"/><path d="M15 19l-3 3-3-3"/><path d="M19 9l3 3-3 3"/><path d="M2 12h20"/><path d="M12 2v20"/>',
    "ghost": '<path d="M9 10h.01"/><path d="M15 10h.01"/><path d="M12 2a8 8 0 0 0-8 8v12l3-3 2.5 2.5 3-3 3 3 2.5-2.5L20 22V10a8 8 0 0 0-8-8z"/>',
    "video": '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><path d="M2 8.5v7a1.5 1.5 0 0 0 1.5 1.5h11a1.5 1.5 0 0 0 1.5-1.5v-7A1.5 1.5 0 0 0 14.5 7h-11A1.5 1.5 0 0 0 2 8.5Z"/>',
    "circle": '<circle cx="12" cy="12" r="10"/>',
    "file-text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "help-circle": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
}

ICON_SIZE = 18
DEFAULT_ICON = "help-circle"


def _build_svg(path_content: str, size: int = ICON_SIZE) -> str:
    """Build full inline SVG with shared attributes and given path(s)."""
    return (
        f'<svg class="icon icon-platform" aria-hidden="true" width="{size}" height="{size}" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f"{path_content}"
        "</svg>"
    )


# Prebuilt SVGs for template use (no per-request allocation).
LUCIDE_ICONS: dict[str, str] = {
    key: _build_svg(path_content) for key, path_content in _LUCIDE_PATHS.items()
}


def normalize_platform(platform: Optional[str]) -> str:
    """Return lowercase key for lookup; empty/None -> 'unknown'."""
    if not platform or not (s := str(platform).strip()):
        return "unknown"
    return s.lower()


def get_platform_icon_name(platform: Optional[str]) -> str:
    """Resolve platform to Lucide icon name. Reusable and extensible."""
    key = normalize_platform(platform)
    return PLATFORM_TO_ICON.get(key, PLATFORM_TO_ICON["unknown"])


def get_platform_icon_svg(platform: Optional[str]) -> str:
    """Return inline SVG for the given platform. Fallback to Unknown icon."""
    icon_name = get_platform_icon_name(platform)
    return LUCIDE_ICONS.get(icon_name, LUCIDE_ICONS[DEFAULT_ICON])
