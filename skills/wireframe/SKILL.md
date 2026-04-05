---
name: Project Wireframe Generator
description: This skill converts any page into a wireframe-only version with consistent placeholder imagery, black background, and grey cross indicators.
---

# Project Wireframe Generator Skill

Use this skill to convert the visual layout of a project into a clean wireframe. This is useful for focusing on layout, structure, and hierarchy without being distracted by final assets.

## Core Features
1. **True Black Theme**: Replaces all background dark colors with `#000000`.
2. **Placeholder Logic**: Replaces all `<img>` tags and `background-image` inline styles with a structural `div` container.
3. **Cross Motif**: Styles placeholders with a grey background and a diagonal cross motif.

## Usage Instructions
1. Ensure the `wireframe-placeholder.svg` is present in the `assets/` directory of the project.
2. Run the provided refitting scripts in the `scripts/` directory to batch process HTML files.
3. Apply the `wireframe-cross` utility class to your structural containers in the Tailwind configuration.

## Required Assets
- `assets/wireframe-placeholder.svg`: The SVG cross pattern used for backgrounds.

## Implementation Details
The conversion process involves:
- Updating Tailwind configuration for `background-dark` and `background-darker`.
- Injecting a custom `@layer utilities` block for the `.wireframe-cross` pattern.
- Replacing image elements with structural `<div>` elements that maintain the original layout classes.
