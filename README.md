# Mela Recipe Importer - Paul's Recipes

Parse a Word document (.docx) containing French-Canadian recipes and convert them into [Mela](https://mela.recipes/) compatible `.melarecipe` files.

## What it does

- Extracts **84 recipes** from `2025-03-28_Recettes.docx` into individual `.melarecipe` JSON files
- Preserves categories (Hors d'oeuvres, Soupe, Plat Principal, Desserts, etc.)
- Extracts embedded images from the docx and base64-encodes them into each recipe
- Parses metadata: prep time, cook time, yield, source URLs, notes
- Adds a "Paul" category to all recipes for easy filtering in Mela
- Optionally bundles everything into a single `.melarecipes` ZIP for sharing

## Requirements

- Python 3.8+
- [python-docx](https://python-docx.readthedocs.io/)

```bash
pip install python-docx
```

## Usage

### Generate individual recipe files

```bash
python parse_recipes.py
```

This creates one `.melarecipe` file per recipe in the `recipes/` directory.

### Bundle for sharing

```bash
python parse_recipes.py --bundle
```

Also creates `recettes.melarecipes` (a ZIP archive) for easy sharing.

### Import into Mela

- **Individual files**: Select all `.melarecipe` files in Finder and double-click to open with Mela
- **Bundle**: Double-click `recettes.melarecipes` and Mela will import all recipes at once

## Recipe categories

| Category | Count |
|---|---|
| Hors d'oeuvres | 8 |
| Soupe et Potage | 6 |
| Entree | 4 |
| Dejeuner / Brunch | 3 |
| Plat Principal (Boeuf, Veau, Porc, Volaille, Fondue, Poisson) | 22 |
| Sauces et Bouillons | 5 |
| Legumes | 4 |
| Pates Alimentaires | 3 |
| Riz | 5 |
| Mets Canadiens | 6 |
| Pains | 2 |
| Desserts / Gateaux / Tartes | 16 |

## File format

Each `.melarecipe` file follows the [Mela file format specification](https://mela.recipes/fileformat/index.html) - a JSON file containing title, ingredients, instructions, images (base64), categories, and metadata.
