# CLAUDE.md

## Project overview

This project converts Paul's French-Canadian recipe collection from a Word document (`2025-03-28_Recettes.docx`) into Mela recipe manager format (`.melarecipe` JSON files).

## Key files

- `parse_recipes.py` - Main parser script. Reads the docx, extracts recipes (title, ingredients, instructions, notes, images, metadata), and writes `.melarecipe` files.
- `recipes/` - Output directory containing individual `.melarecipe` JSON files (84 recipes).
- `recettes.melarecipes` - ZIP bundle of all recipes for sharing (generated with `--bundle`).
- `2025-03-28_Recettes.docx` - Source document (not to be modified).

## How the parser works

The docx uses Word heading styles to structure recipes:
- **Heading 1** = Main category (e.g., HORS D'OEUVRES, SOUPE ET POTAGE)
- **Heading 2/3** = Recipe title (or sub-category like BOEUF, VOLAILLE)
- **List Paragraph** = Ingredients and instruction steps
- **Normal** = Metadata, section headers, notes, URLs

The parser uses state machine logic (`preamble` -> `ingredients` -> `instructions` -> `notes`) and heuristics to split content when explicit section headers are missing.

Images are extracted from inline `w:drawing` elements via their `a:blip` references, base64-encoded, and embedded in the JSON per the Mela file format spec.

## Running

```bash
pip install python-docx
python parse_recipes.py           # individual .melarecipe files
python parse_recipes.py --bundle  # also creates .melarecipes ZIP
```

## Conventions

- All recipes get a "Paul" category added automatically.
- Empty/placeholder recipes (no ingredients or instructions) are skipped.
- EMF images and images under 1KB are excluded.
- Duplicate recipe names get a numeric suffix in filenames.
