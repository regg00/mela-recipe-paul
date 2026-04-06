#!/usr/bin/env python3
"""Parse recipes from docx and generate .melarecipes file for Mela app."""

import argparse
import base64
import json
import re
import uuid
import zipfile
import os
from docx import Document
from docx.oxml.ns import qn

DOCX_PATH = "/Users/regis.tremblay-lefrancois/Downloads/mela/2025-03-28_Recettes.docx"
OUTPUT_DIR = "/Users/regis.tremblay-lefrancois/Downloads/mela/recipes"
OUTPUT_ZIP = "/Users/regis.tremblay-lefrancois/Downloads/mela/recettes.melarecipes"

# Sub-category headings that are NOT recipe titles
SUB_CATEGORIES = {
    "BŒUF", "VEAU", "AGNEAU", "PORC", "CHARCUTERIE", "VOLAILLE", "FONDUE",
    "POISSON ET CRUSTACÉS", "SAUCES ET BOUILLONS", "LÉGUMES", "SALADES",
    "PÂTES ALIMENTAIRES", "RIZ", "METS CANADIENS", "PAINS", "DESSERTS",
    "TARTE", "AUTRE", "GÂTEAU ET POUDINGS",
}

# Stop parsing at this heading
STOP_AT = "Tableaux de conversion"

# These Heading 1 categories should replace "Plat Principal" when they appear as Heading 2
# (the doc nests Desserts/Tarte/Pains etc. under Plat Principal as Heading 2)
PROMOTED_CATEGORIES = {
    "Desserts", "Tarte", "Pains", "Sauces Et Bouillons", "Légumes",
    "Gâteau Et Poudings", "Autre", "Mets Canadiens",
}


def normalize_section(text):
    """Normalize a section header string for comparison."""
    return text.strip().rstrip(':').strip().lower()


def parse_time_metadata(text):
    """Extract prep, cook, total time and yield from a metadata line."""
    info = {}
    prep = re.search(r'[Pp]r[ée]paration\s*:?\s*([\d]+\s*(?:MIN|min|minutes?|heures?))', text)
    cook = re.search(r'[Cc]uisson\s*:?\s*([\d]+\s*(?:MIN|min|minutes?|heures?))', text)
    total = re.search(r'[Tt]otal\s*:?\s*([\d]+\s*(?:MIN|min|minutes?|heures?))', text)
    portions = re.search(r'[Pp]ortions?\s*:?\s*([\d]+(?:\s*à\s*\d+)?)', text)
    rendement = re.search(r'[Rr]endement\s*:?\s*(.+?)(?:\s*$|\s*-|\s*Se\s)', text)

    if prep:
        info['prepTime'] = prep.group(1).strip()
    if cook:
        info['cookTime'] = cook.group(1).strip()
    if total:
        info['totalTime'] = total.group(1).strip()
    if portions:
        info['yield'] = portions.group(1).strip() + " portions"
    elif rendement:
        info['yield'] = rendement.group(1).strip()

    return info


def is_metadata_line(text):
    """Check if a line contains recipe metadata (prep time, cook time, etc.)."""
    text_lower = text.lower()
    keywords = ['préparation', 'cuisson', 'portions', 'rendement', 'refroidissement',
                'trempage', 'repos', 'réfrigération', 'macération']
    has_keyword = any(k in text_lower for k in keywords)
    has_number = bool(re.search(r'\d', text))
    return has_keyword and has_number


def is_section_header(text):
    """Check if text is a section header within a recipe."""
    normalized = normalize_section(text)
    headers = {
        'ingrédients', 'ingredients', 'préparation', 'preparation',
        'instructions', 'garniture', 'note', 'notes',
    }
    return normalized in headers


def get_section_type(text):
    """Return the section type if text is a section header, or None."""
    normalized = normalize_section(text)
    if normalized in ('ingrédients', 'ingredients'):
        return 'ingredients'
    if normalized in ('préparation', 'preparation', 'instructions'):
        return 'instructions'
    if normalized in ('note', 'notes'):
        return 'notes'
    if normalized in ('garniture',):
        return 'garniture'  # treated as sub-section of instructions
    return None


def extract_images_from_paragraph(para, doc_part):
    """Extract base64-encoded images from a paragraph's inline drawings.
    Returns a list of base64 strings. Skips EMF and oversized images."""
    images = []
    for run in para.runs:
        for drawing in run._element.findall(qn('w:drawing')):
            for blip in drawing.findall('.//' + qn('a:blip')):
                embed = blip.get(qn('r:embed'))
                if not embed:
                    continue
                rel = doc_part.rels.get(embed)
                if not rel or rel.is_external:
                    continue
                img_part = rel.target_part
                # Skip EMF (vector format, huge) and tiny images (<1KB likely icons)
                if img_part.content_type == 'image/x-emf':
                    continue
                if len(img_part.blob) < 1000:
                    continue
                images.append(base64.b64encode(img_part.blob).decode('ascii'))
    return images


def is_url(text):
    """Check if text is or starts with a URL."""
    return bool(re.match(r'https?://', text.strip()))


def is_sub_section_header(text, style_name):
    """Check if a Normal-style paragraph is a sub-section header."""
    t = text.strip().rstrip(':')
    if not t:
        return False
    if t == t.upper() and len(t) < 60 and style_name == 'Normal' and len(t) > 1:
        return True
    return False


def parse_recipes(docx_path):
    doc = Document(docx_path)
    recipes = []
    current_category = ""
    current_subcategory = ""

    i = 0
    paragraphs = doc.paragraphs

    while i < len(paragraphs):
        para = paragraphs[i]
        text = para.text.strip()
        style = para.style.name

        if text == STOP_AT:
            break

        if style == 'Heading 1' and text:
            current_category = text.title()
            current_subcategory = ""
            i += 1
            continue

        if style in ('Heading 2', 'Heading 3') and text:
            text_upper = text.upper().strip()
            # Check if it's a sub-category header
            if text_upper in SUB_CATEGORIES or text in SUB_CATEGORIES:
                sub = text.title()
                current_subcategory = sub
                i += 1
                continue

            # Special case: sub-categories that need special handling
            if text.lower() in ('gâteau et poudings', 'foncer un moule à tarte'):
                if text.lower() == 'gâteau et poudings':
                    current_subcategory = text.title()
                i += 1
                continue

            # It's a recipe title
            recipe_title = text
            # Build categories
            categories = []
            if current_subcategory and current_subcategory.title() in PROMOTED_CATEGORIES:
                # Use subcategory as the primary category instead of "Plat Principal"
                categories.append(current_subcategory)
            elif current_category:
                categories.append(current_category)
                if current_subcategory:
                    categories.append(current_subcategory)

            # Extract images from the title heading itself
            title_images = extract_images_from_paragraph(para, doc.part)
            i += 1
            recipe, i = parse_single_recipe(paragraphs, i, recipe_title, categories, doc.part, title_images)
            recipes.append(recipe)
            continue

        i += 1

    return recipes


def parse_single_recipe(paragraphs, start_idx, title, categories, doc_part, initial_images=None):
    """Parse a single recipe. Returns (recipe_dict, next_index)."""
    recipe = {
        'id': str(uuid.uuid4()),
        'title': title,
        'categories': categories,
        'ingredients': '',
        'instructions': '',
        'notes': '',
        'text': '',
        'link': '',
        'images': [],
        'prepTime': '',
        'cookTime': '',
        'totalTime': '',
        'yield': '',
    }

    i = start_idx
    state = 'preamble'
    ingredients_lines = []
    instructions_lines = []
    notes_lines = []
    preamble_lines = []
    urls = []
    recipe_images = list(initial_images or [])

    while i < len(paragraphs):
        para = paragraphs[i]
        text = para.text.strip()
        style = para.style.name

        # Extract images from every paragraph in this recipe's range
        # (before any break check, so we don't miss images on boundary paragraphs)


        # Stop at next recipe or category
        if style == 'Heading 1' and text:
            break
        if style in ('Heading 2', 'Heading 3') and text:
            break

        # Extract images from this paragraph
        para_images = extract_images_from_paragraph(para, doc_part)
        recipe_images.extend(para_images)

        if not text:
            i += 1
            continue

        # Check for URL anywhere
        if is_url(text):
            urls.append(text)
            i += 1
            continue

        # Check for section headers (works in any state)
        section = get_section_type(text)
        if section == 'ingredients':
            state = 'ingredients'
            i += 1
            continue
        elif section == 'instructions':
            state = 'instructions'
            i += 1
            continue
        elif section == 'notes':
            state = 'notes'
            i += 1
            continue
        elif section == 'garniture':
            # Garniture is a sub-section of instructions
            if state == 'ingredients':
                state = 'instructions'
            instructions_lines.append(f"# Garniture")
            i += 1
            continue

        # Check for metadata lines that also signal section change
        if is_metadata_line(text):
            meta = parse_time_metadata(text)
            for k, v in meta.items():
                if v and not recipe[k]:
                    recipe[k] = v
            # If we're in ingredients and see "Préparation" in the metadata line, switch to instructions
            if state == 'ingredients' and 'préparation' in text.lower():
                state = 'instructions'
            i += 1
            continue

        # Handle "Source :" lines
        if text.lower().startswith('source') and ':' in text:
            # Extract source info
            source_text = text.split(':', 1)[1].strip()
            if is_url(source_text):
                urls.append(source_text)
            else:
                notes_lines.append(f"Source: {source_text}")
            i += 1
            continue

        # Content handling based on state
        if state == 'preamble':
            if style == 'List Paragraph':
                # List items without header = ingredients
                state = 'ingredients'
                ingredients_lines.append(text)
            else:
                preamble_lines.append(text)
            i += 1
            continue

        if state == 'ingredients':
            if style == 'List Paragraph':
                ingredients_lines.append(text)
            elif is_sub_section_header(text, style):
                ingredients_lines.append(f"# {text.strip().rstrip(':')}")
            else:
                # Normal text in ingredients - could be sub-section header
                ingredients_lines.append(f"# {text.strip().rstrip(':')}")
            i += 1
            continue

        if state == 'instructions':
            if style == 'List Paragraph':
                instructions_lines.append(text)
            elif is_sub_section_header(text, style):
                instructions_lines.append(f"# {text.strip().rstrip(':')}")
            elif style == 'Normal':
                if text.lower().startswith('note') and ':' in text.lower()[:6]:
                    state = 'notes'
                    # The text after "Note:" is the note content
                    note_content = text.split(':', 1)[1].strip() if ':' in text else text
                    if note_content:
                        notes_lines.append(note_content)
                else:
                    instructions_lines.append(text)
            i += 1
            continue

        if state == 'notes':
            notes_lines.append(text)
            i += 1
            continue

        i += 1

    # For simple recipes with no section headers: try to split ingredients/instructions
    # If we have ingredients but no instructions, check if the last items look like instructions
    if ingredients_lines and not instructions_lines:
        # Heuristic: instructions often start with a verb and are longer sentences
        split_idx = None
        for idx, line in enumerate(ingredients_lines):
            # Skip section headers
            if line.startswith('#'):
                continue
            # If line is long (>60 chars) and starts with a common cooking verb, it's likely an instruction
            lower = line.lower()
            instruction_verbs = [
                'mélanger', 'melanger', 'huiler', 'déposer', 'faire', 'cuire', 'couper',
                'ajouter', 'porter', 'laisser', 'préchauffer', 'placer', 'dans ',
                'sur ', 'servir', 'répartir', 'lavez', 'coupez', 'mettez', 'faites',
                'rectifiez', 'pendant', 'retirer', 'remettre', 'piler', 'farcir',
                'insérer', 'réduire', 'incorporer', 'garnir', 'badigeonner',
            ]
            if any(lower.startswith(v) for v in instruction_verbs):
                if split_idx is None:
                    split_idx = idx
            elif split_idx is not None:
                # If we started seeing instructions but now see something that's not,
                # it might still be an instruction continuation
                pass

        if split_idx is not None:
            instructions_lines = ingredients_lines[split_idx:]
            ingredients_lines = ingredients_lines[:split_idx]

    # Assemble
    recipe['ingredients'] = '\n'.join(ingredients_lines)
    recipe['instructions'] = '\n'.join(instructions_lines)
    recipe['notes'] = '\n'.join(notes_lines)
    recipe['text'] = '\n'.join(preamble_lines) if preamble_lines else ''
    recipe['images'] = recipe_images
    if urls:
        recipe['link'] = urls[0]

    return recipe, i


def sanitize_filename(name, seen):
    """Create a unique safe filename."""
    safe = re.sub(r'[^\w\s\-àâäéèêëïîôùûüÿçœæ]', '', name, flags=re.UNICODE)
    safe = re.sub(r'\s+', '_', safe.strip())
    safe = safe[:80]
    # Handle duplicates
    base = safe
    counter = 2
    while safe in seen:
        safe = f"{base}_{counter}"
        counter += 1
    seen.add(safe)
    return safe


def main(bundle=False):
    print("Parsing recipes from docx...")
    recipes = parse_recipes(DOCX_PATH)

    # Filter out empty recipes (no ingredients AND no instructions)
    non_empty = []
    empty = []
    for r in recipes:
        if r['ingredients'].strip() or r['instructions'].strip():
            non_empty.append(r)
        else:
            empty.append(r)

    print(f"Found {len(non_empty)} recipes ({len(empty)} empty/placeholder entries skipped)\n")
    if empty:
        print("Skipped (no content):")
        for r in empty:
            print(f"  - {r['title']}")
        print()

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Print summary
    total_with_img = sum(1 for r in non_empty if r['images'])
    print(f"Recipes with images: {total_with_img}/{len(non_empty)}\n")

    print(f"{'#':<4} {'Title':<55} {'Category':<25} {'Ingr':<5} {'Instr':<5} {'Img':<4} {'Link'}")
    print("-" * 125)
    for idx, r in enumerate(non_empty, 1):
        cats = ', '.join(r['categories'])[:24]
        n_ing = len([l for l in r['ingredients'].split('\n') if l.strip()]) if r['ingredients'] else 0
        n_ins = len([l for l in r['instructions'].split('\n') if l.strip()]) if r['instructions'] else 0
        n_img = len(r['images'])
        title = r['title'][:53]
        link = 'Y' if r['link'] else ''
        print(f"{idx:<4} {title:<55} {cats:<25} {n_ing:<5} {n_ins:<5} {n_img:<4} {link}")

    # Add 'Paul' category to all recipes
    for r in non_empty:
        if 'Paul' not in r['categories']:
            r['categories'].insert(0, 'Paul')

    # Write individual .melarecipe files
    seen_names = set()
    print(f"\nWriting individual .melarecipe files...")
    for r in non_empty:
        fname = sanitize_filename(r['title'], seen_names) + '.melarecipe'
        fpath = os.path.join(OUTPUT_DIR, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=2)

    print(f"Created {len(non_empty)} .melarecipe files in: {OUTPUT_DIR}/")

    # Optionally bundle into a single .melarecipes file
    if bundle:
        print(f"\nBundling into {OUTPUT_ZIP}...")
        with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(OUTPUT_DIR):
                if fname.endswith('.melarecipe'):
                    zf.write(os.path.join(OUTPUT_DIR, fname), fname)
        print(f"Created: {OUTPUT_ZIP}")

    print(f"\nTo import into Mela: double-click the .melarecipe(s) files")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse recipes from docx into Mela format.')
    parser.add_argument('--bundle', action='store_true',
                        help='Also create a single .melarecipes ZIP file for sharing')
    args = parser.parse_args()
    main(bundle=args.bundle)
