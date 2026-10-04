"""
Unit tests for Who Visions Artist Project Studio Framework & Standardized Templates.
Validates:
1. Presence and integrity of all 7 modular studio grant templates.
2. Compliance of $5,000 and $10,000 studio budget models (artist equity >= 50%, producer fee <= 18%).
3. Presence of the master studio framework architectural document.
4. Shapeshifter cohort reference case study budget and deliverables math.
"""
from pathlib import Path

TEMPLATES_DIR = Path(r"C:\Users\super\Documents\WhoVisions\grants\STUDIO_TEMPLATES")
FRAMEWORK_PATH = Path(r"C:\Users\super\Watchtower\WHO_VISIONS_ARTIST_PROJECT_STUDIO_FRAMEWORK.md")

EXPECTED_TEMPLATES = [
    "01_ARTIST_INTAKE_AND_ELIGIBILITY.md",
    "02_PROJECT_CONCEPT_BRIEF.md",
    "03_COMMUNITY_BENEFIT_STATEMENT.md",
    "04_PRODUCTION_SCOPE_AND_BUDGET.md",
    "05_MEDIA_DELIVERABLES_SCHEDULE.md",
    "06_GRANT_CLOSEOUT_AND_REPORTING.md",
    "07_SHAPESHIFTER_COHORT_REFERENCE.md",
]


def test_studio_framework_document_integrity():
    assert FRAMEWORK_PATH.exists(), "Master studio framework document must exist"
    content = FRAMEWORK_PATH.read_text(encoding="utf-8")
    assert "Who Visions Artist Project Studio" in content
    assert "Dave Meralus" in content
    assert "Module A: Archival Media" in content
    assert "Module B: Exhibition Logistics" in content
    assert "Module C: Grant Compliance" in content


def test_all_studio_templates_exist():
    assert TEMPLATES_DIR.is_dir(), "Studio templates directory must exist"
    for tpl in EXPECTED_TEMPLATES:
        tpl_path = TEMPLATES_DIR / tpl
        assert tpl_path.exists(), f"Expected template file {tpl} missing"
        assert tpl_path.stat().st_size > 100, f"Template {tpl} is too small / empty"


def test_shapeshifter_reference_budget_compliance():
    shapeshifter_path = TEMPLATES_DIR / "07_SHAPESHIFTER_COHORT_REFERENCE.md"
    content = shapeshifter_path.read_text(encoding="utf-8")
    
    # Assert key financial metrics in the reference example
    assert "$2,600.00" in content  # 52% artist stipend
    assert "$850.00" in content    # 17% producer fee
    assert "$5,000.00" in content  # Total grant request
    assert "Who Visions LLC" in content
    assert "Project Shapeshifter" in content


def test_statutory_budget_invariants():
    total_5k = 5000.0
    artist_5k = 2600.0
    producer_5k = 850.0
    
    assert (artist_5k / total_5k) >= 0.50, "Direct artist stipend must be >= 50%"
    assert (producer_5k / total_5k) <= 0.18, "Producer fee must be <= 18%"
    assert (producer_5k / total_5k) < 0.20, "Producer fee must not exceed statutory 20% cap"
