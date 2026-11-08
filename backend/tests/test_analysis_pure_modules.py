import ast
from decimal import Decimal
import math
from pathlib import Path
import pytest

from app.config import settings
from app.services.analysis.file_filter import is_ignored
from app.services.analysis.line_filter import classify_lines
from app.services.analysis.effective_change import calculate_dampened_lines, compute_commit_effective_change
from app.services.analysis.ownership import compute_module_ownership
from app.services.analysis.collaboration import PRData, compute_collaboration_scores
from app.services.analysis.scoring import calculate_final_scores, normalize_signal
from app.services.analysis.confidence import evaluate_member_confidence
from app.services.analysis.flags import (
    check_single_bulk_commit,
    check_late_dump,
    check_rewritten_history,
)
from app.services.summary import generate_rule_based_summary


def test_file_filter_rules():
    # Lockfiles ignored
    assert is_ignored("package-lock.json")[0] is True
    assert is_ignored("yarn.lock")[0] is True
    assert is_ignored("pnpm-lock.yaml")[0] is True
    assert is_ignored("Cargo.lock")[0] is True
    assert is_ignored("go.sum")[0] is True
    assert is_ignored("custom.lock")[0] is True

    # Directories ignored
    assert is_ignored("node_modules/express/index.js")[0] is True
    assert is_ignored("vendor/bundle/ruby.rb")[0] is True
    assert is_ignored(".next/server/page.js")[0] is True
    assert is_ignored(".venv/lib/site-packages/pkg.py")[0] is True
    assert is_ignored("src/__pycache__/app.cpython-312.pyc")[0] is True
    assert is_ignored(".git/objects/abc")[0] is True

    # Minified & Source Maps
    assert is_ignored("dist/bundle.min.js")[0] is True
    assert is_ignored("styles/app.min.css")[0] is True
    assert is_ignored("app.js.map")[0] is True

    # Images / Media / Binaries
    assert is_ignored("assets/logo.png")[0] is True
    assert is_ignored("media/intro.mp4")[0] is True
    assert is_ignored("fonts/font.woff2")[0] is True
    assert is_ignored("bin/app.exe")[0] is True

    # Generated files
    assert is_ignored("src/model.generated.cs")[0] is True
    assert is_ignored("proto/service_pb2.py")[0] is True

    # File size limit
    assert is_ignored("large_data.csv", size_bytes=500 * 1024, max_size_kb=400)[0] is True
    assert is_ignored("small_data.csv", size_bytes=100 * 1024, max_size_kb=400)[0] is False

    # Normal source files NOT ignored
    assert is_ignored("src/app.py")[0] is False
    assert is_ignored("frontend/components/Button.tsx")[0] is False
    assert is_ignored("main.go")[0] is False


def test_file_filter_vendored_libraries_and_fonts():
    # 1. bootstrap.css ignored as vendored library
    ignored, reason = is_ignored("static/css/bootstrap.css")
    assert ignored is True
    assert reason == "vendored_library"

    ignored, reason = is_ignored("bootstrap.css")
    assert ignored is True
    assert reason == "vendored_library"

    # 2. FontAwesome.otf and font extensions ignored as font
    ignored, reason = is_ignored("fonts/FontAwesome.otf")
    assert ignored is True
    assert reason == "font"

    ignored, reason = is_ignored("FontAwesome.otf")
    assert ignored is True
    assert reason == "font"

    for font_file in ["inter.ttf", "roboto.woff", "icon.woff2", "glyph.eot"]:
        ignored, reason = is_ignored(f"assets/fonts/{font_file}")
        assert ignored is True
        assert reason == "font"

    # 3. Normal app file NOT ignored
    ignored, reason = is_ignored("src/app.py")
    assert ignored is False
    assert reason == ""

    ignored, reason = is_ignored("backend/models.py")
    assert ignored is False
    assert reason == ""

    # 4. Vendored path markers
    for path_marker in [
        "static/vendor/plugin.js",
        "app/static/lib/react.js",
        "web/static/libs/moment.js",
        "assets/vendor/slider.js",
        "src/third_party/zlib/zlib.c",
        "bower_components/backbone/backbone.js",
        "wwwroot/lib/lib.js",
    ]:
        ignored, reason = is_ignored(path_marker)
        assert ignored is True
        assert reason == "vendored_library"

    # 5. Known third-party library filenames under static/assets/public/lib/vendor
    for lib_path in [
        "public/js/jquery.js",
        "assets/css/font-awesome.css",
        "assets/css/fontawesome.css",
        "lib/popper.js",
        "static/normalize.css",
        "assets/animate.css",
        "public/d3.js",
        "lib/chart.js",
    ]:
        ignored, reason = is_ignored(lib_path)
        assert ignored is True
        assert reason == "vendored_library"

    # 6. License banner > 20 KB
    for banner in [
        "/*! Bootstrap v5.3.0 */",
        "/*! jQuery v3.6.0 | (c) OpenJS Foundation */",
        "/*! Font Awesome Free 5.15.4 */",
        "/** @license MIT */",
        "/* Copyright (c) 2010-2024 Foo and other contributors */",
        "/* Copyright (c) ... and other contributors */",
    ]:
        ignored, reason = is_ignored(
            "custom_bundle.js",
            size_bytes=25 * 1024,
            content_preview=banner,
        )
        assert ignored is True
        assert reason == "license_banner"

    # License banner <= 20 KB (not ignored by banner)
    ignored, reason = is_ignored(
        "small_bundle.js",
        size_bytes=10 * 1024,
        content_preview="/*! Bootstrap v5.3.0 */",
    )
    assert ignored is False

    # > 20 KB without license banner
    ignored, reason = is_ignored(
        "large_app.js",
        size_bytes=25 * 1024,
        content_preview="/* Normal application code */\nfunction main() {}",
    )
    assert ignored is False


def test_rule_based_summary_never_names_ignored_files():
    facts = {
        "login": "alice",
        "counted_commits": 10,
        "active_days": 5,
        "top_files": [
            {"path": "static/css/bootstrap.css", "surviving_lines": 500},
            {"path": "fonts/FontAwesome.otf", "surviving_lines": 300},
            {"path": "src/app.py", "surviving_lines": 100},
        ],
        "owned_modules": [
            {"path": "static/vendor", "share": 0.9},
            {"path": "src", "share": 0.8},
        ],
        "top_commits": [
            {"sha": "abcdef123456", "sha_short": "abcdef1", "subject": "Initial feature"}
        ],
        "pull_requests_opened": 2,
        "reviews_given": 1,
        "flags": [],
    }
    summary_text, _, _ = generate_rule_based_summary(facts)
    assert "bootstrap.css" not in summary_text
    assert "FontAwesome.otf" not in summary_text
    assert "static/vendor" not in summary_text
    assert "src/app.py" in summary_text


def test_line_filter_c_like():
    js_lines = [
        "  ",
        "// this is a single line comment",
        "const x = 10; // with trailing comment",
        "/* multi line comment */",
        "let y = 20;",
        "/* start block",
        "   middle block",
        "   end block */",
        "const z = 30;",
    ]
    res = classify_lines("index.ts", js_lines)
    assert res == [
        False,  # blank
        False,  # comment
        True,   # code + comment
        False,  # block comment
        True,   # code
        False,  # start block
        False,  # middle
        False,  # end block
        True,   # code
    ]


def test_line_filter_python():
    py_lines = [
        "",
        "# comment line",
        "x = 1 # trailing comment",
        '"""',
        "standalone docstring",
        '"""',
        "y = 'this is a string # not a comment'",
        "def hello():",
        "    '''another docstring'''",
        "    return True",
    ]
    res = classify_lines("app.py", py_lines)
    assert res == [
        False,  # blank
        False,  # comment
        True,   # code
        False,  # docstring start
        False,  # docstring body
        False,  # docstring end
        True,   # code with string
        True,   # def hello():
        False,  # docstring
        True,   # return True
    ]


def test_line_filter_html_and_sql():
    html_lines = [
        "<!-- start comment -->",
        "<div>Hello World</div> <!-- trailing -->",
        "<!-- multi",
        "line",
        "-->",
    ]
    assert classify_lines("page.html", html_lines) == [False, True, False, False, False]

    sql_lines = [
        "-- select all",
        "SELECT id, name FROM users; -- with comment",
        "/* block comment */",
        "WHERE active = 1;",
    ]
    assert classify_lines("query.sql", sql_lines) == [False, True, False, True]


def test_effective_change_dampening():
    cap = 1500
    assert calculate_dampened_lines(500, cap) == 500.0
    assert calculate_dampened_lines(1500, cap) == 1500.0

    large = 20000
    expected = 1500 + math.sqrt(20000 - 1500)
    assert calculate_dampened_lines(large, cap) == pytest.approx(expected, 0.01)


def test_effective_change_exclusions():
    # Merge commit excluded
    dampened, raw, excluded, note = compute_commit_effective_change(
        commit_sha="a" * 40,
        parent_count=2,
        is_bot=False,
    )
    assert excluded is True
    assert dampened == 0.0

    # Bot commit excluded
    dampened, raw, excluded, note = compute_commit_effective_change(
        commit_sha="b" * 40,
        parent_count=1,
        is_bot=True,
    )
    assert excluded is True
    assert dampened == 0.0


def test_scoring_weights_redistribution_and_exact_sum():
    member_ids = ["m1", "m2", "m3"]
    raw_survival = {"m1": 100.0, "m2": 50.0, "m3": 50.0}
    raw_effective = {"m1": 200.0, "m2": 100.0, "m3": 100.0}
    raw_ownership = {"m1": 0.60, "m2": 0.20, "m3": 0.20}
    raw_collab = {"m1": 0.0, "m2": 0.0, "m3": 0.0}

    base_weights = {
        "survival": 0.40,
        "effective_change": 0.25,
        "ownership": 0.15,
        "collaboration": 0.20,
    }

    # When no collaboration data:
    percentages, signals, eff_weights = calculate_final_scores(
        member_ids=member_ids,
        raw_survival=raw_survival,
        raw_effective_change=raw_effective,
        raw_ownership=raw_ownership,
        raw_collaboration=raw_collab,
        weights=base_weights,
        has_collaboration_data=False,
    )

    # Check weights re-normalized
    assert eff_weights["collaboration"] == 0.0
    assert sum(eff_weights.values()) == pytest.approx(1.0, 0.001)

    # Check sum is EXACTLY Decimal('100.00')
    total = sum(percentages.values())
    assert total == Decimal("100.00")
    assert percentages["m1"] > percentages["m2"]


def test_confidence_evaluation_and_caps():
    # High confidence: >=15 commits, >=5 active days, >=100 surviving lines
    high = evaluate_member_confidence(
        counted_commits=20,
        active_days=6,
        surviving_lines=150,
        collaboration_raw=0.0,
        has_unlinked_identities=False,
        project_is_truncated=False,
        total_project_counted_commits=30,
    )
    assert high == "high"

    # High capped at medium if unlinked identities exist
    capped_unlinked = evaluate_member_confidence(
        counted_commits=20,
        active_days=6,
        surviving_lines=150,
        collaboration_raw=0.0,
        has_unlinked_identities=True,
        project_is_truncated=False,
        total_project_counted_commits=30,
    )
    assert capped_unlinked == "medium"

    # High capped at medium if truncated
    capped_trunc = evaluate_member_confidence(
        counted_commits=20,
        active_days=6,
        surviving_lines=150,
        collaboration_raw=0.0,
        has_unlinked_identities=False,
        project_is_truncated=True,
        total_project_counted_commits=30,
    )
    assert capped_trunc == "medium"

    # Low data cap: if project has < 5 commits total, everything is low
    capped_low = evaluate_member_confidence(
        counted_commits=4,
        active_days=4,
        surviving_lines=500,
        collaboration_raw=2.0,
        has_unlinked_identities=False,
        project_is_truncated=False,
        total_project_counted_commits=4,
    )
    assert capped_low == "low"


def test_ownership_computation():
    module_totals = {
        "core": 100,
        "api": 50,
        "small": 10,  # Below 20 lines min threshold
    }
    member_module_lines = {
        "m1": {"core": 80, "api": 10, "small": 8},
        "m2": {"core": 20, "api": 40, "small": 2},
    }
    signals, owned = compute_module_ownership(
        module_totals=module_totals,
        member_module_lines=member_module_lines,
        total_surviving_lines=160,
        min_module_lines=20,
    )

    # m1 owns core (80%), m2 owns api (80%), small has no owner
    assert len(owned["m1"]) == 1
    assert owned["m1"][0]["path"] == "core"
    assert owned["m1"][0]["share"] == 0.80

    assert len(owned["m2"]) == 1
    assert owned["m2"][0]["path"] == "api"
    assert owned["m2"][0]["share"] == 0.80

    assert signals["m1"] > 0
    assert signals["m2"] > 0


def test_collaboration_computation():
    members = {"m1": "alice", "m2": "bob"}
    prs = [
        PRData(number=1, author_login="alice", state="closed", merged=True, reviewers=["bob"]),
        PRData(number=2, author_login="bob", state="open", merged=False, reviewers=["alice"]),
    ]
    raw, norm, has_collab = compute_collaboration_scores(members, prs)
    assert has_collab is True
    # Alice: 1.0 (merged PR 1) + 0.5 (review on PR 2) = 1.5
    # Bob: 0.25 (open PR 2) + 0.5 (review on PR 1) = 0.75
    assert raw["m1"] == 1.5
    assert raw["m2"] == 0.75
    assert norm["m1"] == pytest.approx(1.5 / 2.25)


def test_security_audit_no_shell_true_in_analysis():
    analysis_dir = Path(__file__).resolve().parent.parent / "app" / "services" / "analysis"
    for py_file in analysis_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell":
                        assert isinstance(kw.value, ast.Constant) and kw.value.value is False, (
                            f"Disallowed shell={kw.value.value} in {py_file}"
                        )

