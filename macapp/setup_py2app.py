"""py2app build configuration for the ipdf macOS app.

Build a double-clickable ``ipdf.app`` (run this from the repository root, on a
Mac, inside a virtualenv that has the deps + py2app installed)::

    pip install -r macapp/requirements.txt py2app
    python macapp/setup_py2app.py py2app

The result lands in ``dist/ipdf.app``. See macapp/README notes in the project
README for the WeasyPrint native-library caveat.
"""

from setuptools import setup

APP = ["macapp/launcher.py"]

# Non-Python assets the Flask frontend needs at runtime.
DATA_FILES = [
    ("webapp/templates", ["webapp/templates/index.html"]),
    ("webapp/static", ["webapp/static/style.css", "webapp/static/app.js"]),
]

OPTIONS = {
    "argv_emulation": False,
    # Pull in our own packages plus the ones py2app can't always trace.
    "packages": ["ipdf", "webapp", "macapp", "weasyprint", "markdown", "mammoth"],
    "includes": ["flask", "werkzeug", "jinja2"],
    "plist": {
        "CFBundleName": "ipdf",
        "CFBundleDisplayName": "ipdf",
        "CFBundleIdentifier": "com.motdiem.ipdf",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        # Document types we can open (informational; the UI also accepts drops).
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Markdown or Word document",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": [
                    "net.daringfireball.markdown",
                    "org.openxmlformats.wordprocessingml.document",
                    "public.plain-text",
                ],
            }
        ],
    },
}

setup(
    name="ipdf",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
