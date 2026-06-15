# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the 40 mock listings for items matching what the user described, then narrows by size and price when those were given. It returns the matches ranked best-first so the planning loop can grab the top one.

**Input parameters:**
- `description` (str): the words the user used for what they want, like "vintage graphic tee". Required. This drives the keyword scoring.
- `size` (str | None): a size to filter by, like "M". Matched case-insensitively as a substring, so "m" matches "M", "S/M", and "M/L". If it comes in as None, the size filter is skipped and every size passes.
- `max_price` (float | None): a price ceiling, inclusive. A listing sitting exactly at the cap still counts. If None, the price filter is skipped.

**How each filter works:**
- `price`: keep the listing if `price <= max_price`. Skipped when max_price is None.
- `size`: keep the listing if the lowercased `size` argument appears anywhere inside the listing's lowercased `size` string. Skipped when size is None. This is the loosest part of the whole design, since "M" lives inside a lot of strings.
- `description`: this is scoring, not a hard filter. Split the description into words, then count how many show up across the listing's `title`, `description`, and `style_tags`. Since `style_tags` is a list, I join it into one string (or check each tag) before counting. A listing that scores 0 gets dropped.

**What it returns (success):**
A list of listing dicts, sorted by score highest to lowest. Each dict has exactly these keys:
- `id` (str)
- `title` (str)
- `description` (str)
- `category` (str)
- `style_tags` (list[str])
- `size` (str)
- `condition` (str)
- `price` (float)
- `colors` (list[str])
- `brand` (str | None)
- `platform` (str)

These are the same dicts that come out of `load_listings()`, just filtered and reordered. I'm not bolting a score field onto them.

**What it returns when nothing matches:**
An empty list, `[]`. Not None, not an exception. The planning loop checks `if not session["search_results"]` and branches on that.

**Most likely failure mode:**
The description gets parsed into something that scores zero against everything (too specific, or a typo), so the function returns `[]`. That isn't a crash, it's the empty-list path above, and the loop handles it. The other thing that could actually raise is `load_listings()` failing if `data/listings.json` is missing or broken. I'm letting that propagate as a normal exception, since it means the project is set up wrong, not that the user asked for something weird.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the listing the user is considering plus their wardrobe and asks the LLM to put together one or two full outfits using that item with pieces the user already owns. Returns the suggestion as text.

**Input parameters:**
- `new_item` (dict): one listing dict from `search_listings`. The fields this function actually reads are `title` (so it can name the piece), `category`, `colors`, and `style_tags` (so the LLM knows what it is and what vibe it carries). It doesn't need `price`, `condition`, or `platform` to build an outfit.
- `wardrobe` (dict): the wardrobe in the shape from `wardrobe_schema.json`. It has one entry, `items`, which is a list of wardrobe dicts. Each wardrobe item has `id`, `name`, `category`, `colors`, `style_tags`, and an optional `notes` that can be null. This comes from `get_example_wardrobe()` or `get_empty_wardrobe()`.

**What it returns (success):**
A single non-empty string with the outfit ideas in plain language, naming the new item and specific wardrobe pieces by their `name`. It's prose meant to be shown to the user, not a dict.

**Empty wardrobe or only one item:**
This is the edge case I want to spell out instead of waving at. I check `wardrobe["items"]` first.
- If the list is empty, there's nothing to pair with, so I send the LLM a different prompt asking for general styling advice for the new item on its own: what kinds of bottoms or shoes would go with it, what aesthetic it fits, how to dress it up or down. The return is still a normal string, just advice instead of named pairings.
- If there's exactly one item, I don't bail. I pass that single piece plus the new item and ask for one outfit built around the two of them, then let the LLM add a note about what else would round it out.

**Most likely failure mode:**
The LLM call itself fails (no network, bad `GROQ_API_KEY`, rate limit). Since the contract is never return an empty string and never raise, I wrap the call and on failure return a plain fallback string like "I couldn't generate an outfit right now, but this piece would pair well with simple basics in neutral colors." The loop still gets a usable string.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion into a short, casual caption the user could post with their thrifted find. Think OOTD post, not product copy.

**Input parameters:**
- `outfit` (str): exactly what `suggest_outfit` returns, the outfit suggestion text. It's a plain string, not a dict, so there are no sub-fields to pull from. The caption is built by reading this prose plus the item details below.
- `new_item` (dict): the same listing dict from before. The fields this one needs are `title` (name the piece), `price` (mention what it cost), and `platform` (where it's from). It can also glance at `colors` and `style_tags` to capture the vibe.

**What it returns (success):**
A string, 2 to 4 sentences, usable as an Instagram or TikTok caption. Names the item, its price, and the platform once each, and reads like a real person wrote it.

**Making it different every time:**
This is a stated requirement, so I'm designing for it rather than hoping the model varies on its own. Two things. First, the prompt always includes the specific `title`, `price`, `platform`, `colors`, and the actual outfit text, so different inputs give the model genuinely different material to write from. Second, I'll call the LLM at a higher temperature for this tool than for the others, since I want the wording to feel fresh rather than deterministic. The same item run twice should read a little differently.

**Most likely failure mode:**
`outfit` comes in empty or whitespace-only (say `suggest_outfit` returned a fallback that got cleared somewhere). I check for that first and return a descriptive error string like "Can't write a fit card without an outfit suggestion." instead of raising. If the LLM call fails, same idea as Tool 2: return a short fallback caption string so the loop always has something to show.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop doesn't fire all three tools no matter what. Each pass it looks at the session dict, decides what's missing or broken, and picks the next action from that. What it sees in the session is what changes its behavior. If a tool comes back empty or with an error, the next decision is different from the happy path.

The decision the loop makes each pass, based on session state:

- No `parsed` yet → parse the query into `description`, `size`, `max_price` and store it in `session["parsed"]`. A missing size or price stays None so the search skips that filter.

- `parsed` is set but `search_results` hasn't been filled → call `search_listings(description, size, max_price)` and store the return in `session["search_results"]`. Then look at what came back:
  - Empty list and a filter is still in play (size or max_price set) → loosen one constraint and search again. Drop the size filter first, since that's the loosest match anyway, and note in the session what was relaxed so the user can be told. (This is the retry-with-fallback path; it's also one of the stretch features.)
  - Empty list with nothing left to loosen → set `session["error"]` to a no-results message and stop. Don't call `suggest_outfit`.
  - Non-empty → set `session["selected_item"] = session["search_results"][0]`.

- `selected_item` is set but `outfit_suggestion` isn't → call `suggest_outfit(session["selected_item"], session["wardrobe"])` and store the return in `session["outfit_suggestion"]`. This tool always returns a usable string (it has its own empty-wardrobe branch), so the loop doesn't early-exit here unless it somehow gets back an empty string, in which case set `session["error"]` and stop.

- `outfit_suggestion` is set but `fit_card` isn't → call `create_fit_card(session["outfit_suggestion"], session["selected_item"])` and store it in `session["fit_card"]`. If that string is empty or is the tool's error text, set `session["error"]` so the caller knows the caption didn't come out.

- `fit_card` is set, or `error` is set → done. Return the session.

So the loop is driven by what's already in the session, not by a hardcoded 1-2-3. An empty search changes the next move (loosen, or stop), and an empty wardrobe changes what `suggest_outfit` produces. The agent reacts to returns instead of marching through every tool.

---

## State Management

**How does information from one tool get passed to the next?**

Everything runs through the single session dict that `_new_session()` builds in `agent.py`. No globals, and nothing is handed tool-to-tool directly. Each tool's output gets written to a named field, and the next decision reads from that field. That's also what lets the loop stay state-driven, since the loop reads the same dict to figure out what to do next.

The fields and who touches them:

- `query` (str): the raw request. Written at init, read by the parse step.
- `parsed` (dict): holds `description`, `size`, `max_price`. Written by the parse step, read when calling `search_listings`.
- `search_results` (list[dict]): written from the `search_listings` return. Read to check for the empty case and to pick the top item.
- `selected_item` (dict | None): set to `search_results[0]`. Read by both `suggest_outfit` and `create_fit_card`.
- `wardrobe` (dict): passed in at init, read by `suggest_outfit`.
- `outfit_suggestion` (str | None): written from `suggest_outfit`, read by `create_fit_card`.
- `fit_card` (str | None): written from `create_fit_card`. The final output.
- `error` (str | None): None unless a step bailed early. The caller reads this before trusting anything else.

So the find from `search_listings` flows into `suggest_outfit` as `selected_item` without the user retyping it, and the outfit text flows into `create_fit_card` the same way. The chain is search_results → selected_item → outfit_suggestion → fit_card, each one hop, all parked on the session.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No listing matches the parsed query (returns `[]`) | First try the fallback: drop the size filter and search again, and if that finds something, show the results with a note like "Nothing matched size M, so here's what's out there in other sizes." If it's still empty after loosening, set `session["error"]` to a specific message that names the filters, e.g. "No listings under $30 matched 'vintage graphic tee'. Try raising your price or describing it differently," and stop before the other tools run. |
| suggest_outfit | Wardrobe is empty (or has just one item) | Don't error. Switch to the general-advice prompt and return styling ideas for the item on its own (what to pair it with, what vibe it suits), so the user still gets a real suggestion. With one item, build the outfit around that piece plus the new item and add a note on what would round it out. |
| create_fit_card | `outfit` is missing, empty, or whitespace | Return a descriptive string instead of raising, e.g. "Can't write a fit card without an outfit suggestion. Try the styling step first," and set `session["error"]` so the caller can still show the search result and outfit without a broken caption. If the LLM call itself fails, return a short fallback caption so the user isn't left with nothing. |

---

## Architecture

The loop decides each step by reading the session dict, so the arrows below are "what the loop does when the session looks like this," not a fixed 1-2-3. Error branches and the empty-search fallback are drawn in.

```
User query (natural language)
    │  "vintage graphic tee under $30, size M"
    ▼
┌───────────────────────────────────────────────────────────┐
│ Planning Loop  (run_agent in agent.py)                      │
│ each pass: read session → decide next action                │
└───────────────────────────────────────────────────────────┘
    │
    │  parse query
    │  WRITE session["parsed"] = {description, size, max_price}
    ▼
[session has parsed, no search_results yet]
    │  READ session["parsed"]
    ├─► search_listings(description, size, max_price)
    │       │  returns list[dict] of listings, best-first
    │       │  WRITE session["search_results"]
    │       │
    │       │  results == [] AND a filter is still set
    │       ├──► FALLBACK: drop size filter, search again,
    │       │             note what was relaxed for the user
    │       │
    │       │  results == [] AND nothing left to loosen
    │       ├──► [ERROR] WRITE session["error"] = "No listings matched..."
    │       │            return session   (skip suggest_outfit + create_fit_card)
    │       │
    │       │  results == [item, ...]
    │       ▼
    │   WRITE session["selected_item"] = search_results[0]
    │
    ▼
[session has selected_item, no outfit_suggestion yet]
    │  READ session["selected_item"], session["wardrobe"]
    ├─► suggest_outfit(selected_item, wardrobe)
    │       │  wardrobe["items"] == []  → general styling advice (still a string)
    │       │  wardrobe["items"] != []  → outfit using owned pieces by name
    │       │  returns outfit string (always non-empty by design)
    │       │  WRITE session["outfit_suggestion"]
    │       │
    │       │  (defensive) outfit == ""  → WRITE session["error"], return
    │
    ▼
[session has outfit_suggestion, no fit_card yet]
    │  READ session["outfit_suggestion"], session["selected_item"]
    └─► create_fit_card(outfit_suggestion, selected_item)
            │  outfit empty/whitespace → return error string, WRITE session["error"]
            │  otherwise returns caption string
            │  WRITE session["fit_card"]
            ▼
        return session   (caller checks session["error"] first)
            │
            ▼
        User sees: matched listing + outfit + fit card
                   (or, on the error branch, just the no-results message)
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

I'll use Claude (inside Claude Code) for each of the three tools, one at a time instead of all at once, so I can test each before moving on.

- search_listings: I'll give Claude the Tool 1 spec above (the parameters, the filter rules, the exact return shape, the empty-list contract) plus the field reference comment at the top of `utils/data_loader.py`. I expect a `search_listings` that loads with `load_listings()`, applies the price and size filters, scores on description overlap, drops zero-score items, and sorts best-first. To check it before trusting it: run "vintage graphic tee" with size "M" and max_price 30 and confirm a top result like lst_002 comes back; run it with max_price 5 and confirm I get `[]`; run it with size None and confirm the size filter is skipped. If any of those three misbehave, I send the failing case back and fix it.

- suggest_outfit: I'll give Claude the Tool 2 spec plus the `example_wardrobe` and `empty_wardrobe` structures from `wardrobe_schema.json`. I expect a function that branches on `wardrobe["items"]` being empty and calls the LLM with the right prompt for each case. To check it: call it once with `get_example_wardrobe()` and confirm the output actually names pieces like the baggy jeans and chunky sneakers; call it once with `get_empty_wardrobe()` and confirm it returns general advice, not an empty string or an error.

- create_fit_card: I'll give Claude the Tool 3 spec, including the requirement that output varies by input and the higher-temperature note. I expect a function that guards against an empty outfit and otherwise returns a short caption naming the item, price, and platform. To check it: run it twice on the same item and confirm the two captions read differently; run it with an empty outfit string and confirm I get the error string back instead of a crash.

**Milestone 4 — Planning loop and state management:**

I'll give Claude the Planning Loop section, the State Management section, and the architecture diagram, along with the `_new_session` and `run_agent` stubs in `agent.py`. I expect it to fill in `run_agent` so it parses the query, calls the tools by reading session state at each step, writes each result to the right field, and takes the early-exit and fallback branches when `search_results` is empty. To check it: run the happy-path query from the diagram and confirm `session["error"]` is None and `fit_card` is filled; run "designer ballgown size XXS under $5" and confirm `session["error"]` is set and `outfit_suggestion` and `fit_card` stay None. I'll read the generated branch logic line by line against my Planning Loop section before keeping it, since the decision order and the early return are the parts most likely to come out wrong.

---

## A Complete Interaction (Step by Step)

### What FitFindr needs to do end to end

A user sends a casual request, and `search_listings` runs first. It removes anything in `listings.json` priced over `max_price`, filters out sizes that don't match, and then ranks the remaining listings by how well the user's `description` overlaps with each one's `title`, `description`, and `style_tags`, returning the dicts best match first. The top listing then goes into `suggest_outfit` along with the user's wardrobe (either the `example_wardrobe` from `wardrobe_schema.json` or an empty one), where it gets paired against closet pieces by `category`, `colors`, and `style_tags`. The resulting outfit text and that same listing dict are passed to `create_fit_card` to produce the caption. The case I need to handle carefully is an empty search result: if `search_listings` returns an empty list, the steps after it should not run, since there is no real item to style. In that case the agent stops the chain and reports that it found nothing.

### Traced walkthrough

**Example user query:** "I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers."

**Step 1, parse:**
The loop reads the query and pulls out three values, writing them to `session["parsed"]`: `description="vintage graphic tee"`, `size="M"`, `max_price=30.00`. The "baggy jeans and chunky sneakers" bit isn't a search filter, it's about what the user already owns, so it doesn't go into the search call. It matters later, in the wardrobe.

**Step 2, search_listings:**
The session has `parsed` but no `search_results`, so the loop calls `search_listings(description="vintage graphic tee", size="M", max_price=30.00)`.

Inside: load all listings, drop anything over $30.00, then keep only sizes where "m" appears in the size string. That substring rule is the loosest part of the design, since "M" sits inside "S/M" and "M/L" too, so combined sizes pass. Whatever survives gets scored on how many of "vintage", "graphic", "tee" turn up in the title, description, and `style_tags`.

The top match is **lst_002**, the "Y2K Baby Tee — Butterfly Print": `size` "S/M" (clears the M filter), `price` 18.00 (under the cap), `style_tags` `["y2k", "vintage", "graphic tee", "cottagecore"]` (scores on both "vintage" and "graphic tee"). The return is a list with lst_002 first, and it gets written to `session["search_results"]`.

**Step 3, select the item:**
`session["search_results"]` isn't empty, so the loop sets `session["selected_item"] = search_results[0]`, which is:

```json
{
  "id": "lst_002",
  "title": "Y2K Baby Tee — Butterfly Print",
  "category": "tops",
  "style_tags": ["y2k", "vintage", "graphic tee", "cottagecore"],
  "size": "S/M",
  "condition": "excellent",
  "price": 18.00,
  "colors": ["white", "pink", "purple"],
  "brand": null,
  "platform": "depop"
}
```

`brand` being null is normal in this dataset, so anything that displays the brand has to handle it being missing.

**Step 4, suggest_outfit:**
Now the session has `selected_item` but no `outfit_suggestion`, so the loop calls `suggest_outfit(session["selected_item"], session["wardrobe"])` where the wardrobe is `get_example_wardrobe()`. That closet already holds the pieces the user mentioned: `w_001` "Baggy straight-leg jeans, dark wash" (bottoms, "baggy" in its tags) and `w_007` "Chunky white sneakers" (shoes, "chunky" in its tags). The tool reads the tee's `colors` and `style_tags`, scans the wardrobe `items` by `category`, and returns a string like: "Pair the butterfly baby tee with your baggy dark-wash jeans (w_001) and the chunky white sneakers (w_007). Throw the vintage black denim jacket (w_006) over it on cooler days." That string is written to `session["outfit_suggestion"]`.

**Step 5, create_fit_card:**
The session has `outfit_suggestion` but no `fit_card`, so the loop calls `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. It returns a caption naming the tee, the $18 price, and depop, something like: "thrifted this y2k butterfly baby tee on depop for $18 and it was meant to be. styled it with my baggy jeans and chunky sneakers for an easy 2000s look." That goes to `session["fit_card"]`.

**Final output to user:**
`session["error"]` is None, so the user sees the matched listing (lst_002, $18, depop), the outfit built from their own closet, and the fit card caption they could post.

### Error path (search returns nothing)

Say the user asks for the same tee but "under $10". The parse step sets `max_price=10.00`. `search_listings` filters every listing out and returns `[]`, which lands in `session["search_results"]`.

The loop sees the empty list and a filter still in play, so it takes the fallback first: drop the size filter and search again, noting that it relaxed the size. If that turns up something, the user gets results with a heads-up that size M came up empty. If it's still empty after loosening, the loop sets `session["error"]` to something like "No listings under $10 matched 'vintage graphic tee'. Try raising your price." and returns the session right there. `suggest_outfit` and `create_fit_card` never run, so `selected_item`, `outfit_suggestion`, and `fit_card` all stay None. The user sees just that message and the nudge to loosen a filter.
