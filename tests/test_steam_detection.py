import os
import sys
import textwrap

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import steam_library as sl  # noqa: E402


SAMPLE_ACF = textwrap.dedent("""
    "AppState"
    {
        "appid"     "270230"
        "Universe"      "1"
        "name"      "Injustice: Gods Among Us Ultimate Edition"
        "StateFlags"        "4"
        "installdir"        "Injustice"
    }
""")

SAMPLE_LIBRARYFOLDERS = textwrap.dedent(r"""
    "libraryfolders"
    {
        "0"
        {
            "path"      "C:\\Program Files (x86)\\Steam"
            "label"     ""
            "contentid"     "1111111111111111111"
            "apps"
            {
                "270230"        "1234567"
            }
        }
        "1"
        {
            "path"      "D:\\SteamLibrary"
            "label"     ""
            "contentid"     "2222222222222222222"
            "apps"
            {
                "440"       "7654321"
            }
        }
    }
""")


def test_loads_handles_comments_and_escaped_quotes():
    text = """
    // a leading comment
    "root"
    {
        "key" "value with \\"quotes\\""  // inline comment
    }
    """
    data = sl.loads(text)
    assert data["root"]["key"] == 'value with "quotes"'


def test_parse_acf_text_extracts_appid_and_name():
    info = sl.parse_acf_text(SAMPLE_ACF)
    assert info == {
        "appid": "270230",
        "name": "Injustice: Gods Among Us Ultimate Edition",
    }


def test_parse_acf_text_returns_none_when_incomplete():
    broken = '"AppState"\n{\n    "Universe" "1"\n}\n'
    assert sl.parse_acf_text(broken) is None


def test_parse_library_folders_text_extracts_paths():
    paths = sl.parse_library_folders_text(SAMPLE_LIBRARYFOLDERS)
    assert paths == [r"C:\Program Files (x86)\Steam", r"D:\SteamLibrary"]


def test_parse_library_folders_text_empty_when_missing_root():
    assert sl.parse_library_folders_text('"somethingelse" { "a" "b" }') == []


def test_resolve_steamapps_dir(tmp_path):
    root = tmp_path / "Steam"
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    assert sl.resolve_steamapps_dir(str(root)) == str(steamapps)
    assert sl.resolve_steamapps_dir(str(tmp_path / "missing")) is None


def test_get_installed_games_scans_manifests_and_extra_libraries(tmp_path):
    main_root = tmp_path / "SteamMain"
    extra_root = tmp_path / "SteamExtra"
    main_steamapps = main_root / "steamapps"
    extra_steamapps = extra_root / "steamapps"
    main_steamapps.mkdir(parents=True)
    extra_steamapps.mkdir(parents=True)

    (main_steamapps / "appmanifest_270230.acf").write_text(SAMPLE_ACF, encoding="utf-8")
    (extra_steamapps / "appmanifest_440.acf").write_text(
        textwrap.dedent("""
            "AppState"
            {
                "appid"     "440"
                "name"      "Team Fortress 2"
            }
        """),
        encoding="utf-8",
    )

    library_vdf = f"""
    "libraryfolders"
    {{
        "0"
        {{
            "path"      "{main_root}"
        }}
        "1"
        {{
            "path"      "{extra_root}"
        }}
    }}
    """
    (main_steamapps / "libraryfolders.vdf").write_text(library_vdf, encoding="utf-8")

    games, steamapps_dirs = sl.get_installed_games(manual_path=str(main_steamapps))

    names = sorted(g["name"] for g in games)
    assert names == ["Injustice: Gods Among Us Ultimate Edition", "Team Fortress 2"]
    assert str(main_steamapps) in steamapps_dirs
    assert str(extra_steamapps) in steamapps_dirs


def test_get_installed_games_returns_empty_for_unknown_path(tmp_path):
    games, steamapps_dirs = sl.get_installed_games(manual_path=str(tmp_path / "does-not-exist"))
    assert games == []
    assert steamapps_dirs == []


def test_find_userdata_ids(tmp_path):
    userdata = tmp_path / "userdata"
    (userdata / "123456789").mkdir(parents=True)
    (userdata / "987654321").mkdir(parents=True)
    (userdata / "not-an-id").mkdir(parents=True)

    ids = sl.find_userdata_ids(str(tmp_path))
    assert ids == ["123456789", "987654321"]


def test_find_userdata_ids_missing_dir(tmp_path):
    assert sl.find_userdata_ids(str(tmp_path)) == []
