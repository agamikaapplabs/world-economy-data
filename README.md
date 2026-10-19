# World Economy Cockpit Web — V5

Collectors now write working data to `data/raw/`.

`publish_v5.py` creates the public/client contract:

    data/manifest.json
    data/current/
    data/history/
    data/metadata/
    data/reports/

The browser loads the manifest and current views first. Full canonical history is loaded only when a history tile is opened.

Run:

    UPDATE_AND_OPEN.bat

Publish existing raw data only:

    PUBLISH_ONLY.bat
