# Contributing

This repo files AI SEO tools by the layer of the stack they work on and ships a script that checks the first two layers. The most useful contributions are a corrected fact with a vendor link, and a new AI user agent with a link to the vendor's crawler documentation.

## Change the data, then regenerate

1. Edit [tools.yaml](tools.yaml). One entry per tool, entry plan facts only.
2. Set `layers` to what the vendor says the tool does: `fetch`, `markup`, `measure`, `create`, `data`. If the public pages do not say, leave the layer out.
3. Never type the README table by hand. Run `python render_table.py --write`, then `python render_table.py --check`.
4. Open a pull request with the vendor link.

## Add a user agent

Agents live in the `AGENTS` tuple in [ai_seo_check.py](ai_seo_check.py). Each one needs a token, a vendor and a purpose of `training`, `search` or `user`. Link the vendor page that documents the purpose.

## Accepted

* Price, plan, engine or integration changes with a source link.
* A new AI user agent with documentation.
* Extra checks for the fetch or markup layer, with a test.

## Not accepted

* Affiliate or tracking links.
* Review scores and star ratings.
* Dependencies in `ai_seo_check.py`. It stays standard library only and must run on Python 3.10.

## Run the tests

```bash
pip install pyyaml
python -m unittest discover -s tests -v
```
