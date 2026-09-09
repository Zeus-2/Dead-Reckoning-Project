"""Main menu for my final vehicle-telemetry dissertation toolkit."""

from pathlib import Path

from src.analysis import behaviour
from src.core.app_state import remember_path, remembered_path
from src.core.paths import newest_folder, open_html
from src.core.settings import RAW_DATA_FOLDER, TOOLKIT_VERSION
from src.dead_reckoning import v1, v2
from src.preprocessing import clean_dataset, privacy_trim
from src.visualisation import results, showcase


def show_menu():
    print()
    print(f"Vehicle Telemetry Thesis Toolkit - {TOOLKIT_VERSION}")
    print("=" * 52)
    print("1. Privacy trim my raw CSV recordings")
    print("2. Clean and classify my dataset")
    print("3. Run my V1 baseline dead reckoning")
    print("4. Run my V2 dead reckoning (with/without OSM)")
    print("5. Analyse my driving-behaviour features")
    print("6. Generate my comparison figures")
    print("7. Build and open my dissertation showcase")
    print("8. Open my latest showcase")
    print("0. Exit")


def current_cleaned():
    return remembered_path("last_cleaned_output")


def default_raw_source():
    remembered = remembered_path("last_raw_source")
    return remembered if remembered is not None else RAW_DATA_FOLDER


def open_latest_showcase():
    cleaned = current_cleaned()

    if cleaned is None:
        print("[ERROR] I do not have a remembered cleaned dataset yet.")
        return

    folder = newest_folder(cleaned, ("showcase",))

    if folder is None or not (folder / "index.html").exists():
        print("[ERROR] I have not built a showcase for this dataset yet.")
        return

    open_html(folder / "index.html")
    print(f"Opened: {folder / 'index.html'}")


def main():
    RAW_DATA_FOLDER.mkdir(parents=True, exist_ok=True)

    while True:
        show_menu()

        privacy_output = remembered_path("last_privacy_output")
        cleaned_output = current_cleaned()

        if privacy_output:
            print(f"\nMy latest privacy-trimmed dataset:\n  {privacy_output}")

        if cleaned_output:
            print(f"My latest cleaned dataset:\n  {cleaned_output}")

        choice = input("\nSelect an option: ").strip()

        if choice == "1":
            result = privacy_trim.main(
                default_source=default_raw_source()
            )

            if result is not None:
                remember_path("last_privacy_output", result)
                remember_path("last_raw_source", Path(result).parent)

        elif choice == "2":
            result = clean_dataset.main(default_source=privacy_output)

            if result is not None:
                remember_path("last_cleaned_output", result)

        elif choice == "3":
            result = v1.main(default_source=cleaned_output)

            if result is not None:
                remember_path("last_v1_output", result)

        elif choice == "4":
            result = v2.main(default_source=cleaned_output)

            if result is not None:
                remember_path("last_v2_output", result)

        elif choice == "5":
            result = behaviour.main(default_source=cleaned_output)

            if result is not None:
                remember_path("last_behaviour_output", result)

        elif choice == "6":
            result = results.main(default_source=cleaned_output)

            if result is not None:
                remember_path("last_visuals_output", result)

        elif choice == "7":
            result = showcase.main(default_source=cleaned_output)

            if result is not None:
                remember_path("last_showcase_output", result)

        elif choice == "8":
            open_latest_showcase()

        elif choice == "0":
            print("Exiting.")
            break

        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()
