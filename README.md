# FitFindr

FitFindr is a small multi-tool agent for thrifting. You describe what you're after in plain language, and it searches a set of mock secondhand listings, picks the best match, suggests how to style it against your wardrobe, and writes a short caption you could actually post. The point of the project wasn't really the clothes. It was building an agent that decides which tool to call based on what came back from the last one, and that doesn't fall apart when a tool returns nothing useful.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Put your Groq key in a `.env` file in the repo root (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Then run the app:

```bash
python app.py
```

It serves at http://localhost:7860 (check the terminal, the port can change). Type something like "vintage graphic tee under $30, size M", pick a wardrobe, and hit Find it. There's also a row of example queries at the bottom, including one deliberately impossible one so you can see the no-results path.

To run the tools on their own:

```bash
pytest tests/
```

## The tools

There are three tools, each a plain function in `tools.py`. I built and tested each one by itself before wiring anything together.

**`search_listings(description, size, max_price) -> list[dict]`**
Searches the 40 listings in `data/listings.json`. `description` (str) is the words for what you want and is required. `size` (str or None) filters by a case-insensitive substring match, so "M" matches "M", "S/M", and "M/L"; pass None to skip it. `max_price` (float or None) is an inclusive ceiling; None skips it. It scores each surviving listing by how many of the description words show up across the title, description, joined style_tags, and category, drops anything that scores zero, and returns the listing dicts sorted best first. No match returns an empty list, never an exception. Each dict has `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), and `platform`.

**`suggest_outfit(new_item, wardrobe) -> str`**
Takes one listing dict and the user's wardrobe and returns outfit ideas as a string. `new_item` (dict) is a listing from the search; the prompt includes its title, description, category, colors, style_tags, condition, and price so the model has the full picture, with the title, category, colors, and tags doing the most work. `wardrobe` (dict) follows `wardrobe_schema.json`, so it has an `items` list where each piece has `id`, `name`, `category`, `colors`, `style_tags`, and an optional `notes`. If the wardrobe has pieces, it asks the LLM to build one or two outfits and name the specific pieces used. If the wardrobe is empty, it switches to a general-advice prompt and gives styling ideas for that one item instead of a dead end.

**`create_fit_card(outfit, new_item) -> str`**
Writes a short, casual caption. `outfit` (str) is the suggestion text from `suggest_outfit`, and `new_item` (dict) is the same listing, where it pulls title, price, platform, and style_tags. It returns a 2 to 4 sentence caption that reads like a real post. Both LLM tools use Groq's `llama-3.3-70b-versatile`.

## How the planning loop works

This is the part I care most about. The loop in `agent.py` (`run_agent`) does not call all three tools in order no matter what. Each step it looks at the session dict, figures out what's missing or what just came back, and decides the next move from that.

It starts by parsing the query into a description, size, and price. I went with regex for this, not the LLM. One thing I had to add: if the query has a "what I own" clause like "I mostly wear baggy jeans and chunky sneakers", I cut everything from "I wear" onward before parsing. Without that cut, words like "baggy" and "jeans" get scored as things the user is searching for and pull denim listings above the tee they actually asked about.

Then it calls `search_listings` and checks the result before anything else. This is the real branch point. If the result is empty and the user had given a size, the loop first retries the search with the size filter dropped, since the inconsistent size strings in the data are the most common reason a search comes back empty. If that retry finds something, it keeps those results and records a note that it ignored the size, so the user knows what changed. If the result is still empty, or there was no size to drop, the loop writes a specific error to the session and returns right there, without calling `suggest_outfit` on empty input. If there are results, it sets `selected_item` to the top one and keeps going.

From there it calls `suggest_outfit` with the selected item and the wardrobe. An empty wardrobe still comes back with useful styling advice, so that's treated like any normal result and the loop continues. The only thing that stops it at this step is an actual LLM failure, which comes back as a string starting with "Sorry, I couldn't put an outfit together, because ...". The loop checks for that prefix so a dead API call doesn't get passed downstream as if it were a real suggestion. Last, it calls `create_fit_card` with the suggestion and the item, and stores the caption.

So the behavior genuinely changes based on what each tool returns. An impossible search ends the whole thing after one tool call. A good search runs all three. That difference is the planning loop doing its job.

## State management

Everything for one interaction lives on a single session dict built by `_new_session()` in `agent.py`. There are no globals, and no tool hands its result straight to the next one. Each tool's output is written to a named field, and the next step reads from that field. The fields are `query`, `parsed`, `search_results`, `selected_item`, `wardrobe`, `outfit_suggestion`, `fit_card`, `error`, and `notice` (set when the agent relaxes a filter, like dropping the size after an empty search).

The chain is `search_results` to `selected_item` to `outfit_suggestion` to `fit_card`. The listing found by the search flows into `suggest_outfit` as `selected_item` without the user retyping anything, and the same listing plus the outfit text flow into `create_fit_card`. At the end, the caller checks `error` first; if it's None, the other fields are filled in. `app.py` reads the finished session and maps it onto the three output panels.

## Error handling

Each tool owns its own failure mode and none of them crash the agent.

`search_listings` returns `[]` when nothing matches. The loop first tries to recover by dropping the size filter and searching again (see the stretch section below), and only if that still finds nothing does it turn the empty result into a message that names what failed and what to try. Real example from my testing, the query "designer ballgown size XXS under $5":

> No listings matched 'designer ballgown' under $5, even after I ignored the size XXS filter. Try raising your price or describing it differently.

In that run `outfit_suggestion` and `fit_card` both stayed None, which is how I confirmed `suggest_outfit` never got called.

`suggest_outfit` handles an empty wardrobe by giving general advice for the item instead of giving up. Real example, the Y2K baby tee with an empty wardrobe:

> The Y2K Baby Tee — Butterfly Print is a charming, nostalgic piece. To style it, pair it with high-waisted jeans or a flowy skirt for a cute, casual look. It fits into the cottagecore aesthetic, so consider adding floral or pastel-colored accessories ...

If the LLM call itself fails, it returns a "Sorry, I couldn't put an outfit together, because ..." string instead of raising.

`create_fit_card` guards against an empty outfit before it ever calls the LLM. Real example, calling it with an empty string:

> Can't write a fit card without an outfit suggestion. Run the styling step first.

Each of these has a test in `tests/test_tools.py`, so a regression on any failure mode shows up when I run pytest.

## Stretch: retry with loosened constraints

I built the retry-with-fallback stretch into the planning loop. When `search_listings` comes back empty and the user had specified a size, the agent doesn't give up right away. It drops the size filter and runs the search one more time, keeping the price filter in place. The size is the first thing it relaxes because the size strings in the data are so inconsistent that an exact-ish size is the likeliest reason a search finds nothing. If the second search turns up listings, the agent uses them and writes a note like "Nothing matched size XXL, so I dropped the size filter and searched without it," which shows up at the top of the listing panel so the user understands what was adjusted. If even the loosened search finds nothing, it falls back to the normal no-results error and stops. The price filter is never auto-dropped, since spending more money isn't a change the agent should make on the user's behalf.

## Reflection on the spec

Writing the tool specs before any code is the part that helped most. Having the exact return shape and the failure behavior written down for each tool meant that when I went to implement them, there was a clear right answer to test against. The empty-list rule for `search_listings` is a good example: because planning.md already said no match returns `[]` and never an exception, I knew exactly what my test should assert and what the planning loop should check for, so the search-to-loop handoff worked the first time instead of me discovering the contract by trial and error. The written-out field lists helped the same way, the agent code knew which fields to read off a listing without me guessing.

Where the implementation diverged: the empty-wardrobe handling. My first version had `suggest_outfit` return a short "add at least two items" message and skip the LLM, on the logic that a one-piece closet can't make a full outfit. When I reread the spec during the failure-mode milestone, it actually asks for useful styling advice in that case, not a dead end. So I switched it to general advice for the item. The reason for the divergence was honestly just that I'd guessed at the behavior I thought made sense instead of matching what the spec asked for, and testing against the spec caught it. That change also rippled into the agent: the advice is now a normal result, so the loop continues to the fit card instead of stopping there.

A couple of smaller things I'd harden next. The size matching is the loosest part of the design and I knew it going in. Sizes in the data are all over the place ("M", "S/M", "W30 L30", "US 8.5", "One Size"), so I match on substring, which keeps "M" from throwing out "S/M" but also lets "M" match strings I didn't intend. And the query parser is regex, so "around 30 dollars" or a bare "medium" without the word "size" won't parse. I kept it simple and predictable on purpose, but it's the most brittle piece.

## AI usage

I used Claude (through Claude Code) to help write the implementation. Two specific cases:

**Implementing the three tools.** I gave Claude one tool spec block at a time from `planning.md` (the inputs, the return shape, and the failure mode) plus the field reference at the top of `utils/data_loader.py`, and asked it to fill in each function in `tools.py`. It produced working first drafts. I overrode two things. The empty-wardrobe path it first wrote returned a no-LLM "wardrobe too sparse" message, and I changed that to general styling advice once I matched it against the spec. And `create_fit_card` outputs were too similar across runs at first, so I bumped the temperature to 1.0 and reran it three times on the same input until the captions actually differed before I trusted it.

**Wiring the planning loop.** I gave Claude the Planning Loop and State Management sections of `planning.md`, the agent diagram, and the existing session dict in `agent.py`, and asked it to implement `run_agent`. The branching it generated was close, but I added the query parser myself, including the part that cuts off the "what I own" clause, because the generated version fed the whole query into the search and the wardrobe words polluted the results. I also added the error-prefix check so the loop could tell a real LLM failure apart from a real suggestion, then verified both the happy path and the no-results path by printing the session dict and confirming the no-results run never touched the styling tools.
