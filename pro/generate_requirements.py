import pkg_resources

# Only keep libraries relevant to NexLedger
ALLOWED_PREFIXES = [
    "pyqt6",
    "pyqtgraph",
    "pandas",
    "numpy",
    "matplotlib",
    "pdfplumber",
    "reportlab",
    "sqlalchemy",
    "requests",
    "openpyxl",
    "python-dateutil",
    "pyyaml",
    "cryptography",
    "pillow",
    "fuzzywuzzy",
    "python-docx",
    "pyinstaller",
    "xlrd",
    "xlwt",
    "xlsxwriter",
    "regex",
    "chardet",
]

# Convert to lowercase for consistent comparison
ALLOWED_PREFIXES = [p.lower() for p in ALLOWED_PREFIXES]

def is_relevant(package_name: str):
    name = package_name.lower()
    return any(name.startswith(prefix) for prefix in ALLOWED_PREFIXES)

def main():
    installed_packages = pkg_resources.working_set
    filtered = []

    for dist in installed_packages:
        if is_relevant(dist.project_name):
            filtered.append(f"{dist.project_name}=={dist.version}")

    filtered.sort()

    with open("requirements.txt", "w") as f:
        f.write("\n".join(filtered))

    print("Filtered requirements.txt generated successfully!")
    print("\nPackages included:")
    for line in filtered:
        print(" -", line)

if __name__ == "__main__":
    main()
