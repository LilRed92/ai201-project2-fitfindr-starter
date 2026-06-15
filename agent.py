"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Pull a description, size, and max_price out of a natural language query.

    I cut off any "what I own" clause (e.g. "I mostly wear baggy jeans") before
    parsing, so the things the user already owns don't end up scored as things
    they're searching for. Size and price come out via regex; whatever text is
    left after stripping those becomes the description.
    """
    text = query.strip()

    # Drop a trailing wardrobe-context clause so it doesn't pollute the search.
    cut = re.search(
        r"\bi\s+(?:mostly\s+|usually\s+|normally\s+|often\s+)?wear\b",
        text,
        flags=re.IGNORECASE,
    )
    if cut:
        text = text[: cut.start()]

    # size: "size M", "in size 8", "size: XXS"
    size = None
    m_size = re.search(r"\bsize[:\s]+([A-Za-z0-9/.]+)", text, flags=re.IGNORECASE)
    if m_size:
        size = m_size.group(1).strip(" .,/").upper() or None

    # max_price: prefer "under/below/less than $X", else fall back to a bare "$X"
    max_price = None
    m_price = re.search(
        r"(?:under|below|less than|<)\s*\$?\s*(\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if not m_price:
        m_price = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    if m_price:
        max_price = float(m_price.group(1))

    # description = the text with the size and price phrases removed
    description = text
    if m_size:
        description = description.replace(m_size.group(0), " ")
    if m_price:
        description = description.replace(m_price.group(0), " ")
    description = re.sub(r"[,.]", " ", description)
    description = re.sub(r"\s+", " ", description).strip()

    return {"description": description, "size": size, "max_price": max_price}


# These prefixes match the error strings the tools in tools.py return, so the
# loop can tell an error result apart from a real suggestion/caption without
# changing the tools.
_OUTFIT_ERROR_PREFIXES = (
    "Sorry, I couldn't put an outfit together, because",
)
_FITCARD_ERROR_PREFIXES = (
    "Can't write a fit card",
    "Sorry, I couldn't write a fit card, because",
)


def _looks_like_error(text: str, prefixes: tuple) -> bool:
    """True if a tool returned an empty string or one of its error messages."""
    if not text or not text.strip():
        return True
    return text.startswith(prefixes)


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into search parameters.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: search. Look at what came back before doing anything else.
    results = search_listings(
        parsed["description"], parsed["size"], parsed["max_price"]
    )
    session["search_results"] = results

    if not results:
        # No listings matched. Stop here, don't touch the styling tools.
        filters = []
        if parsed["max_price"] is not None:
            filters.append(f"under ${parsed['max_price']:.0f}")
        if parsed["size"]:
            filters.append(f"in size {parsed['size']}")
        filter_text = " " + " ".join(filters) if filters else ""
        desc = parsed["description"] or query
        session["error"] = (
            f"No listings matched '{desc}'{filter_text}. "
            f"Try raising your price, dropping the size, or describing it differently."
        )
        return session

    # Step 4: pick the top-ranked listing.
    session["selected_item"] = results[0]

    # Step 5: suggest an outfit. An empty wardrobe still returns useful general
    # styling advice, so the only thing that stops the loop here is an actual
    # LLM failure coming back as an error string.
    suggestion = suggest_outfit(session["selected_item"], wardrobe)
    if _looks_like_error(suggestion, _OUTFIT_ERROR_PREFIXES):
        session["error"] = suggestion
        return session
    session["outfit_suggestion"] = suggestion

    # Step 6: turn the outfit into a fit card.
    card = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    if _looks_like_error(card, _FITCARD_ERROR_PREFIXES):
        session["error"] = card
    else:
        session["fit_card"] = card

    # Step 7: hand the whole session back.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
