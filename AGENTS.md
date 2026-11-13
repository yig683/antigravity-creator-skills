# Workspace Visual & Engineering Guidelines

- **Generate Visual References First (`image-generator`):** Before building 3D Blender scenes (`makine_studio/episodes/*.py`), channel branding, thumbnails, or custom UI/graphic assets in this workspace, always generate visual concept/blueprint reference images using the `image-generator` subagent (for Makine Studio episodes, save under `makine_studio/references/<slug>/`) and inspect them with `read_file`.
- **Inspect & Match References:** Derive geometry silhouettes, proportions, mechanical connections, color contrast, lighting, and camera framing from those inspected visual references, then compare `--mode preview` / rendered visual outputs side-by-side against the references before finalizing.
