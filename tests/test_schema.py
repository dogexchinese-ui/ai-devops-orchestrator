import pytest

from orchestrator.schema import ValidationError, validate_plan


def test_validate_plan_ok():
    validate_plan(
        {
            "planId": "p1",
            "subtasks": [
                {"id": "a", "prompt": "do a"},
                {"id": "b", "prompt": "do b", "dependsOn": ["a"]},
            ],
        }
    )


def test_validate_plan_cycle():
    with pytest.raises(ValidationError):
        validate_plan(
            {
                "planId": "p1",
                "subtasks": [
                    {"id": "a", "prompt": "do a", "dependsOn": ["b"]},
                    {"id": "b", "prompt": "do b", "dependsOn": ["a"]},
                ],
            }
        )
