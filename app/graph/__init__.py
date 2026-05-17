"""Legacy graph module — kept as compatibility stubs only.

After the strict pipeline switch, the runtime no longer loads the k2-18
LearningChunkGraph. These stubs let modules that still mention the old types
(``retriever.py`` / ``generator.py`` / ``ingest.py``) import cleanly without
forcing a refactor of code paths that are not called from the new API.

Anything you find here that touches a real graph should be considered dead
code unless you are explicitly running the legacy ingest (``app.rag.ingest``).
"""
