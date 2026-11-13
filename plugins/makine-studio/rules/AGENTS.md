# Makine Studio Plugin Guidelines

- Keep generated episode scripts (`episodes/<slug>.py`), visual reference sheets (`references/<slug>/`), and rendered media outputs (`output/`) inside the user's active workspace rather than writing user project files inside the plugin installation folder.
- **Visual Reference First (`image-generator`):** Before authoring 3D Blender geometry or branding artwork for a new episode or scene, generate clear visual concept/blueprint reference images in `<workspace>/makine_studio/references/<slug>/` using the `image-generator` subagent, inspect them with `read_file`, and match their proportions, material contrast, mechanical joints, and framing in Blender—then verify `--mode preview` PNGs against those references.
- Resolve the bundled studio runtime dynamically from `<plugin_root>/engine` (for example via `PYTHONPATH`) and invoke `python -m studio.pipeline --episode-file <workspace>/episodes/<slug>.py --output-dir <workspace>/output`.
- Always run `--mode preview` first and visually inspect the rendered frames and audio (`master_audio.wav`) before launching `--mode full --skip-tts`.
- Use `--recomposite-only` whenever only HUD label offsets, headlines, or subtitle styling change so 3D frames do not need re-rendering.
