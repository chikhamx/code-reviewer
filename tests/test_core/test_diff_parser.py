from code_review_agent.core.diff_parser import DiffParser


def test_parse_basic_diff(sample_diff):
    parser = DiffParser()
    files = parser.parse(sample_diff)

    assert len(files) == 1
    assert files[0].path == "src/auth.py"
    assert files[0].language == "python"
    assert len(files[0].hunks) == 2


def test_parse_finds_hunks(sample_diff):
    parser = DiffParser()
    files = parser.parse(sample_diff)

    hunk1 = files[0].hunks[0]
    assert hunk1.old_start == 10
    assert hunk1.new_start == 10

    hunk2 = files[0].hunks[1]
    assert hunk2.old_start == 25
    assert hunk2.new_start == 25


def test_language_detection():
    parser = DiffParser()
    assert parser._detect_language("main.go") == "go"
    assert parser._detect_language("lib.rs") == "rust"
    assert parser._detect_language("App.tsx") == "typescript"
    assert parser._detect_language("unknown.xyz") == ""


def test_diff_to_text(sample_diff):
    parser = DiffParser()
    files = parser.parse(sample_diff)
    text = parser.diff_to_text(files)

    assert "src/auth.py" in text
    assert "@@ -10,7 +10,7 @@" in text


def test_empty_diff():
    parser = DiffParser()
    files = parser.parse("")
    assert files == []
