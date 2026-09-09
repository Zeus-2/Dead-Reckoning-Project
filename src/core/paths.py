"""Path helpers used by the different stages of my toolkit."""

import os
import webbrowser
from datetime import datetime
from pathlib import Path


CLASSIFICATION_FOLDERS = (
    "01_PRIMARY_DEAD_RECKONING",
    "02_SUPPLEMENTARY_DISTANCE_ONLY",
    "03_PRELIMINARY_METHOD_DEVELOPMENT",
    "04_UNUSABLE",
)


def versioned_output_folder(parent, base_name):
    parent = Path(parent)
    base = parent / base_name

    if not base.exists():
        base.mkdir(parents=True, exist_ok=False)
        return base

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = parent / f"{base_name}_{stamp}"
    suffix = 1

    while candidate.exists():
        candidate = parent / f"{base_name}_{stamp}_{suffix}"
        suffix += 1

    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def newest_folder(parent, prefixes):
    parent = Path(parent)

    if not parent.exists() or not parent.is_dir():
        return None

    candidates = []

    for folder in parent.iterdir():
        if not folder.is_dir():
            continue

        if not any(folder.name.startswith(prefix) for prefix in prefixes):
            continue

        try:
            modified = folder.stat().st_mtime
        except OSError:
            modified = 0.0

        candidates.append((modified, folder))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def newest_cleaned_dataset(privacy_source):
    if privacy_source is None:
        return None

    return newest_folder(
        Path(privacy_source),
        ("cleaned_dataset",),
    )


def resolve_cleaned_dataset(path):
    path = Path(path)

    if not path.exists() or not path.is_dir():
        raise ValueError("The selected folder does not exist.")

    if path.name.startswith("cleaned_dataset"):
        return path

    candidate = newest_cleaned_dataset(path)

    if candidate is not None:
        return candidate

    raise ValueError("I could not find a cleaned_dataset folder there.")


def resolve_primary_folder(path):
    path = Path(path)

    if not path.exists() or not path.is_dir():
        raise ValueError("The selected source folder does not exist.")

    if path.name == "01_PRIMARY_DEAD_RECKONING":
        return path

    direct = path / "01_PRIMARY_DEAD_RECKONING"

    if direct.exists() and direct.is_dir():
        return direct

    cleaned = resolve_cleaned_dataset(path)
    primary = cleaned / "01_PRIMARY_DEAD_RECKONING"

    if primary.exists() and primary.is_dir():
        return primary

    raise ValueError("I could not find 01_PRIMARY_DEAD_RECKONING there.")


def normalise_run_name(name):
    value = Path(str(name)).stem.lower()

    for suffix in (
        "_privacy_trimmed_clean",
        "_privacy_trimmed",
        "_clean",
    ):
        if value.endswith(suffix):
            value = value[:-len(suffix)]

    return value


def short_run_label(name):
    value = normalise_run_name(name)

    if value.startswith("csvlog_"):
        value = value[7:]

    return value


def find_run_folder(results_folder, run_name):
    if results_folder is None:
        return None

    target = normalise_run_name(run_name)

    for folder in Path(results_folder).iterdir():
        if folder.is_dir() and normalise_run_name(folder.name) == target:
            return folder

    return None


def find_pbf_candidates(*roots):
    candidates = []
    seen = set()

    for root in roots:
        if root is None:
            continue

        root = Path(root)

        search_roots = [root]

        if root.is_file():
            search_roots = [root.parent]

        for search_root in search_roots:
            current = search_root

            for _ in range(4):
                if current.exists() and current.is_dir():
                    for pattern in ("*.osm.pbf", "*.pbf"):
                        for path in current.glob(pattern):
                            key = str(path.resolve()).lower()

                            if key not in seen:
                                seen.add(key)
                                candidates.append(path)

                if current.parent == current:
                    break

                current = current.parent

    return sorted(candidates, key=lambda path: path.name.lower())


def open_folder(path):
    path = Path(path)

    try:
        if os.name == "nt":
            os.startfile(str(path))
        else:
            webbrowser.open(path.resolve().as_uri())
        return True
    except Exception:
        return False


def open_html(path):
    try:
        webbrowser.open(Path(path).resolve().as_uri())
        return True
    except Exception:
        return False
