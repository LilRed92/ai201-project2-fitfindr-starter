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
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): ...
- `size` (str): ...
- `max_price` (float): ...

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): ...
- `wardrobe` (dict): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (...): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | |
| suggest_outfit | Wardrobe is empty | |
| create_fit_card | Outfit input is missing or incomplete | |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**Milestone 4 — Planning loop and state management:**

---

## A Complete Interaction (Step by Step)

### What FitFindr needs to do end to end

A user sends a casual request, and `search_listings` runs first. It removes anything in `listings.json` priced over `max_price`, filters out sizes that don't match, and then ranks the remaining listings by how well the user's `description` overlaps with each one's `title`, `description`, and `style_tags`, returning the dicts best match first. The top listing then goes into `suggest_outfit` along with the user's wardrobe (either the `example_wardrobe` from `wardrobe_schema.json` or an empty one), where it gets paired against closet pieces by `category`, `colors`, and `style_tags`. The resulting outfit text and that same listing dict are passed to `create_fit_card` to produce the caption. The case I need to handle carefully is an empty search result: if `search_listings` returns an empty list, the steps after it should not run, since there is no real item to style. In that case the agent stops the chain and reports that it found nothing.

### Traced walkthrough

**Example user query:** "I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers."

**Step 1 — search_listings:**
The agent pulls three values out of the request and calls `search_listings(description="vintage graphic tee", size="M", max_price=30.00)`.

Inside the tool: load all listings, drop anything over $30.00, then keep only the sizes that match "M" case-insensitively. The size matching is looser than I expected at first. "M" is a substring of "S/M", so a listing tagged `"S/M"` still passes the filter. That is worth noting, because several listings use combined sizes. The listings that remain are then scored on how many of the words "vintage", "graphic", and "tee" appear in the title, description, and `style_tags`.

The best match that survives is **lst_002**, the "Y2K Baby Tee — Butterfly Print". Its `size` is "S/M" (clears the M filter), its `price` is 18.00 (under the cap), and its `style_tags` are `["y2k", "vintage", "graphic tee", "cottagecore"]`, so it scores on both "vintage" and "graphic tee".

**Step 2 — the top result:**
The dict that comes back looks like this:

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

One thing to watch is that `brand` is `null` here, which is common in this dataset, so any code that displays the brand has to handle it being missing.

**Step 3 — suggest_outfit:**
Next the agent calls `suggest_outfit(new_item=<the lst_002 dict>, wardrobe=get_example_wardrobe())`. The wardrobe already contains the pieces the user described: `w_001` "Baggy straight-leg jeans, dark wash" (`category` bottoms, with "baggy" in its `style_tags`) and `w_007` "Chunky white sneakers" (`category` shoes, with "chunky" in its tags). The tool reads the tee's `colors` and `style_tags`, looks across the wardrobe `items` by `category`, and assembles an outfit: the butterfly tee with the baggy dark-wash jeans and the chunky white sneakers, possibly with `w_006`, the vintage black denim jacket, layered on top.

**Step 4 — create_fit_card:**
The outfit string and the lst_002 dict are passed to `create_fit_card`, which returns a short caption that names the tee, its $18 price, and that it is listed on depop.

**Final output to user:**
The user sees the matched listing, an outfit built from their own closet, and a caption they could post.

### Error path (search returns nothing)

Suppose the user asks for the same tee but "under $10". `search_listings` filters out every listing and returns `[]`. With no top result, the agent does not call `suggest_outfit` or `create_fit_card`. It tells the user that nothing matched and points to whichever filter was likely too tight, such as the price ceiling or the size, so they can loosen one and try again. Because the tool returns an empty list instead of raising, this stays a normal branch in the planning loop rather than an error.
