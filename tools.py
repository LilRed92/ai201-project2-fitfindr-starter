"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    try:
        listings = load_listings()
    except Exception as exc:
        print(f"[search_listings] could not load listings: {exc}")
        return []

    try:
        query_words = [w for w in (description or "").lower().split() if w]

        scored = []
        for item in listings:
            # price filter — skip entirely when max_price is None
            if max_price is not None and item["price"] > max_price:
                continue

            # size filter — case-insensitive substring, skip when size is None
            if size is not None and size.lower() not in str(item["size"]).lower():
                continue

            # description scoring across title, description, style_tags, category.
            # style_tags is a list, so join it into the searchable text first.
            haystack = " ".join([
                item["title"],
                item["description"],
                " ".join(item["style_tags"]),
                item["category"],
            ]).lower()

            score = sum(1 for word in query_words if word in haystack)
            if score == 0:
                continue

            scored.append((score, item))

        # highest score first; stable sort keeps original order for ties
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored]
    except Exception as exc:
        print(f"[search_listings] unexpected error: {exc}")
        return []


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

    item_colors = ", ".join(new_item.get("colors", []))
    item_tags = ", ".join(new_item.get("style_tags", []))

    if not items:
        # Empty wardrobe: nothing to pair against, so give general styling
        # advice for this specific piece instead of a dead-end message.
        prompt = (
            f"A shopper is considering this secondhand piece but hasn't entered "
            f"any wardrobe items yet:\n"
            f"Title: {new_item.get('title')}\n"
            f"Description: {new_item.get('description')}\n"
            f"Category: {new_item.get('category')}\n"
            f"Colors: {item_colors}\n"
            f"Style tags: {item_tags}\n"
            f"Condition: {new_item.get('condition')}\n"
            f"Price: ${new_item.get('price')}\n\n"
            f"Give general styling advice for this specific piece: what kinds of "
            f"items would pair well with it, what aesthetic it fits, and how to "
            f"dress it up or down. Mention the {new_item.get('title')} by name. "
            f"Keep it practical and short."
        )
    else:
        # Format the wardrobe so the model can name specific pieces the user owns.
        wardrobe_lines = []
        for it in items:
            colors = ", ".join(it.get("colors", []))
            tags = ", ".join(it.get("style_tags", []))
            line = f"- {it.get('name')} ({it.get('category')}; colors: {colors}; style: {tags}"
            if it.get("notes"):
                line += f"; note: {it['notes']}"
            line += ")"
            wardrobe_lines.append(line)
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            f"A shopper is considering this secondhand piece:\n"
            f"Title: {new_item.get('title')}\n"
            f"Description: {new_item.get('description')}\n"
            f"Category: {new_item.get('category')}\n"
            f"Colors: {item_colors}\n"
            f"Style tags: {item_tags}\n"
            f"Condition: {new_item.get('condition')}\n"
            f"Price: ${new_item.get('price')}\n"
            f"Platform: {new_item.get('platform')}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_text}\n\n"
            f"Suggest one or two complete outfits that pair the "
            f"{new_item.get('title')} with specific pieces from their wardrobe. "
            f"Name the wardrobe pieces you use. Keep it practical and short."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a thoughtful personal stylist."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as exc:
        return f"Sorry, I couldn't put an outfit together, because {exc}."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard against a missing or empty outfit before spending an LLM call.
    if not outfit or not outfit.strip():
        return (
            "Can't write a fit card without an outfit suggestion. "
            "Run the styling step first."
        )

    tags = ", ".join(new_item.get("style_tags", []))
    prompt = (
        f"Write a short, fun caption for a social media post about a thrifted "
        f"outfit. Sound like a real person posting their fit, not a product "
        f"listing. 2 to 4 sentences, casual and a little playful. Mention the "
        f"piece, its price, and where it's from naturally, once each.\n\n"
        f"Item: {new_item.get('title')}\n"
        f"Price: ${new_item.get('price')}\n"
        f"From: {new_item.get('platform')}\n"
        f"Style tags: {tags}\n\n"
        f"The outfit: {outfit}"
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You write casual, authentic social media captions.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=1.0,
        )
        return response.choices[0].message.content
    except Exception as exc:
        return f"Sorry, I couldn't write a fit card, because {exc}."
